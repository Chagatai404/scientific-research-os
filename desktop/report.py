"""Collect delivery evidence only after every required gate and package smoke passes."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib
import base64
import json
import platform
import re
import shutil

ROOT=Path(__file__).resolve().parents[1]
DOC=ROOT/'docs/desktop-rebuild'

def read(name):return json.loads((DOC/name).read_text(encoding='utf-8'))

def digest(path,kind='sha256'):
    with path.open('rb') as stream:return hashlib.file_digest(stream,kind).hexdigest()

def tap_count(path):
    match=re.search(r'^(?:#|ℹ) tests (\d+)\s*$',path.read_text(encoding='utf-8'),re.M)
    return match[1] if match else 'see raw log'

def main():
    version=json.loads((ROOT/'desktop/package.json').read_text(encoding='utf-8'))['version']
    gate=json.loads((ROOT/'.desktop-build/gate-results.json').read_text(encoding='utf-8'))
    required=gate.get('required_checks',[])
    assert gate['complete_gate'] and required and set(required)=={row['name'] for row in gate['checks']} and all(row['exit']==0 for row in gate['checks']), 'Full gate has not passed.'
    assert gate.get('desktop_version')==version,'Gate belongs to a different desktop version.'
    native=read('packaged-smoke.json');frozen=read('frozen-smoke.json');installed=read('installer-smoke.json');update=read('updater-smoke.json');corrupt=read('updater-corrupt-smoke.json');performance=read('native-performance.json');sources=read('source-performance.json')
    assert native['exit']==0 and not native['page']['overflow'] and frozen['compute_ok'] and frozen['bundled_python']
    assert installed['installer_exit']==installed['application_exit']==installed['uninstaller_exit']==0 and installed['records_preserved'] and installed['installed_executable_removed']
    assert update['exit']==0 and update['state']=='ready' and corrupt['exit']==0 and corrupt['state']=='unavailable'
    assert installed['version']==update['version']==corrupt['version']==version
    assert installed['organization_and_sources_preserved']
    assert native['executable_sha256']==digest(ROOT/'desktop/dist/win-unpacked/Research OS.exe'),'Native smoke is stale.'
    assert frozen['backend_sha256']==digest(ROOT/'desktop/dist/win-unpacked/resources/backend/research-os-backend/research-os-backend.exe'),'Frozen smoke is stale.'
    installer_name=f'Research-OS-Setup-{version}-x64.exe'
    assert all(row['installer_sha256']==digest(ROOT/'desktop/dist'/installer_name) for row in (installed,update,corrupt)),'Installer evidence is stale.'
    assert sources['files']==10000 and performance['cycles']==50
    evidence=DOC/'evidence';evidence.mkdir(exist_ok=True)
    shutil.copy2(ROOT/'.desktop-build/gate-results.json',evidence/'gate-results.json')
    for step in gate['checks']:shutil.copy2(ROOT/'.desktop-build'/(step['name']+'-gate.log'),evidence/(step['name']+'-gate.log'))
    artifacts=[]
    for name in (installer_name,installer_name+'.blockmap','latest.yml'):
        file=ROOT/'desktop/dist'/name
        with file.open('rb') as stream:sha256=hashlib.file_digest(stream,'sha256').hexdigest()
        with file.open('rb') as stream:sha512=hashlib.file_digest(stream,'sha512').hexdigest()
        artifacts.append({'file':str(file.relative_to(ROOT)).replace('\\','/'),'bytes':file.stat().st_size,'sha256':sha256,'sha512':sha512})
    manifest={'version':version,'artifacts':artifacts,'source_branch':'agent/codex/desktop-rebuild','implementation_baseline':'2f00d3b','signed':False,'published':False,'tools':frozen['cli_tools'],'full_gate_pass':True,'installer_tested':True,'upgrade_tested':bool(installed.get('upgrade_from'))}
    metadata=(ROOT/'desktop/dist/latest.yml').read_text(encoding='utf-8')
    assert re.search(r'^version: '+re.escape(version)+r'\s*$',metadata,re.M) and base64.b64encode(bytes.fromhex(artifacts[0]['sha512'])).decode() in metadata and installer_name in metadata, 'Shipped updater metadata does not match installer.'
    (DOC/'ARTIFACT.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    python=(evidence/'python-gate.log').read_text(encoding='utf-8');count=re.search(r'Ran (\d+) tests in ([\d.]+)s',python)
    skipped=re.search(r'OK \(skipped=(\d+)\)',python)
    vault_text='Live vault migration evidence has not been collected in this report; fixture success does not prove personal-data migration.'
    if (DOC/'vault-reconciliation.json').is_file():vault_text='Live vault reconciliation was explicitly authorized and performed separately from isolated tests. Its backup, counts, conflicts, preservation and rollback evidence is recorded in [vault-reconciliation.json](vault-reconciliation.json).'
    upgrade_text=('The previous installer `'+installed['upgrade_from']+'` was installed before replacement. Named organization and profile data remained byte-identical through upgrade and uninstall.') if installed.get('upgrade_from') else 'Upgrade from an earlier installer has not been exercised by this run.'
    bundle=ROOT/'ros/portal/workspace';assets=bundle/'assets';initial=sum(p.stat().st_size for p in assets.glob('index-*') if p.suffix in ('.js','.css'));total=sum(p.stat().st_size for p in bundle.rglob('*') if p.is_file())
    table='\n'.join('| '+row['name']+' | PASS | '+str(row['seconds'])+' s |' for row in gate['checks'])
    text=f'''# Desktop acceptance evidence

Verified {datetime.now(timezone(timedelta(hours=3))).isoformat(timespec='seconds')} (Europe/Istanbul). Windows {platform.release()} {platform.machine()}, Python {platform.python_version()}, Electron 43.8.4. Branch `agent/codex/desktop-rebuild`, usability baseline `2f00d3b`. No push, merge or public release.

## Deliverable and launch

Install [Research OS {version}](../../desktop/dist/{installer_name}). It includes Electron and the frozen backend, creates shortcuts, and preserves records on uninstall. The complete unpacked application is [Research OS.exe](../../desktop/dist/win-unpacked/Research%20OS.exe). Keep its adjacent resources. The installer is unsigned; no signing identity was supplied. ARTIFACT.json records final SHA-256/SHA-512 and byte sizes. The earlier installer and preview ZIP are superseded.

Installed copies check the public GitHub stable-release feed and download newer versions automatically. Settings shows progress and permits restart after active owned work finishes. Publication requires an explicit matching `desktop-v<version>` tag; no release was published in this session. Unpacked/development copies use manual replacement. Backend version {native['page']['version']} is retained for compatibility; desktop package version is {version}.

## Complete verification

`python desktop/verify.py` passed all **{len(required)}** configured checks on the final functional tree. Python: **{count[1]} tests, {skipped[1] if skipped else '0'} optional/platform skips**, {count[2]} s. Frontend: **{tap_count(evidence/'frontend-tests-gate.log')} tests**. Electron lifecycle/updater unit tests: **{tap_count(evidence/'desktop-lifecycle-gate.log')} tests**. Timing budgets and browser coverage were retained, adapting equivalent user interactions where the interface changed.

| Check | Result | Duration |
|---|---|---|
{table}

Raw logs and machine-readable results: [evidence/gate-results.json](evidence/gate-results.json). The legacy portal remains a compatibility test; desktop workflows use the native workspace. Browser evidence covers source privacy/Unicode/revisions, real bounded computation and retained output, learning/questions/assistance, draft/dictation races, record isolation/SSE, graph lenses/navigation, sanitized math/GFM/diagrams, dark/light, seven widths (320–1920), 1280×720 and 200% zoom. Screenshots are under screenshots/; the computation artifact view and native launch were visually inspected.

## Packaged application and installer

- Native packaged GUI: exit 0, protocol `{native['page']['protocol']}`, no horizontal overflow. [packaged-smoke.json](packaged-smoke.json) points to the actual screenshot. The earlier `0x80000003` reproduced only in the restricted launch environment; native launch outside it passes.
- Frozen backend with Python removed from PATH: **{frozen['cli_tools']} tools**, local PDF-to-PNG rendering and actual bundled-Python computation pass. [frozen-smoke.json](frozen-smoke.json).
- Actual NSIS **install → installed app launch → uninstall** passes in a guarded workspace destination. The installed executable is removed and an independent record sentinel is preserved. Existing Research OS installs are protected by a registry preflight. [installer-smoke.json](installer-smoke.json).
- {upgrade_text}
- Real electron-updater downloaded the installer to 100% and reached ready against a loopback future-release fixture. A corrupt SHA-512 was rejected. No test installed an update. [positive](updater-smoke.json), [corrupt](updater-corrupt-smoke.json).

## Performance measurements

The observations below are historical unless separately rerun and explicitly attributed to the redesigned build. They are retained for comparison and do not certify new graph frame-rate or latency targets. Artifact smoke evidence above is matched against the current binary and installer hashes.

Native release automation: three launches, p50 **{performance['launch_p50_ms']} ms**, p95 **{performance['launch_p95_ms']} ms**; 50 navigation cycles, probe p50 **{performance['route_p50_ms']} ms**, p95 **{performance['route_p95_ms']} ms**. Navigation probes include a 120 ms settling interval and do not represent pure render time. These measurements do not meet the proposed 2 s warm-launch target; the observed cold maximum is slightly above 5 s. The navigation probe also exceeds 150 ms while including its fixed delay. They remain performance optimization limits, not hidden passes. Process/window/SSE counts and Electron/owned-backend memory are captured in [native-performance.json](native-performance.json). Small samples on one host do not establish a general latency or memory-leak bound; inspect warm-up and retained caches separately from model processes. The uncollected working-set run is preserved in native-performance-before-gc.json. Forced-GC observations retain the same DOM/window/stream counts and less than 1 MiB JavaScript-heap growth; allocator working set still warms over the run. A 1k-visible-node FPS stress test and provider first-token latency are not certified.

Explicit 10,000-file synthetic Markdown source index: listing **{sources['listing_seconds']} s**, indexing **{sources['index_seconds']} s**; indexed search cold **{sources['search_cold_ms']} ms**, warm p50 **{sources['search_warm_p50_ms']} ms**, p95 **{sources['search_warm_p95_ms']} ms**. [source-performance.json](source-performance.json). This fixture excludes PDF OCR and embeddings. Sparse/dense graph timings and bounded payloads are in the workspace benchmark log.

Bundled workspace assets: initial index JS+CSS **{initial:,} bytes**, total workspace **{total:,} bytes**, uncompressed including optional chunks/fonts/notices. Vite's >500 kB chunk warning remains visible; no budget or warning was disabled.

## Scope and limits

Automated tests use `ROS_NO_VAULT=1`, isolated records and synthetic content. {vault_text} No private media export, paid inference, model download or credential extraction is required by these verification scripts. Native Codex/Claude protocols and governed tool effects use deterministic fixtures; real logins, entitlements, rate limits, model scientific quality, GPU voice/animation, live uv/kernel and personal Obsidian launch are unverified deployment checks. Optional engines remain explicit dependencies. Windows x64 is the packaged acceptance target; macOS/Linux artifacts are not certified.

Cloud image/PDF transport requires individual human permission for the exact retained revision and configured destination, expires in ten minutes, and is consumed once. Destination changes are rechecked before dispatch. Local Only media is always blocked. PDF rendering is local and records its first-four-page scope. Transcription review preserves the original and prior drafts. Scientific plan approval, claim decisions, independent audits and waivers retain their original authority boundaries. Scratch computation uses local OS permissions and is not an OS sandbox.
'''
    (DOC/'ACCEPTANCE.md').write_text(text,encoding='utf-8')
    print('Delivery evidence collected; installer SHA-256 '+artifacts[0]['sha256'])

if __name__=='__main__':main()
