"""Scripted native provider protocols; no CLI authentication or inference calls."""
import io
import json
import os
import tempfile
import threading
import unittest
from unittest.mock import patch
from ros.lib import providers

class Process:
    def __init__(self,events):
        self.stdin=io.StringIO();self.stdout=io.StringIO(''.join(json.dumps(e)+'\n' for e in events));self.pid=0
    def poll(self):return None

class ProtocolTests(unittest.TestCase):
    def test_codex_dynamic_tools_and_terminal_state(self):
        process=Process([{'id':1,'result':{}},{'id':2,'result':{'thread':{'id':'t1'}}},{'method':'item/agentMessage/delta','params':{'delta':'Partial '}},{'id':12,'method':'item/tool/call','params':{'tool':'claims','arguments':{},'callId':'op1'}},{'method':'thread/tokenUsage/updated','params':{'tokenUsage':{'inputTokens':10,'outputTokens':5}}},{'method':'turn/completed','params':{'turn':{'status':'completed'}}}])
        output=[];calls=[]
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'CODEX_HOME':folder}),patch.object(providers,'codex_executable',return_value='fixture-codex'),patch.object(providers,'launch',return_value=process),patch.object(providers,'terminate'):
            result=providers.codex({'model':'codex:fixture','effort':'low','messages':[{'role':'user','content':'Inspect'}],'images':[{'mime':'image/png','data':'synthetic-fixture'}],'system':'Scoped context','tools':[{'name':'claims','description':'Read claims','parameters':{'type':'object'}}]},output.append,lambda name,args,key:calls.append((name,key)) or {'committed':'event:1'},threading.Event(),lambda p:None)
        self.assertEqual(output,['Partial ']);self.assertEqual(calls,[('claims','op1')]);self.assertEqual(result['usage']['inputTokens'],10)
        sent=[json.loads(line) for line in process.stdin.getvalue().splitlines()];thread=next(e for e in sent if e.get('method')=='thread/start')['params']
        self.assertEqual(thread['sandbox'],'read-only');self.assertEqual(thread['approvalPolicy'],'never');self.assertEqual(thread['dynamicTools'][0]['name'],'claims')
        turn=next(e for e in sent if e.get('method')=='turn/start')['params'];self.assertEqual(turn['input'][1],{'type':'image','url':'data:image/png;base64,synthetic-fixture'})
        response=next(e for e in sent if e.get('id')==12);self.assertIn('event:1',response['result']['contentItems'][0]['text'])
    def test_native_auth_failure_diagnostics_are_not_exposed(self):
        process=Process([{'id':1,'error':{'message':'secret-account-diagnostic'}}])
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'CODEX_HOME':folder}),patch.object(providers,'codex_executable',return_value='fixture'),patch.object(providers,'launch',return_value=process),patch.object(providers,'terminate'):
            with self.assertRaises(providers.ProviderError) as error:providers.codex({'model':'codex:fixture','system':'test','messages':[]},lambda _:None,None,threading.Event(),lambda _:None)
        self.assertNotIn('secret-account',str(error.exception))
    def test_claude_streaming_result_and_reported_cost(self):
        process=Process([{'type':'stream_event','event':{'delta':{'type':'text_delta','text':'Structured reply'}}},{'type':'result','is_error':False,'result':'Structured reply','usage':{'input_tokens':12},'total_cost_usd':0.012}])
        # Claude closes stdin after sending the turn; retain the fixture text for inspection.
        class Input(io.StringIO):
            def close(self):pass
        process.stdin=Input();output=[]
        with patch.object(providers.shutil,'which',return_value='fixture'),patch.object(providers,'launch',return_value=process) as launch,patch.object(providers,'terminate'):
            result=providers.claude({'model':'claude:fixture','messages':[],'images':[{'mime':'image/png','data':'synthetic-fixture'}],'system':'test','bridge':{'url':'http://127.0.0.1:1234','token':'fixture-only'}},output.append,None,threading.Event(),lambda _:None)
        self.assertEqual(output,['Structured reply']);self.assertEqual(result['cost'],0.012)
        argv=launch.call_args.args[0];self.assertIn('--strict-mcp-config',argv);self.assertIn('--tools',argv);self.assertNotIn('--dangerously-skip-permissions',argv)
        self.assertIn('--input-format',argv);self.assertEqual(json.loads(process.stdin.getvalue())['message']['content'][1]['source']['data'],'synthetic-fixture')
    def test_malformed_native_stream_and_pre_cancelled_turn(self):
        process=Process([]);process.stdout=io.StringIO('invalid-json\n')
        with self.assertRaises(providers.ProviderError):list(providers.lines(process,threading.Event(),1))
        cancel=threading.Event();cancel.set()
        with self.assertRaisesRegex(providers.ProviderError,'cancelled'):list(providers.lines(Process([{}]),cancel,1))
