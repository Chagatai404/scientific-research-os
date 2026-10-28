"""Portable, bounded verification. Uses only disposable storage and fixture providers."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
STEPS={
 'python':([sys.executable,'-m','unittest','discover','-s','tests','-p','test_*.py'],900),
 'frontend-tests':(['npm','--prefix','frontend','test'],180),
 'typecheck':(['npm','--prefix','frontend','run','typecheck'],120),
 'frontend-build':(['npm','--prefix','frontend','run','build'],240),
 'legacy-browser':(['node','tests/ros-portal-browser.cjs'],180),
 'workspace-browser':(['node','tests/ros-workspace-browser.cjs'],180),
 'usability-browser':(['node','tests/ros-desktop-usability.cjs'],300),
 'desktop-browser':(['node','tests/ros-desktop-browser.cjs'],180),
 'workspace-benchmark':([sys.executable,'tests/bench_workspace.py'],600),
 'desktop-lifecycle':(['npm','--prefix','desktop','test'],120),
}
def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--only',help='comma-separated focused checks; the report is explicitly partial')
 args=parser.parse_args();names=args.only.split(',') if args.only else list(STEPS)
 if any(n not in STEPS for n in names):parser.error('unknown check name')
 os.chdir(ROOT);env=dict(os.environ)
 temp=ROOT/'.desktop-fixtures'/'tmp';temp.mkdir(parents=True,exist_ok=True)
 env.update(ROS_NO_VAULT='1',ROS_HOME=str(ROOT/'.desktop-fixtures'/'gate-home'),TEMP=str(temp),TMP=str(temp),PYTHON=sys.executable,PYTHONUTF8='1')
 env['PYTHONPATH']=str(ROOT)+os.pathsep+str(ROOT/'.desktop-build/python-packages')+os.pathsep+env.get('PYTHONPATH','')
 env.setdefault('ROS_PLAYWRIGHT',str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'))
 if os.name=='nt':env.setdefault('ROS_BROWSER',r'C:\Program Files\Google\Chrome\Application\chrome.exe')
 output=ROOT/'.desktop-build';output.mkdir(exist_ok=True)
 started_at=datetime.now(timezone.utc).isoformat()
 results=[]
 for name in names:
  argv,timeout=STEPS[name];start=time.monotonic();timed_out=False
  if os.name=='nt' and argv[0]=='npm':argv=['cmd.exe','/d','/c',*argv]
  with (output/(name+'-gate.log')).open('w',encoding='utf-8') as log:
   process=subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT,env=env,**({'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {'start_new_session':True}))
   try:code=process.wait(timeout=timeout)
   except (subprocess.TimeoutExpired,KeyboardInterrupt):
    timed_out=True
    if os.name=='nt':subprocess.run(['taskkill','/pid',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    else:
     import signal
     os.killpg(process.pid,signal.SIGTERM)
    process.kill();process.wait();code=124
    log.write('\nVerification interrupted or timed out; no pass inferred.\n')
  results.append({'name':name,'exit':code,'seconds':round(time.monotonic()-start,3),'timed_out':timed_out})
  report={'complete_gate':not bool(args.only),'required_checks':list(STEPS),'started_at':started_at,'updated_at':datetime.now(timezone.utc).isoformat(),'desktop_version':json.loads((ROOT/'desktop/package.json').read_text(encoding='utf-8'))['version'],'checks':results}
  (output/'gate-results.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
  print(name+': exit '+str(code),flush=True)
 return 1 if any(r['exit'] for r in results) else 0
if __name__=='__main__':raise SystemExit(main())
