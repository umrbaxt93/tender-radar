"""GitHub report-only adapter; Codex is invoked by the official action."""
import json
import os
from pathlib import Path
import sys
import supervisor as s
ROOT=s.ROOT

def write_status(status, attempts=()):
    (ROOT/'reports').mkdir(exist_ok=True)
    (ROOT/'reports/status.json').write_text(json.dumps({'status':status,'phase':'SCAFFOLD_ONLY','attempts':list(attempts)},indent=2)+'\n')
    print('Supervisor: '+status)

def trusted(env):
    return env.get('GITHUB_ACTIONS')=='true' and env.get('GITHUB_REF')=='refs/heads/main' and env.get('GITHUB_EVENT_NAME') in ('workflow_dispatch','schedule')

def main():
    if not trusted(os.environ):
        write_status('blocked_untrusted_context');return 2
    if '--finalize' in sys.argv:
        status=json.loads((ROOT/'reports/status.json').read_text())
        if status['status']=='codex_pending':
            result=ROOT/'reports/codex-review.md'
            if os.environ.get('CODEX_OUTCOME')=='success' and result.is_file() and result.stat().st_size:
                (ROOT/'reports/review.md').write_text('# Unverified Codex scaffold review\n\n'+s.redact(result.read_text()[:30000],[]))
                write_status('review_ready',status['attempts']+[{'provider':'codex','status':'success'}]);return 0
            write_status('all_configured_providers_failed',status['attempts']);return 1
        return 0 if status['status'] in ('review_ready','done_no_provider_calls') else 1
    report=ROOT/'reports';report.mkdir(exist_ok=True)
    def flag(value):
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('codex_needed='+value+'\n')
    flag('false')
    if (ROOT/'PROGRESS.md').read_text().splitlines()[0]=='STATUS: DONE':
        write_status('done_no_provider_calls');return 0
    prompt='\n\n'.join('--- '+f+' ---\n'+(ROOT/f).read_text() for f in s.CONTEXT)
    if len(prompt)>60000:
        write_status('context_limit_exceeded');return 2
    configured=[];keys=[]
    for p,k,m in [('gemini','GEMINI_API_KEY','GEMINI_MODEL'),('claude','ANTHROPIC_API_KEY','CLAUDE_MODEL')]:
        key=os.environ.get(k,'').strip();model=os.environ.get(m,'').strip()
        if key and model:
            keys.append(key);configured.append((p,model,k,key))
    if any(k in prompt for k in keys):
        write_status('secret_detected_in_context');return 2
    context=Path(os.environ['RUNNER_TEMP'])/'tender-review-context.md'
    context.write_text(prompt)
    result,attempts=s.chain(configured,prompt)
    if result:
        (report/'review.md').write_text('# Unverified scaffold review\n\n'+s.redact(result,keys)[:30000]+'\n')
        write_status('review_ready',attempts)
    elif os.environ.get('CODEX_CONFIGURED')=='true':
        flag('true');write_status('codex_pending',attempts)
    else:
        write_status('blocked_no_successful_provider',attempts)
    return 0

if __name__=='__main__':raise SystemExit(main())
