"""Offline repository checks; no application execution or external calls."""
from pathlib import Path
import re
root = Path(__file__).resolve().parents[1]
required = ['docs/SPEC.md','CLAUDE.md','AGENTS.md','GEMINI.md',
 '.agents/rules/tender-radar.md','.antigravity/rules.md','prompts/CLOUD_REVIEW_PROMPT.md',
 'PROGRESS.md','DECISIONS.md','TODO.md','.env.example','Makefile',
 'docker-compose.yml','.gitignore','supervisor.sh','supervisor.ps1','.github/workflows/checks.yml',
 'ci/supervisor.py','ci/gemini-deny.toml','.github/workflows/supervisor.yml','docs/CLOUD_WORKFLOW.md',
 'pyproject.toml','alembic.ini','alembic/env.py','radar/models.py','radar/cli.py','docs/HANDOFF.md']
for name in required:
 assert (root/name).is_file() and (root/name).stat().st_size, f'Missing {name}'
for name in ['CLAUDE.md','GEMINI.md','.agents/rules/tender-radar.md','.antigravity/rules.md']:
 assert (root/name).read_bytes() == (root/'AGENTS.md').read_bytes(), 'Rule drift'
# A local .env is expected on a host that actually runs the platform (scripts/bootstrap.sh
# creates one). What must never happen is committing it, so check tracking, not existence.
import subprocess
assert '.env' in (root/'.gitignore').read_text().split(), '.env must stay git-ignored'
tracked = subprocess.run(['git', 'ls-files', '--error-unmatch', '.env'], cwd=root,
                         capture_output=True)
assert tracked.returncode != 0, '.env is tracked by git; remove it from the index'
# The cloud review prompt is the supervisor's only instruction source and stays review-only.
review = (root/'prompts/CLOUD_REVIEW_PROMPT.md').read_text()
for phrase in ['Review only', 'do not output application code']:
 assert phrase in review, 'Cloud review prompt lost its review-only constraint'
import ast
supervisor = ast.parse((root/'ci/supervisor.py').read_text())
context = next(n for n in ast.walk(supervisor)
               if isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', '') == 'CONTEXT')
files = [e.value for e in context.value.elts]
assert files[0] == 'prompts/CLOUD_REVIEW_PROMPT.md', 'Supervisor must read the review prompt first'
assert 'AGENTS.md' not in files and 'CLAUDE.md' not in files, 'Supervisor must not read dev rules'
# Secrets never belong in tracked files.
tracked = [p for p in root.rglob('*') if p.is_file()
           and not any(part in {'.git','.venv','node_modules','__pycache__','out','data'}
                       for part in p.parts)]
pattern = re.compile(r'\b(?:glpat-|sk-proj-|sk-ant-)[A-Za-z0-9_-]{16,}|AIza[A-Za-z0-9_-]{30,}')
for path in tracked:
 if path.suffix in {'.md','.py','.yml','.yaml','.toml','.ini','.txt','.sh','.ps1','.example','.json'}:
  assert not pattern.search(path.read_text(errors='ignore')), f'Credential detected in {path}'
# Synthetic fixtures must stay labelled as synthetic.
for path in (root/'samples/synthetic').glob('*.json'):
 assert '"synthetic": true' in path.read_text(), f'Unlabelled fixture {path}'
print('Repository validation passed. Hosted Actions checks and authenticated CLI smoke tests '
      'remain separate; no real source data has been imported.')
