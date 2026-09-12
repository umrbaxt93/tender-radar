import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('supervisor',Path(__file__).resolve().parents[1]/'ci/supervisor.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)

class SupervisorTests(unittest.TestCase):
 def test_untrusted_and_mr_contexts_denied(self):
  env={'CI':'true','CI_COMMIT_REF_PROTECTED':'true','CI_COMMIT_BRANCH':'main','CI_DEFAULT_BRANCH':'main','CI_PIPELINE_SOURCE':'web'}
  self.assertTrue(s.permitted(env))
  for key,value in [('CI_PIPELINE_SOURCE','merge_request_event'),('CI_COMMIT_REF_PROTECTED','false'),('CI_COMMIT_BRANCH','feature'),('CI_DEFAULT_BRANCH','')]:
   self.assertFalse(s.permitted({**env,key:value}))
 def test_order_and_stop_after_success(self):
  calls=[]
  def run(p,*args):
   calls.append(p);return ('review','success') if p=='claude' else (None,'timeout')
  output,attempts=s.chain([(p,'m','KEY','secret') for p in ('gemini','claude','codex')],'prompt',run)
  self.assertEqual(calls,['gemini','claude']);self.assertEqual(output,'review')
 def test_exhaustion(self):
  result,attempts=s.chain([(p,'m','K','s') for p in ('gemini','claude','codex')],'p',lambda *a:(None,'cli_failed'))
  self.assertIsNone(result);self.assertEqual(len(attempts),3)
 def test_structured_provider_error(self):
  for p,raw in [('gemini','{"error":{"code":429},"response":"partial"}'),('claude','{"is_error":true,"result":"partial"}'),('codex','{"type":"turn.failed"}')]:
   with self.assertRaises(ValueError):s.parse_output(p,raw)
 def test_quota_word_in_success_is_not_failure(self):
  self.assertEqual(s.parse_output('gemini','{"response":"Set quota limits."}'),'Set quota limits.')
 def test_empty_and_invalid_responses(self):
  for raw in ['{}','{"response":""}','not-json']:
   with self.assertRaises(ValueError):s.parse_output('gemini',raw)
 def test_codex_requires_completion(self):
  message=json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'review'}})
  with self.assertRaises(ValueError):s.parse_output('codex',message)
  self.assertEqual(s.parse_output('codex',message+'\n{"type":"turn.completed"}'),'review')
 def test_secret_redaction(self):
  self.assertEqual(s.redact('abc secret-value xyz',['secret-value']),'abc [REDACTED] xyz')
 def test_child_environment_has_no_gitlab_or_other_key(self):
  class Process:
   returncode=0
   def communicate(self,*args,**kwargs):return ('{"response":"ok"}',None)
  with patch.dict(os.environ,{'CI_JOB_TOKEN':'private','OPENAI_API_KEY':'private'}),patch.object(s.subprocess,'Popen',return_value=Process()) as popen:
   self.assertEqual(s.run_one('gemini','m','GEMINI_API_KEY','only-this','p')[0],'ok')
   env=popen.call_args.kwargs['env']
   self.assertNotIn('CI_JOB_TOKEN',env);self.assertNotIn('OPENAI_API_KEY',env)
   self.assertEqual(env['GEMINI_API_KEY'],'only-this')
 def test_timeout_kills_own_process(self):
  # Exercise actual process timeout without any model call or external dependency.
  with patch.object(s,'command',return_value=[sys.executable,'-c','import time;time.sleep(5)']),patch.object(s,'MAX_SECONDS',0.02):
   self.assertEqual(s.run_one('gemini','m','KEY','s','p'),(None,'timeout'))
 def test_done_skips_credentials_and_models(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'PROGRESS.md').write_text('STATUS: DONE\n')
   with patch.object(s,'ROOT',root),patch.object(s,'permitted',return_value=True),patch.object(s,'chain') as chain:
    self.assertEqual(s.main(),0);chain.assert_not_called()
   self.assertEqual(json.loads((root/'reports/status.json').read_text())['status'],'done_no_provider_calls')

if __name__=='__main__':unittest.main()
