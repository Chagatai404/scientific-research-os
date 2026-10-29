"""Bounded native smoke in disposable storage; never uses personal records."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import time
import tempfile
import hashlib
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dev', action='store_true')
    args = parser.parse_args()
    folder = Path(tempfile.mkdtemp(prefix='native-dev-' if args.dev else 'native-packaged-',dir=ROOT/'.desktop-fixtures'))
    folder.mkdir(parents=True, exist_ok=True)
    profile = folder / 'profile'
    profile.mkdir(exist_ok=True)
    env = dict(os.environ, ROS_HOME=str(folder), ROS_NO_VAULT='1', ROS_DESKTOP_SMOKE='1', PYTHONUTF8='1',
               ROS_DESKTOP_PROFILE=str(profile), APPDATA=str(profile), LOCALAPPDATA=str(profile), TEMP=str(ROOT/'.desktop-fixtures/tmp'), TMP=str(ROOT/'.desktop-fixtures/tmp'))
    env.pop('ELECTRON_RUN_AS_NODE', None)
    executable = ROOT / 'desktop' / ('node_modules/electron/dist/electron.exe' if args.dev else 'dist/win-unpacked/Research OS.exe')
    argv = [str(executable)] + ([str(ROOT/'desktop')] if args.dev else [])
    started = time.monotonic()
    with (folder/'process.log').open('w', encoding='utf-8') as log:
        process = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            code = process.wait(timeout=60)
        except subprocess.TimeoutExpired:
            subprocess.run(['taskkill','/pid',str(process.pid),'/T','/F'], capture_output=True)
            process.kill(); process.wait(); code = 124
    screenshot = folder/'desktop-smoke.png'
    with executable.open('rb') as stream: executable_sha256=hashlib.file_digest(stream,'sha256').hexdigest()
    result = {'exit':code, 'seconds':round(time.monotonic()-started,2), 'screenshot':str(screenshot) if screenshot.exists() else None,
              'executable_sha256':executable_sha256,'tested_at':datetime.now(timezone.utc).isoformat()}
    if (folder/'desktop-smoke.json').exists():
        result['page'] = json.loads((folder/'desktop-smoke.json').read_text(encoding='utf-8'))
    if (folder/'desktop-smoke-error.txt').exists():
        result['startup_error'] = (folder/'desktop-smoke-error.txt').read_text(encoding='utf-8')[:1500]  # why the app could not start, e.g. a module missing from app.asar
    (folder/'result.json').write_text(json.dumps(result,indent=2)+'\n', encoding='utf-8')
    if not args.dev:(ROOT/'docs/desktop-rebuild/packaged-smoke.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))
    return 0 if code == 0 and result['screenshot'] and not result.get('page',{}).get('overflow') else 1

if __name__ == '__main__':
    raise SystemExit(main())
