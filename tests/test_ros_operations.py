"""Real committed operation effects and human gates, using disposable code and metadata fixtures."""
import io
import base64
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ros import api, runtime
from ros.store import Record
from ros.lib import desktop_operations

class Operations(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.environment=patch.dict(os.environ,{'ROS_NO_VAULT':'1','ROS_HOME':self.temp.name});self.environment.start();self.addCleanup(self.environment.stop)
        self.rec=Record(Path(self.temp.name)/'record');self.addCleanup(self.rec.close);self.addCleanup(api.release)
    def stage(self,text='print(6*7)'):
        return api.call('compute_stage',self.rec,experiment='experiment:fixture',files={'main.py':text},argv=['python','main.py'])
    def approve(self):api.call('approve',self.rec,subject='experiment:fixture',decision='approved',by='Fixture Researcher')
    def test_no_execution_before_plan_and_permission_and_changed_code_invalidates_approval(self):
        self.stage()
        with self.assertRaisesRegex(ValueError,'human approval'):api.call('compute_request',self.rec,experiment='experiment:fixture',by='Person',reason='Test')
        self.approve();job=api.call('compute_request',self.rec,experiment='experiment:fixture',by='Person',reason='Trusted fixture')
        self.stage('print(43)')
        with self.assertRaisesRegex(ValueError,'Plan changed'):api.call('operation_start',self.rec,identifier=job['id'])
        self.assertEqual(api.call('operation_list',self.rec)[0]['state'],'queued')
    def test_real_compute_commits_output_hashes_and_manifest_without_mutating_staged_code(self):
        self.stage('from pathlib import Path\nPath("result.json").write_text("{\\"value\\":42}")\nprint(42)')
        self.approve();job=api.call('compute_request',self.rec,experiment='experiment:fixture',by='Person',reason='Trusted deterministic fixture')
        result=runtime.execute_operation(self.rec,job['id'])
        self.assertEqual(result['state'],'completed',result)
        self.assertIn('42',result['result']['output']);self.assertEqual(result['result']['manifest']['observed']['exit_code'],0)
        artifact=next(a for a in result['result']['artifacts'] if a['path']=='result.json');self.assertEqual(json.loads(artifact['text'])['value'],42)
        self.assertEqual(json.loads((self.rec.root/'operation-artifacts'/artifact['sha256']).read_text())['value'],42)
        self.assertEqual(runtime.execute_operation(self.rec,job['id'])['state'],'completed')
    def test_metadata_search_records_candidates_without_claiming_verification(self):
        payload={'message':{'items':[{'title':['Fixture source'],'DOI':'10.0000/fixture','published':{'date-parts':[[2026]]}}]}}
        response=io.BytesIO(json.dumps(payload).encode())
        class Opener:
            def open(self,request,timeout):self.request=request;return response
        with patch.object(desktop_operations.urllib.request,'build_opener',return_value=Opener()):
            result=desktop_operations.search({'query':'public fixture','engine':'crossref','limit':2})
        self.assertTrue(result['ok']);self.assertEqual(result['candidates'][0]['verification_status'],'unverified');self.assertEqual(len(result['response_sha256']),64)
    def test_agent_tool_search_persists_actual_engine_result_and_receipt(self):
        from ros.lib import providers
        def provider(request,emit,tool,cancel,own):
            value=tool('literature_search',{'query':'public fixture'},'search-once')
            self.assertEqual(value['state'],'completed');emit('Discovery saved; scientific support is unverified.');return {}
        sent=api.call('workspace_chat_send',self.rec,text='Learn a public fixture topic',model='ollama:fixture',mode='learn')
        with patch.dict(providers.ADAPTERS,{'ollama':provider}),patch.object(runtime,'engine_process',return_value={'ok':True,'candidates':[{'title':'Fixture','verification_status':'unverified'}]}):runtime.execute(self.rec,sent,sent['_engine'])
        row=api.call('run_get',self.rec,run=sent['run']);self.assertEqual(row['state'],'completed');self.assertEqual(row['steps'][0]['tool'],'literature_search');self.assertEqual(api.call('operation_list',self.rec)[0]['state'],'completed')
    def test_transcription_review_preserves_exact_original_and_prior_drafts(self):
        root=Path(self.temp.name)/'scan';root.mkdir();original=root/'notes.txt';original.write_text('Original ambiguous notation',encoding='utf-8')
        source=api.call('source_register',self.rec,root=str(root),kind='folder')['id'];ref=api.call('source_capture',self.rec,source=source,path='notes.txt')
        draft=api.call('transcription_draft',self.rec,source=source,path='notes.txt',revision=ref['revision'],text='x [uncertain: exponent 2 or 3]')
        api.call('transcription_accept',self.rec,draft=draft['draft'],by='Researcher')
        rows=api.call('transcription_list',self.rec,source=source);self.assertTrue(rows[0]['reviewed']);self.assertIn('uncertain',rows[0]['text']);self.assertEqual(original.read_text(),'Original ambiguous notation')
    def test_local_vision_uses_only_a_verified_loopback_profile_and_retains_source_scope(self):
        root=Path(self.temp.name)/'image';root.mkdir();raw=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aP1sAAAAASUVORK5CYII=');(root/'scan.png').write_bytes(raw)
        source=api.call('source_register',self.rec,root=str(root),kind='folder')['id'];ref=api.call('source_capture',self.rec,source=source,path='scan.png')
        with self.assertRaises(ValueError):api.call('workspace_chat_send',self.rec,text='Transcribe faithfully',model='codex:gpt-6.1-sol',scope=[ref])
        api.call('provider_configure',self.rec,provider='ollama',endpoint='http://127.0.0.1:11434',model='fixture',vision=True)
        sent=api.call('workspace_chat_send',self.rec,text='Transcribe faithfully; retain uncertainty.',model='ollama:fixture',scope=[ref])
        self.assertEqual(base64.b64decode(sent['_engine']['images'][0]['data']),raw)
        runtime.execute(self.rec,sent,sent['_engine'],legacy_engine=lambda _: {'ok':True,'text':'x [uncertain exponent]'})
        message=api.call('workspace_chat',self.rec,conversation=sent['conversation'])['messages'][-1]
        self.assertEqual(message['scope'][0]['revision'],ref['revision']);self.assertEqual((root/'scan.png').read_bytes(),raw)
    @unittest.skipUnless(importlib.util.find_spec('pypdfium2'),'optional local PDF renderer')
    def test_pdf_pages_are_rendered_locally_with_explicit_page_scope(self):
        import pypdfium2
        from ros.lib import pdf_vision
        pdf=pypdfium2.PdfDocument.new();page=pdf.new_page(120,120);page.close();file=Path(self.temp.name)/'scan.pdf';pdf.save(str(file));pdf.close()
        raw=file.read_bytes();result=pdf_vision.render([{'mime':'application/pdf','data':base64.b64encode(raw).decode(),'revision':'fixture-revision'}])
        self.assertTrue(result['ok']);self.assertEqual(result['page_scope'][0]['included_pages'],[1]);self.assertEqual(result['images'][0]['mime'],'image/png');self.assertEqual(file.read_bytes(),raw)

    def test_cloud_media_needs_exact_single_use_permission_and_rechecks_destination(self):
        root=Path(self.temp.name)/'public-image';root.mkdir();(root/'scan.png').write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aP1sAAAAASUVORK5CYII='))
        source=api.call('source_register',self.rec,root=str(root),kind='folder',local_only=False)['id'];ref=api.call('source_capture',self.rec,source=source,path='scan.png')
        model='codex:fixture';api.call('provider_configure',self.rec,provider='codex',endpoint='',model='fixture',vision=True)
        with self.assertRaisesRegex(ValueError,'permission'):api.call('workspace_chat_send',self.rec,text='Synthetic image only',model=model,scope=[ref])
        grant=api.call('vision_permission',self.rec,source=source,path='scan.png',revision=ref['revision'],model=model)
        bound=dict(ref,visionPermission=grant['permission']);sent=api.call('workspace_chat_send',self.rec,text='Synthetic image only',model=model,scope=[bound])
        self.assertNotIn('_engine',api.external_result(sent));self.assertNotIn('visionPermission',json.dumps(api.call('workspace_chat',self.rec,conversation=sent['conversation'])))
        api.call('vision_dispatch_check',self.rec,permissions=[grant['permission']],request=sent['request'],model=model)
        with self.assertRaisesRegex(ValueError,'already been used'):api.call('workspace_chat_send',self.rec,text='Reuse denied',model=model,scope=[bound])
        api.call('provider_configure',self.rec,provider='codex',endpoint='',model='fixture',vision=True,context_limit=20000)
        with self.assertRaisesRegex(ValueError,'destination changed'):api.call('vision_dispatch_check',self.rec,permissions=[grant['permission']],request=sent['request'],model=model)
        private_root=Path(self.temp.name)/'private-image';private_root.mkdir();(private_root/'scan.png').write_bytes((root/'scan.png').read_bytes())
        private=api.call('source_register',self.rec,root=str(private_root),kind='folder')['id'];private_ref=api.call('source_capture',self.rec,source=private,path='scan.png')
        with self.assertRaisesRegex(ValueError,'Local-only'):api.call('vision_permission',self.rec,source=private,path='scan.png',revision=private_ref['revision'],model=model)

    def test_one_shot_claim_refreshes_a_second_record_instance(self):
        from ros.store import make_event
        other=Record(self.rec.root);self.addCleanup(other.close)
        event=make_event('fixture.claim','fixture',{},id='claim:fixture')
        with other.reading():
            other.events(type='fixture.claim')
            self.assertTrue(self.rec.append_once(event));self.assertFalse(other.append_once(event))
        self.assertEqual(len(other.events(type='fixture.claim')),1)

    def test_source_directory_pages_refresh_names_and_ignore_rules(self):
        root=Path(self.temp.name)/'files';root.mkdir()
        for name in ('a.txt','b.txt','c.txt'):(root/name).write_text(name)
        source=api.call('source_register',self.rec,root=str(root),kind='folder')['id']
        self.assertEqual([r['name'] for r in api.call('source_children',self.rec,source=source,offset=1,limit=1)],['b.txt'])
        (root/'.gitignore').write_text('b.txt\n')
        self.assertEqual([r['name'] for r in api.call('source_children',self.rec,source=source)],['a.txt','c.txt'])
        (root/'d.txt').write_text('new')
        self.assertEqual([r['name'] for r in api.call('source_children',self.rec,source=source)],['a.txt','c.txt','d.txt'])
