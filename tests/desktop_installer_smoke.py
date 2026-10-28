"""Install, launch and uninstall only an isolated workspace copy; preserve application data."""
from pathlib import Path
import json
import os
import subprocess
import tempfile
import time
import winreg

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
    if existing_install():raise ValueError('Existing Research OS installation found; isolated test must not replace it.')
    fixtures=(ROOT/'.desktop-fixtures').resolve()
    folder=Path(tempfile.mkdtemp(prefix='installer-',dir=fixtures)).resolve();target=(folder/'application').resolve()
    if not target.is_relative_to(fixtures):raise ValueError('Install target escapes workspace fixtures.')
    home=folder/'record';home.mkdir();(home/'preserve.txt').write_text('Installer must preserve records.')
    profile=folder/'profile';profile.mkdir()
    env=dict(os.environ,ROS_NO_VAULT='1',ROS_HOME=str(home),ROS_DESKTOP_SMOKE='1',ROS_DESKTOP_PROFILE=str(profile),APPDATA=str(profile),LOCALAPPDATA=str(profile))
    env.pop('ELECTRON_RUN_AS_NODE',None)
    installer=ROOT/'desktop/dist/Research-OS-Setup-1.3.0-x64.exe'
    with (folder/'install.log').open('w',encoding='utf-8') as log:
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
        result={'installer_exit':code,'application_exit':launch,'uninstaller_exit':removed,'page':page,'records_preserved':(home/'preserve.txt').read_text()=='Installer must preserve records.','installed_executable_removed':not executable.exists(),'fixture':str(folder)}
        (ROOT/'docs/desktop-rebuild/installer-smoke.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(result,indent=2));return 0 if removed==0 and result['records_preserved'] and result['installed_executable_removed'] else 1
if __name__=='__main__':raise SystemExit(main())
