"""Optional bounded retrieval and explicit trusted-code execution workers. No domain imports."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from . import computational_manifest

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args):raise ValueError('Retrieval redirect refused; inspect the source independently.')

def search(packet):
    query=urllib.parse.urlencode({'query':packet['query'],'rows':packet['limit']})
    url='https://api.crossref.org/works?'+query
    if packet['engine']=='europepmc':url='https://www.ebi.ac.uk/europepmc/webservices/rest/search?'+urllib.parse.urlencode({'query':packet['query'],'pageSize':packet['limit'],'format':'json'})
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    request=urllib.request.Request(url,headers={'User-Agent':'ResearchOS/1.3 scholarly-metadata','Accept':'application/json'})
    with opener.open(request,timeout=15) as response:raw=response.read(2*1024*1024+1)
    if len(raw)>2*1024*1024:raise ValueError('Metadata response exceeds 2 MB.')
    data=json.loads(raw);rows=data.get('message',{}).get('items',[]) if packet['engine']=='crossref' else data.get('resultList',{}).get('result',[])
    candidates=[]
    for row in rows[:packet['limit']]:
        title=row.get('title') or ['Untitled'];title=title[0] if isinstance(title,list) else title
        doi=row.get('DOI') or row.get('doi');identity='https://doi.org/'+doi if doi else 'https://europepmc.org/article/'+str(row.get('source','MED'))+'/'+str(row.get('id',''))
        candidates.append({'title':title,'doi':doi,'source_url':identity,'access':'metadata','verification_status':'unverified','year':row.get('pubYear') or row.get('published',{}).get('date-parts',[[None]])[0][0],'abstract':row.get('abstract','')[:6000]})
    return {'ok':True,'query':packet['query'],'retrieved_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'request_url':url,'response_sha256':hashlib.sha256(raw).hexdigest(),'candidates':candidates,'limitation':'Metadata is discovery, not proof that full text was read or a claim verified.'}

def compute(packet):
    started=time.monotonic();command=packet['argv'];executable=shutil.which(command[0])
    bundled=not executable and command[0]=='python' and getattr(sys,'frozen',False)
    if bundled:executable=sys.executable
    if not executable:raise ValueError('Install '+command[0]+' to run this approved experiment.')
    environment={k:v for k,v in os.environ.items() if k.upper() in ('PATH','SYSTEMROOT','WINDIR','TEMP','TMP','HOME','USERPROFILE','LANG','PYTHONUTF8') or k.startswith('G4')}
    environment['PYTHONUTF8']='1'
    with tempfile.TemporaryDirectory(prefix='ros-approved-compute-') as folder:
        root=Path(folder)
        for path,text in packet['files'].items():
            target=(root/path).resolve()
            if not target.is_relative_to(root):raise ValueError('Staged path escaped scratch directory.')
            target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text,encoding='utf-8')
        for row in packet.get('input_files',[]):
            original=Path(row['snapshot']);raw=original.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=row['revision']:raise ValueError('Input snapshot integrity failure.')
            target=root/'inputs'/row['name'];target.parent.mkdir(exist_ok=True);target.write_bytes(raw)
        argv=[executable,'--worker','script',*command[1:]] if bundled else [executable,*command[1:]]
        if bundled and (command[1].startswith('-') or command[1] not in packet['files']):raise ValueError('Bundled Python runs an explicitly staged script file; use an installed interpreter for other command forms.')
        output_file=root/'operation-output.log';failure=None
        with output_file.open('wb') as stream:
            process=subprocess.Popen(argv,cwd=root,env=environment,stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,**({'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {'start_new_session':True}))
            while process.poll() is None:
                if time.monotonic()-started>packet['timeout'] or output_file.stat().st_size>1024*1024:
                    failure='Execution time or 1 MB output bound reached.'
                    if os.name=='nt':subprocess.run(['taskkill','/pid',str(process.pid),'/T','/F'],capture_output=True)
                    else:
                        import signal
                        os.killpg(process.pid,signal.SIGTERM)
                    process.kill();process.wait();break
                time.sleep(.05)
        with output_file.open('rb') as stream:
            stream.seek(max(0,output_file.stat().st_size-60000));output=stream.read(60000)
        artifacts=[];total=0
        for file in sorted(root.rglob('*')):
            if file==output_file or not file.is_file() or file.is_symlink() or not file.resolve().is_relative_to(root):continue
            if len(artifacts)>=50 or file.stat().st_size>2*1024*1024:continue
            raw=file.read_bytes();total+=len(raw)
            if total>8*1024*1024:break
            digest=hashlib.sha256(raw).hexdigest()
            if packet.get('output_dir'):
                destination=Path(packet['output_dir']);destination.mkdir(parents=True,exist_ok=True)
                blob=destination/digest
                if not blob.exists():
                    with blob.open('xb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
            artifacts.append({'path':file.relative_to(root).as_posix(),'sha256':digest,'bytes':len(raw),'text':raw.decode('utf-8',errors='replace')[:6000] if b'\0' not in raw else None})
        manifest=computational_manifest.create(packet['experiment'],observed={'exit_code':process.returncode,'seconds':round(time.monotonic()-started,3),'platform':platform.platform(),'executable':executable,'staged_digest':packet['digest'],'bundled_python':bundled},declared={'argv':command,'inputs':[{k:v for k,v in r.items() if k!='snapshot'} for r in packet.get('input_files',[])]},artifacts=[r['path'] for r in artifacts],reproduction_command=json.dumps(command),failure=failure or (None if process.returncode==0 else 'Process exited '+str(process.returncode)))
        return {'ok':process.returncode==0 and not failure,'manifest':manifest,'artifacts':artifacts,'output':output.decode('utf-8',errors='replace')[-60000:],'note':'Original files were not changed. Scratch execution is not an OS security sandbox.'}

def main():
    try:
        request=json.load(sys.stdin);result=search(request['packet']) if request['kind']=='literature' else compute(request['packet'])
    except Exception as exc:result={'ok':False,'error':str(exc)[:1500]}
    print(json.dumps(result,ensure_ascii=False));return 0 if result['ok'] else 1
if __name__=='__main__':raise SystemExit(main())
