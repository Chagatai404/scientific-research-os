"""Desktop contracts: durable effects, source privacy, revision-bound authority and interruption.

All providers are deterministic fixtures. No personal records, vaults or inference.
"""
import http.client
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from ros import api, runtime, serve
from ros.store import Record
from ros.lib import providers
from support_human import session_headers, decision

class Desktop(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = patch.dict(os.environ, {'ROS_HOME': str(self.root), 'ROS_NO_VAULT': '1'}); env.start(); self.addCleanup(env.stop)
        self.rec = Record(self.root/'projects'/'test'); self.addCleanup(self.rec.close); self.addCleanup(api.release)
        self.source = self.root/'sources'; self.source.mkdir(); (self.source/'paper.md').write_text('# Paper\nA precise result.\nUncertainty matters.\n', encoding='utf-8')
    def connect(self, **args): return api.call('source_register',self.rec,root=str(self.source),kind='folder',**args)
    def test_native_location_is_resolved_only_inside_the_registered_vault(self):
        connection=api.call('source_register',self.rec,root=str(self.source),kind='vault')
        result=api.call('source_location',self.rec,source=connection['id'],path='paper.md')
        self.assertEqual(result['kind'],'vault')
        self.assertEqual(Path(result['path']),(self.source/'paper.md').resolve())
        with self.assertRaises(ValueError):api.call('source_location',self.rec,source=connection['id'],path='../outside.md')
    def test_registration_is_read_only_deduplicated_and_not_an_import(self):
        before = list(self.source.iterdir()); a=self.connect(); b=self.connect()
        self.assertEqual(a['id'],b['id']); self.assertEqual(a['access'],'read'); self.assertTrue(a['localOnly'])
        self.assertEqual(before,list(self.source.iterdir())); self.assertEqual(self.rec.nodes(),[])
        self.assertEqual(len(self.rec.events(type='source.registered')),1)
    def test_snapshot_and_locator_survive_source_changes_and_disconnect_preserves_file(self):
        source=self.connect()['id']; ref=api.call('source_capture',self.rec,source=source,path='paper.md',start_line=2,end_line=2)
        (self.source/'paper.md').write_text('Changed source',encoding='utf-8')
        old=api.call('source_preview',self.rec,source=source,path='paper.md',revision=ref['revision'])
        self.assertTrue(old['changed']); self.assertTrue(old['retained']); self.assertIn('precise result',old['text']); self.assertEqual(ref['locator']['startLine'],2)
        api.call('source_change',self.rec,source=source,action='remove'); self.assertTrue((self.source/'paper.md').exists())
        with self.assertRaises(KeyError): api.call('source_preview',self.rec,source=source,path='paper.md')
    def test_traversal_secret_binary_and_links_are_refused(self):
        source=self.connect()['id']; (self.source/'.env').write_text('not a real secret'); (self.source/'binary.md').write_bytes(b'abc\0def')
        for path in ('../outside.txt','/etc/passwd','C:/outside','folder\\file','.env','binary.md'):
            with self.subTest(path=path),self.assertRaises((ValueError,FileNotFoundError)): api.call('source_preview',self.rec,source=source,path=path)
        try: (self.source/'outside').symlink_to(self.root,target_is_directory=True)
        except OSError: return # Windows without symlink privilege; junction checks run in browser fixture separately
        with self.assertRaises(ValueError): api.call('source_children',self.rec,source=source,path='outside')
    def test_incremental_index_and_missing_file_search(self):
        source=self.connect()['id']; a=api.call('source_index_batch',self.rec,source=source,paths=['paper.md'],generation='a'); b=api.call('source_index_batch',self.rec,source=source,paths=['paper.md'],generation='b')
        self.assertEqual(a['indexed'],1); self.assertEqual(b['unchanged'],1)
        hits=api.call('source_search',self.rec,q='precise',source=source); self.assertEqual(hits[0]['relativePath'],'paper.md'); self.assertTrue(hits[0]['localOnly'])
        (self.source/'paper.md').unlink(); self.assertEqual(api.call('source_search',self.rec,q='precise',source=source),[])
    def test_turn_idempotency_and_explicit_terminal_state(self):
        a=api.call('workspace_chat_send',self.rec,text='Hello',model='ollama:fixture',key='turn-one'); b=api.call('workspace_chat_send',self.rec,text='Hello',model='ollama:fixture',key='turn-one')
        self.assertEqual(a['request'],b['request']); self.assertTrue(b['duplicate']); self.assertEqual(len(self.rec.events(type='conversation.message')),1)
        runtime.execute(self.rec,a,a['_engine'],legacy_engine=lambda _: {'ok':True,'text':'A fixture reply'})
        row=api.call('run_get',self.rec,run=a['run']); self.assertEqual(row['state'],'completed'); self.assertEqual(row['output'],'A fixture reply')
        with self.assertRaises(ValueError): api.call('run_transition',self.rec,run=a['run'],state='running')
    def test_restart_marks_unfinished_runs_interrupted_without_retry(self):
        sent=api.call('workspace_chat_send',self.rec,text='Hello',model='ollama:fixture'); runtime.recover(self.rec)
        self.assertEqual(api.call('run_get',self.rec,run=sent['run'])['state'],'interrupted')
        self.assertEqual(api.call('workspace_chat',self.rec,conversation=sent['conversation'])['pending'],[])
        self.assertEqual(len(self.rec.events(type='conversation.message')),1)
    def test_source_and_derived_conversation_never_cross_into_cloud(self):
        source=self.connect()['id']; ref=api.call('source_capture',self.rec,source=source,path='paper.md')
        with self.assertRaisesRegex(ValueError,'local-only'): api.call('workspace_chat_send',self.rec,text='Read',model='codex:gpt-6.1-sol',scope=[ref])
        sent=api.call('workspace_chat_send',self.rec,text='Read',model='ollama:fixture',scope=[ref]); runtime.execute(self.rec,sent,sent['_engine'],legacy_engine=lambda _: {'ok':True,'text':'Derived private summary'})
        with self.assertRaisesRegex(ValueError,'local-only'): api.call('workspace_chat_send',self.rec,text='Continue',model='codex:gpt-6.1-sol',conversation=sent['conversation'])
    def test_tool_effects_are_committed_and_human_tools_are_unavailable(self):
        called=[]
        def fake(request,emit,tool,cancel,own):
            names={t['name'] for t in request['tools']}; self.assertTrue(names); self.assertNotIn('approve',names); self.assertNotIn('waive',names); self.assertNotIn('verdict',names)
            value=tool('claims',{},'operation-1'); self.assertEqual(tool('claims',{},'operation-1'),value); called.append(value)
            with self.assertRaises(ValueError): tool('approve',{},'operation-2')
            emit('Saved result'); return {}
        sent=api.call('workspace_chat_send',self.rec,text='Inspect this question',model='ollama:fixture')
        with patch.dict(providers.ADAPTERS,{'ollama':fake}): runtime.execute(self.rec,sent,sent['_engine'])
        run=api.call('run_get',self.rec,run=sent['run']); self.assertEqual(run['state'],'completed'); self.assertEqual(len(run['steps']),1); self.assertEqual(len(called),1)
    def test_director_task_record_routes_committed_effects(self):
        other=Record(self.root/'projects'/'other');self.addCleanup(other.close)
        other.put_node('project:other','project',title='Target record')
        sent=api.call('workspace_chat_send',self.rec,text='Study routing',model='ollama:fixture',mode='learn')
        original=api.call
        def routed(name,rec,**args):
            if name=='work':return {'use_record':'other','task':{'id':'task:fixture'}}
            return original(name,rec,**args)
        def fake(request,emit,tool,cancel,own):
            tool('work',{'by':'fixture'},'claim-task')
            tool('add_node',{'id':'capability:routed','type':'capability','data':{'title':'Routed outcome'}},'save-outcome')
            emit('Persisted in the task record');return {}
        with patch.object(api,'call',side_effect=routed),patch.dict(providers.ADAPTERS,{'ollama':fake}):runtime.execute(self.rec,sent,sent['_engine'])
        run=original('run_get',self.rec,run=sent['run'])
        self.assertEqual(run['state'],'completed',run)
        self.assertIsNotNone(other.node('capability:routed'))
        self.assertIsNone(self.rec.node('capability:routed'))
        self.assertEqual(original('run_get',self.rec,run=sent['run'])['state'],'completed')
    def test_execution_limits_are_validated_and_queue_is_bounded(self):
        saved=api.call('execution_configure',self.rec,values={'tool_steps':2,'queue':1})
        self.assertEqual(saved['tool_steps'],2)
        with self.assertRaises(ValueError):api.call('execution_configure',self.rec,values={'deadline':0})
        api.call('workspace_chat_send',self.rec,text='First',model='ollama:fixture')
        with self.assertRaisesRegex(ValueError,'queue is full'):api.call('workspace_chat_send',self.rec,text='Second',model='ollama:fixture')
    def test_committed_notebook_must_match_exact_permission_before_environment_starts(self):
        from ros.lib import notebook_trace as trace
        copy=self.root/'copy';copy.mkdir();(copy/'a.ipynb').write_text('{"cells":[]}',encoding='utf-8')
        entry={'approved_notebooks':[{'id':'a','path':'a.ipynb','approved_by':'Researcher','revision':'0'*64}]}
        original=self.root/'notebooks';original.mkdir();(original/'a.ipynb').write_text('{"cells":[]}',encoding='utf-8')
        with patch.object(trace,'prepare_copy',return_value={'copy':copy,'parent':self.root/'scratch'}),patch.object(trace,'remove_copy'),patch.object(trace,'sync_environment') as sync:
            with self.assertRaisesRegex(trace.TraceError,'authorized revision'):trace.trace_notebook(original,entry,'a',run=True)
            sync.assert_not_called()
    def test_linked_private_derivations_cannot_leak_through_cloud_director_context(self):
        api.call('link',self.rec,user_wide=True)
        other=Record(self.root/'projects'/'linked');self.addCleanup(other.close)
        api.call('link',other,user='test',project='project:linked',title='Private linked project')
        api.call('source_protect_derived',other,origin='fixture',run='run:fixture')
        with self.assertRaisesRegex(ValueError,'linked record'):
            api.call('workspace_chat_send',self.rec,text='Summarize my projects',model='codex:gpt-6.1-sol')
    def test_local_derivations_block_future_cloud_context(self):
        api.call('source_protect_derived',self.rec,origin='fixture',run='run:fixture')
        with self.assertRaisesRegex(ValueError,'local-only derived'):
            api.call('workspace_chat_send',self.rec,text='Read this record',model='codex:gpt-6.1-sol')
    def test_cancel_stops_actual_owned_worker_and_preserves_partial_output(self):
        started=threading.Event()
        def fake(request,emit,tool,cancel,own):
            emit('Partial'); started.set(); cancel.wait(2); raise providers.ProviderError('cancelled')
        sent=api.call('workspace_chat_send',self.rec,text='Wait',model='ollama:fixture')
        with patch.dict(providers.ADAPTERS,{'ollama':fake}):
            worker=threading.Thread(target=runtime.execute,args=(self.rec,sent,sent['_engine'])); worker.start(); self.assertTrue(started.wait(2)); runtime.cancel(self.rec,sent['run']); worker.join(3)
        self.assertFalse(worker.is_alive()); self.assertEqual(api.call('run_get',self.rec,run=sent['run'])['state'],'cancelled')
    def test_browser_authority_is_bound_to_subject_revision(self):
        self.rec.put_node('experiment:e','experiment',title='Plan',plan={'scope':'first'})
        server=serve.start(self.rec,0); self.addCleanup(server.server_close); self.addCleanup(server.shutdown); port=server.server_port
        def post(path,packet,headers):
            connection=http.client.HTTPConnection('127.0.0.1',port,timeout=5); connection.request('POST',path,json.dumps(packet),headers); response=connection.getresponse(); body=json.loads(response.read()); connection.close(); return response.status,body
        params={'subject':'experiment:e','decision':'approved','by':'Researcher'}
        status,_=post('/api/approve',params,{'X-ROS':'1','Sec-Fetch-Site':'same-origin'}); self.assertEqual(status,403)
        headers=session_headers(port); packet={'name':'approve','args':params}
        status,body=post('/services/human-prepare',packet,headers); self.assertEqual(status,200)
        self.rec.put_node('experiment:e','experiment',title='Changed',plan={'scope':'second'})
        status,_=post('/services/human-commit',{**packet,'approval':body['result']['approval']},headers); self.assertEqual(status,400); self.assertEqual(self.rec.events(type='approval'),[])
        self.assertEqual(decision(port,'approve',params)[0],200)
    def test_local_endpoint_configuration_is_loopback_only_and_not_inference(self):
        for endpoint in ('https://cloud.example/v1','http://user:password@localhost/v1','file:///private'):
            with self.assertRaises(ValueError): api.call('provider_configure',self.rec,provider='compatible',endpoint=endpoint,model='fixture')
        result=api.call('provider_configure',self.rec,provider='compatible',endpoint='http://127.0.0.1:1234/v1',model='fixture')
        self.assertFalse(result['tools']); self.assertEqual(len(api.call('provider_profiles',self.rec)),1)
    def test_external_records_require_explicit_registration_and_keep_distinct_identity(self):
        repo=self.root/'other repo'; repo.mkdir(); external=Record(repo/'.ros'); external.put_node('project:external','project',title='External'); external.close(); pool=serve.Pool(self.rec); self.addCleanup(pool.close)
        with self.assertRaises(ValueError): pool.get(str(repo/'.ros'))
        api.call('source_register',self.rec,root=str(repo),kind='codebase'); key=next(iter(pool.external())); opened=pool.get(key)
        self.assertEqual(opened.root.resolve(),(repo/'.ros').resolve()); self.assertNotEqual(key,self.rec.root.name)

class ProviderStreams(unittest.TestCase):
    def test_text_only_local_stream_and_malformed_output(self):
        for provider,event in (('ollama',{'message':{'content':'hello'},'done':True}),('compatible',{'choices':[{'delta':{'content':'hello'},'finish_reason':'stop'}]})):
            data=json.dumps(event).encode()+b'\n'; out=[]
            with patch.object(providers,'local_open',return_value=io.BytesIO(data)):
                providers.local({'model':provider+':fixture','messages':[],'system':'test'},out.append,lambda *a: self.fail('text-only model used a tool'),threading.Event(),lambda _:None)
            self.assertEqual(''.join(out),'hello')
        with patch.object(providers,'local_open',return_value=io.BytesIO(b'bad-json\n')):
            with self.assertRaises(providers.ProviderError): providers.local({'model':'ollama:fixture','messages':[],'system':'test'},lambda _:None,None,threading.Event(),lambda _:None)

class FakeProcess:
    def __init__(self, lines=()): self.stdin=io.StringIO(); self.stdout=iter(lines); self.returncode=1
    def poll(self): return self.returncode

class ProviderLaunch(unittest.TestCase):
    """The installed CLIs are reached through npm .cmd shims; those must start, and Codex must accept our arguments."""
    def run_adapter(self, adapter, request, lines=()):
        launched=[]
        def launch(argv, cwd): launched.append(argv); return FakeProcess(lines)
        with patch.object(providers,'launch',launch):
            try: adapter(dict(request,system='s',messages=[],deadline=2),lambda _:None,None,threading.Event(),lambda _:None)
            except providers.ProviderError as exc: error=exc
            else: error=None
        return launched[0], error
    @unittest.skipUnless(os.name=='nt','npm .cmd shims exist only on Windows')
    def test_an_npm_shim_resolves_to_the_native_binary_or_the_node_script(self):
        for package,entry,native in (('@anthropic-ai/claude-code','bin/claude.exe',True),('@anthropic-ai/claude-code','cli.js',False),('@openai/codex','bin/codex.js',False)):
            with tempfile.TemporaryDirectory() as folder:
                root=Path(folder); name=package.split('/')[1].replace('-code',''); shim=root/(name+'.cmd'); shim.write_text('@echo off')
                target=root/'node_modules'/package/entry; target.parent.mkdir(parents=True); target.write_text('')
                with patch.object(providers.subprocess,'Popen') as popen, patch.object(providers.shutil,'which',return_value='node.exe'):
                    providers.launch([str(shim),'--print'],folder)
                argv=popen.call_args.args[0]
                self.assertEqual(argv, [str(target),'--print'] if native else ['node.exe',str(target),'--print'])
        with tempfile.TemporaryDirectory() as folder:
            shim=Path(folder)/'claude.cmd'; shim.write_text('@echo off')
            with self.assertRaises(providers.ProviderError): providers.launch([str(shim)],folder)
    def test_codex_overrides_name_servers_and_plugins_the_way_codex_parses_them(self):
        with tempfile.TemporaryDirectory() as home:
            (Path(home)/'config.toml').write_text('[mcp_servers.my-server]\nurl="x"\n[mcp_servers."odd.name"]\nurl="x"\n[plugins."pdf@runtime"]\nenabled=true\n',encoding='utf-8')
            with patch.dict(os.environ,{'CODEX_HOME':home}), patch.object(providers,'codex_executable',return_value='codex'):
                argv,error=self.run_adapter(providers.codex,{'model':'codex:gpt-6.1-sol'})
        overrides=[argv[i+1] for i,value in enumerate(argv) if value=='-c']
        self.assertIn('mcp_servers.my-server.enabled=false',overrides); self.assertIn('plugins.pdf@runtime.enabled=false',overrides)
        # A quoted segment is read literally and a `mcp_servers={}` reset empties every transport: both make Codex exit with "invalid transport".
        self.assertFalse([o for o in overrides if '"' in o or o.startswith('mcp_servers=')])
        self.assertFalse([o for o in overrides if 'odd.name' in o])
        self.assertIn('terminal turn event',str(error)); self.assertIn('exit 1',str(error))
    def test_claude_gets_an_effort_only_for_models_that_take_one(self):
        result=json.dumps({'type':'result','result':'ok'})+'\n'
        for model,effort,expected in (('claude:sonnet','high',['--effort','high']),('claude:opus','max',['--effort','max']),('claude:haiku','high',None)):
            with patch.object(providers.shutil,'which',return_value='claude'):
                argv,error=self.run_adapter(providers.claude,{'model':model,'effort':effort},[result])
            self.assertIsNone(error)
            if expected: self.assertEqual(argv[argv.index('--effort'):argv.index('--effort')+2],expected)
            else: self.assertNotIn('--effort',argv)

if __name__=='__main__': unittest.main()
