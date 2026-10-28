"""Exercise real electron-updater download/hash verification against an isolated loopback release feed. Never installs."""
from pathlib import Path
import base64
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
import subprocess
import threading
import tempfile
import sys
ROOT=Path(__file__).resolve().parents[1]

def main():
    installer=ROOT/'desktop/dist/Research-OS-Setup-1.3.0-x64.exe'
    if not installer.is_file():raise ValueError('Build the installer first.')
    with installer.open('rb') as stream:digest=base64.b64encode(hashlib.file_digest(stream,'sha512').digest()).decode()
    corrupt='--corrupt' in sys.argv
    if corrupt:digest=base64.b64encode(bytes(64)).decode()
    manifest=f'version: 9.9.9\nfiles:\n  - url: installer.exe\n    sha512: {digest}\n    size: {installer.stat().st_size}\npath: installer.exe\nsha512: {digest}\nreleaseDate: 2026-10-28T00:00:00.000Z\n'
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            if self.path.split('?')[0]=='/latest.yml':
                raw=manifest.encode();self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
            elif self.path.split('?')[0]=='/installer.exe':
                self.send_response(200);self.send_header('Content-Length',str(installer.stat().st_size));self.end_headers()
                with installer.open('rb') as stream:
                    while block:=stream.read(1024*1024):self.wfile.write(block)
            else:self.send_error(404)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
    folder=Path(tempfile.mkdtemp(prefix='updater-smoke-',dir=ROOT/'.desktop-fixtures'))
    profile=folder/'profile';profile.mkdir(exist_ok=True)
    env=dict(os.environ,ROS_NO_VAULT='1',ROS_HOME=str(folder),ROS_DESKTOP_SMOKE='1',ROS_DESKTOP_PROFILE=str(profile),ROS_UPDATE_TEST_URL=f'http://127.0.0.1:{server.server_port}/',APPDATA=str(profile),LOCALAPPDATA=str(profile),TEMP=str(ROOT/'.desktop-fixtures/tmp'),TMP=str(ROOT/'.desktop-fixtures/tmp'))
    env.pop('ELECTRON_RUN_AS_NODE',None)
    try:
        with (folder/'process.log').open('w',encoding='utf-8') as log:
            process=subprocess.Popen([str(ROOT/'desktop/dist/win-unpacked/Research OS.exe')],env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
            try:code=process.wait(timeout=100)
            except subprocess.TimeoutExpired:
                subprocess.run(['taskkill','/pid',str(process.pid),'/T','/F'],capture_output=True);process.kill();process.wait();code=124
        result=json.loads((folder/'updater-smoke.json').read_text()) if (folder/'updater-smoke.json').exists() else {'state':'failed'}
        result.update(exit=code,installer_sha512=digest,installation_performed=False)
        (ROOT/('docs/desktop-rebuild/updater-corrupt-smoke.json' if corrupt else 'docs/desktop-rebuild/updater-smoke.json')).write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2));return 0 if code==0 and (result['state']=='ready' if not corrupt else result['state']=='unavailable' and 'checksum mismatch' in (folder/'process.log').read_text(encoding='utf-8').lower()) else 1
    finally:server.shutdown();server.server_close()
if __name__=='__main__':raise SystemExit(main())
