"""Offline scaffold checks; no application implementation or external calls."""
from pathlib import Path
import json
import re
root = Path(__file__).resolve().parents[1]
required = ['docs/SPEC.md','CLAUDE.md','AGENTS.md','GEMINI.md',
 '.agents/rules/tender-radar.md','.antigravity/rules.md','prompts/AGENT_PROMPT.md',
 'PROGRESS.md','DECISIONS.md','TODO.md','.env.example','Makefile',
 'docker-compose.yml','.gitignore','supervisor.sh','supervisor.ps1','.github/workflows/checks.yml',
 'ci/supervisor.py','ci/gemini-deny.toml','.github/workflows/supervisor.yml','docs/CLOUD_WORKFLOW.md']
for name in required:
 assert (root/name).is_file() and (root/name).stat().st_size, f'Missing {name}'
for name in ['CLAUDE.md','GEMINI.md','.agents/rules/tender-radar.md','.antigravity/rules.md']:
 assert (root/name).read_bytes() == (root/'AGENTS.md').read_bytes(), 'Rule drift'
assert not (root/'.env').exists(), 'Unexpected .env'
for folder in ('radar','src','app','classify','alembic'):
 assert not (root/folder).exists(), 'Application source forbidden in current phase'
for name in required:
 text=(root/name).read_text()
 assert not re.search(r'\b(?:glpat-|sk-proj-)[A-Za-z0-9_-]{16,}',text), 'Credential detected'
assert 'ENABLE_AGENT_SCHEDULE' in (root/'.github/workflows/supervisor.yml').read_text()
print('Scaffold validation passed. Hosted Actions checks and authenticated CLI smoke tests remain separate.')
