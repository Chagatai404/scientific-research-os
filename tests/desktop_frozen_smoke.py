"""Prove bundled CLI, PDF renderer and Python computation work without Python on PATH."""
from pathlib import Path
import base64
import json
import os
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.desktop-build/python-packages'))

def main():
    import pypdfium2
    folder=Path(tempfile.mkdtemp(prefix='frozen-',dir=ROOT/'.desktop-fixtures'))
    backend=ROOT/'desktop/dist/win-unpacked/resources/backend/research-os-backend/research-os-backend.exe'
    env=dict(os.environ,ROS_NO_VAULT='1',ROS_HOME=str(folder/'home'),PATH=str(Path(os.environ['SystemRoot'])/'System32'),PYTHONUTF8='1')
    def call(args,packet=None):
        value=subprocess.run([str(backend),'--worker',*args],input=json.dumps(packet) if packet else None,env=env,capture_output=True,text=True,encoding='utf-8',timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
        if value.returncode:raise ValueError(value.stdout+'\n'+value.stderr)
        return json.loads(value.stdout)
    tools=call(['cli','tools','--json'])
    pdf=pypdfium2.PdfDocument.new();page=pdf.new_page(120,120);page.close();file=folder/'fixture.pdf';pdf.save(str(file));pdf.close()
    rendered=call(['pdf-vision'],{'images':[{'mime':'application/pdf','data':base64.b64encode(file.read_bytes()).decode(),'revision':'synthetic-fixture'}]})
    assert rendered['ok'] and rendered['images'][0]['mime']=='image/png'
    result=call(['operation'],{'kind':'compute','packet':{'experiment':'experiment:frozen-fixture','digest':'synthetic-fixture','files':{'main.py':'from pathlib import Path\nPath("result.txt").write_text("42")\nprint(42)'},'argv':['python','main.py'],'timeout':15,'output_dir':str(folder/'output')}})
    assert result['ok'] and result['manifest']['observed']['bundled_python'] and '42' in result['output']
    report={'cli_tools':len(tools),'python_on_path':False,'pdf_page_scope':rendered['page_scope'],'compute_ok':result['ok'],'bundled_python':result['manifest']['observed']['bundled_python'],'artifact_count':len(result['artifacts'])}
    (ROOT/'docs/desktop-rebuild/frozen-smoke.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':main()
