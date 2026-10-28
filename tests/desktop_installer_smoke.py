"""Install, launch and uninstall only an isolated workspace copy; preserve application data."""
from pathlib import Path
import json
import os
import subprocess
import tempfile
import time
import winreg
import argparse
import hashlib
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]

def existing_install():
    for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
        try:key=winreg.OpenKey(hive,r'Software\Microsoft\Windows\CurrentVersion\Uninstall')
        except FileNotFoundError:continue
        with key:
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    with winreg.OpenKey(key,winreg.EnumKey(key,i)) as app:
                        if winreg.QueryValueEx(app,'DisplayName')[0]=='Research OS':return True
                except OSError:pass
    return False

def run(argv,env,log,timeout=120):
    process=subprocess.Popen(argv,env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
    try:return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        subprocess.run(['taskkill','/pid',str(process.pid),'/T','/F'],capture_output=True);process.kill();process.wait();raise

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upgrade-from',type=Path,help='Previous installer to install first in the same isolated destination')
    args=parser.parse_args()
    if existing_install():raise ValueError('Existing Research OS installation found; isolated test must not replace it.')
    fixtures=(ROOT/'.desktop-fixtures').resolve()
    folder=Path(tempfile.mkdtemp(prefix='installer-',dir=fixtures)).resolve();target=(folder/'application').resolve()
    if not target.is_relative_to(fixtures):raise ValueError('Install target escapes workspace fixtures.')
    home=folder/'record';home.mkdir();(home/'preserve.txt').write_text('Installer must preserve records.')
    profile=folder/'profile';profile.mkdir()
    env=dict(os.environ,ROS_NO_VAULT='1',ROS_HOME=str(home),ROS_DESKTOP_SMOKE='1',ROS_DESKTOP_PROFILE=str(profile),APPDATA=str(profile),LOCALAPPDATA=str(profile))
    env.pop('ELECTRON_RUN_AS_NODE',None)
    version=json.loads((ROOT/'desktop/package.json').read_text(encoding='utf-8'))['version']
    installer=ROOT/f'desktop/dist/Research-OS-Setup-{version}-x64.exe'
    previous=args.upgrade_from
    if previous is not None:
        previous=previous.resolve(strict=True)
        if previous==installer.resolve():raise ValueError('Upgrade baseline must be a previous installer.')
    with installer.open('rb') as stream:installer_sha256=hashlib.file_digest(stream,'sha256').hexdigest()
    with (folder/'install.log').open('w',encoding='utf-8') as log:
        previous_exit=None
        if previous:
            previous_exit=run([str(previous),'/S','/D='+str(target)],env,log)
            if previous_exit:raise ValueError('Previous installer exit '+str(previous_exit))
        # Persist representative organization and source membership data before replacement.
        record=home/'projects'/'upgrade-fixture';record.mkdir(parents=True)
        preserved={
            record/'record.json':json.dumps({'title':'Renamed Ω workspace','role':'user'}),
            record/'events.jsonl':json.dumps({'id':'fixture:organization','ts':'2026-10-28T00:00:00Z','type':'organization.renamed','subject':'course:fixture','data':{'title':'Quantum computing Ω'}})+'\n',
            record/'graph'/'nodes.jsonl':json.dumps({'id':'source:upgrade-fixture','type':'source','title':'Preserved lecture Ω','path':str(folder/'materials'/'lecture.md')})+'\n',
            folder/'materials'/'lecture.md':'# Original lecture Ω\n\nPreserve this source and its stable record reference.\n',
            profile/'organization-preferences.json':json.dumps({'course':'Quantum computing Ω','session':'Teleportation'})}
        for file,text in preserved.items():
            file.parent.mkdir(parents=True,exist_ok=True)
            file.write_text(text,encoding='utf-8')
        before={str(file.relative_to(folder)):hashlib.sha256(file.read_bytes()).hexdigest() for file in preserved}
        code=run([str(installer),'/S','/D='+str(target)],env,log)
        if code!=0:raise ValueError('Installer exit '+str(code))
        executable=target/'Research OS.exe';uninstaller=target/'Uninstall Research OS.exe'
        if not executable.is_file() or not uninstaller.is_file():raise ValueError('Installer did not create executable/uninstaller.')
        if not (target/'resources/app-update.yml').is_file():raise ValueError('Updater feed configuration missing.')
        try:
            launch=run([str(executable)],env,log,60)
            page=json.loads((home/'desktop-smoke.json').read_text(encoding='utf-8'))
            if launch or page['overflow']:raise ValueError('Installed application smoke failed.')
        finally:
            # The target was resolved and confined before installation. Invoke only its own uninstaller.
            removed=run([str(uninstaller),'/S'],env,log)
        deadline=time.monotonic()+20
        while executable.exists() and time.monotonic()<deadline:time.sleep(.2)
        after={str(file.relative_to(folder)):hashlib.sha256(file.read_bytes()).hexdigest() if file.exists() else None for file in preserved}
        result={'version':version,'installer_sha256':installer_sha256,'tested_at':datetime.now(timezone.utc).isoformat(),'installer_exit':code,'application_exit':launch,'uninstaller_exit':removed,'page':page,'records_preserved':(home/'preserve.txt').read_text()=='Installer must preserve records.','organization_and_sources_preserved':before==after,'preserved_hashes':after,'installed_executable_removed':not executable.exists(),'upgrade_from':previous.name if previous else None,'previous_installer_exit':previous_exit,'fixture':str(folder)}
        (ROOT/'docs/desktop-rebuild/installer-smoke.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result,indent=2));return 0 if removed==0 and result['records_preserved'] and result['organization_and_sources_preserved'] and result['installed_executable_removed'] else 1
if __name__=='__main__':raise SystemExit(main())
