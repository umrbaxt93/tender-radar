import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ci=Path(__file__).resolve().parents[1]/'ci'
sys.path.insert(0,str(ci))
import github_review as g

class GitHubReviewTests(unittest.TestCase):
 def test_only_default_branch_dispatch_or_schedule(self):
  good={'GITHUB_ACTIONS':'true','GITHUB_REF':'refs/heads/main','GITHUB_EVENT_NAME':'workflow_dispatch'}
  self.assertTrue(g.trusted(good))
  self.assertFalse(g.trusted({**good,'GITHUB_EVENT_NAME':'pull_request_target'}))
  self.assertFalse(g.trusted({**good,'GITHUB_REF':'refs/heads/topic'}))
 def test_done_prevents_calls(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'PROGRESS.md').write_text('STATUS: DONE\n')
   with patch.object(g,'ROOT',root),patch.object(g,'trusted',return_value=True),patch.dict(os.environ,{'GITHUB_OUTPUT':str(root/'output')}),patch.object(g.s,'chain') as run:
    self.assertEqual(g.main(),0);run.assert_not_called()
 def test_no_credentials_reports_blocker(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   for f in g.s.CONTEXT:
    path=root/f;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('TODO\n')
   env={'GITHUB_OUTPUT':str(root/'output'),'RUNNER_TEMP':tmp}
   with patch.object(g,'ROOT',root),patch.object(g,'trusted',return_value=True),patch.dict(os.environ,env,clear=True):
    self.assertEqual(g.main(),0)
   self.assertEqual(json.loads((root/'reports/status.json').read_text())['status'],'blocked_no_successful_provider')
 def test_codex_handoff_without_exposing_openai_key(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   for f in g.s.CONTEXT:
    path=root/f;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('TODO\n')
   env={'GITHUB_OUTPUT':str(root/'output'),'RUNNER_TEMP':tmp,'CODEX_CONFIGURED':'true'}
   with patch.object(g,'ROOT',root),patch.object(g,'trusted',return_value=True),patch.dict(os.environ,env,clear=True):
    self.assertEqual(g.main(),0)
   self.assertIn('codex_needed=true',(root/'output').read_text())
   self.assertEqual(json.loads((root/'reports/status.json').read_text())['status'],'codex_pending')

if __name__=='__main__':unittest.main()
