"""Bounded, report-only CLI orchestration. No application code or repository writes."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = (
    ('gemini', 'GEMINI_API_KEY_FILE', 'GEMINI_API_KEY', 'GEMINI_MODEL'),
    ('claude', 'ANTHROPIC_API_KEY_FILE', 'ANTHROPIC_API_KEY', 'CLAUDE_MODEL'),
    ('codex', 'OPENAI_API_KEY_FILE', 'CODEX_API_KEY', 'CODEX_MODEL'),
)
CONTEXT = ('prompts/AGENT_PROMPT.md', 'docs/SPEC.md', 'PROGRESS.md',
           'DECISIONS.md', 'TODO.md', 'docs/SOURCE_API.md')
MAX_SECONDS = 180


def permitted(env):
    return (env.get('CI') == 'true' and env.get('CI_COMMIT_REF_PROTECTED') == 'true'
            and bool(env.get('CI_DEFAULT_BRANCH'))
            and env.get('CI_COMMIT_BRANCH') == env.get('CI_DEFAULT_BRANCH')
            and env.get('CI_PIPELINE_SOURCE') in ('web', 'schedule'))


def redact(text, secrets):
    for secret in sorted((s for s in secrets if s), key=len, reverse=True):
        text = text.replace(secret, '[REDACTED]')
    return re.sub(r'\b(?:sk-[A-Za-z0-9_-]{12,}|AIza[A-Za-z0-9_-]{20,}|glpat-[A-Za-z0-9_-]{12,})',
                  '[REDACTED]', text)


def parse_output(provider, raw):
    if len(raw) > 2_000_000:
        raise ValueError('oversize_output')
    if provider != 'codex':
        data = json.loads(raw)
        if data.get('error') or data.get('is_error'):
            raise ValueError('provider_error')
        result = data.get('response' if provider == 'gemini' else 'result', '')
    else:
        events = [json.loads(line) for line in raw.splitlines() if line.strip()]
        if any(e.get('type') == 'turn.failed' for e in events):
            raise ValueError('provider_error')
        if not any(e.get('type') == 'turn.completed' for e in events):
            raise ValueError('incomplete_turn')
        messages = [e['item'].get('text', '') for e in events
                    if e.get('type') == 'item.completed'
                    and e.get('item', {}).get('type') == 'agent_message']
        result = messages[-1] if messages else ''
    if not isinstance(result, str) or not result.strip():
        raise ValueError('empty_response')
    return result


def command(provider, model, home):
    if provider == 'gemini':
        policy = home / '.gemini/policies/deny.toml'
        policy.parent.mkdir(parents=True)
        policy.write_text((ROOT / 'ci/gemini-deny.toml').read_text())
        return ['gemini', '-p', 'Review the supplied text only; do not use tools.',
                '--model', model, '--output-format', 'json']
    if provider == 'claude':
        return ['claude', '-p', '--bare', '--tools', '', '--disallowedTools', 'mcp__*',
                '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
                '--no-session-persistence', '--max-turns', '1', '--max-budget-usd', '0.25',
                '--model', model, '--output-format', 'json']
    # Fresh HOME and empty cwd: no project hooks, instructions, plugins or MCP configs.
    return ['codex', '-a', 'never', 'exec', '--skip-git-repo-check',
            '--sandbox', 'read-only', '--ephemeral', '--json', '--model', model,
            '-c', 'features.shell_tool=false', '-c', 'features.unified_exec=false',
            '-c', 'features.shell_snapshot=false', '-c', 'features.apps=false',
            '-c', 'features.skill_mcp_dependency_install=false',
            '-c', 'web_search="disabled"', '-']


def run_one(provider, model, secret_name, secret, prompt):
    with tempfile.TemporaryDirectory(prefix='tender-review-') as temp:
        home = Path(temp) / 'home'
        cwd = Path(temp) / 'empty'
        home.mkdir(); cwd.mkdir()
        cmd = command(provider, model, home)
        # Never inherit GitLab job tokens, other provider keys, proxies or user configs.
        child_env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
                     'HOME': str(home), 'LANG': 'C.UTF-8', 'CI': 'true',
                     'NO_COLOR': '1', secret_name: secret}
        try:
            proc = subprocess.Popen(cmd, cwd=cwd, env=child_env,
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True, start_new_session=True)
        except OSError:
            return None, 'cli_unavailable'
        try:
            raw, error = proc.communicate(prompt, timeout=MAX_SECONDS)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            return None, 'timeout'
        except BaseException:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            raise
        if proc.returncode != 0:
            # Emit fixed categories only; never provider text, headers, or secrets.
            diagnostic = (raw + (error or '')).lower()
            categories = (
                ('invalid_api_key', ('api key not valid', 'api_key_invalid', 'invalid api key')),
                ('authentication_failed', ('unauthenticated', 'authentication', '401')),
                ('quota_exceeded', ('resource_exhausted', 'quota', '429')),
                ('model_unavailable', ('model not found', 'not found for api version', '404')),
                ('policy_configuration', ('policy', 'toml')),
                ('runtime_dependency', ('cannot find module', 'module_not_found', 'enoent')),
                ('permission_denied', ('permission_denied', '403')),
                ('invalid_cli_option', ('unknown argument', 'unknown option')),
            )
            for category, markers in categories:
                if any(marker in diagnostic for marker in markers):
                    return None, category
            print('Redacted CLI diagnostic: '+redact((error or raw)[-2000:], [secret]), flush=True)
            return None, 'cli_failed'
        try:
            return parse_output(provider, raw), 'success'
        except (ValueError, TypeError, KeyError, AttributeError):
            return None, 'invalid_response'


def chain(configured, prompt, runner=run_one):
    attempts = []
    for provider, model, secret_name, secret in configured:
        result, reason = runner(provider, model, secret_name, secret, prompt)
        attempts.append({'provider': provider, 'status': reason})
        if result:
            return result, attempts
    return None, attempts


def main():
    reports = ROOT / 'reports'
    reports.mkdir(exist_ok=True)
    # Remove only our own stale output from an earlier manual run.
    (reports / 'review.md').unlink(missing_ok=True)
    def finish(status, attempts=(), code=0):
        (reports / 'status.json').write_text(json.dumps(
            {'status': status, 'phase': 'SCAFFOLD_ONLY', 'attempts': list(attempts)}, indent=2)+'\n')
        print('Supervisor: '+status)
        return code
    if not permitted(os.environ):
        return finish('blocked_untrusted_context', code=2)
    if (ROOT / 'PROGRESS.md').read_text().splitlines()[0] == 'STATUS: DONE':
        return finish('done_no_provider_calls')
    configured, skipped, secrets = [], [], []
    for provider, file_var, child_var, model_var in PROVIDERS:
        location, model = os.environ.get(file_var), os.environ.get(model_var, '').strip()
        if not location or not model:
            skipped.append({'provider': provider, 'status': 'not_configured'})
            continue
        path = Path(location)
        # FILE CI variables are runner-managed files; reject repo files and huge inputs.
        try:
            if path.resolve().is_relative_to(ROOT.resolve()) or path.stat().st_size > 8192:
                return finish('invalid_secret_file', code=2)
            secret = path.read_text().strip()
        except (OSError, ValueError):
            return finish('unreadable_secret_file', code=2)
        if not secret or '\n' in secret:
            return finish('invalid_secret_value', code=2)
        secrets.append(secret)
        configured.append((provider, model, child_var, secret))
    if not configured:
        return finish('blocked_no_provider_credentials_or_models', skipped, 2)
    prompt = '\n\n'.join(f'--- {f} ---\n'+(ROOT/f).read_text() for f in CONTEXT)
    if len(prompt) > 60000:
        return finish('context_limit_exceeded', code=2)
    # Secret text cannot accidentally enter a model prompt through committed docs.
    if any(secret in prompt for secret in secrets):
        return finish('secret_detected_in_context', code=2)
    fingerprint = hashlib.sha256((prompt + (ROOT/'ci/supervisor.py').read_text()
        + (ROOT/'ci/versions.json').read_text()
        + json.dumps([(p,m) for p,m,_,_ in configured])).encode()).hexdigest()
    cache = ROOT / '.supervisor-state'
    last = cache / 'last-success'
    if (os.environ.get('CI_PIPELINE_SOURCE') == 'schedule' and last.is_file()
            and last.read_text().strip() == fingerprint):
        return finish('unchanged_no_provider_calls')
    result, attempts = chain(configured, prompt)
    if result is None:
        return finish('all_configured_providers_failed', skipped+attempts, 1)
    result = redact(result, secrets)
    (reports/'review.md').write_text('# Scaffold review (unverified model output)\n\n'+result[:30000]+'\n')
    cache.mkdir(exist_ok=True)
    last.write_text(fingerprint+'\n')
    return finish('review_ready', skipped+attempts)


if __name__ == '__main__':
    raise SystemExit(main())
