'use strict';
const fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..');
const lock=JSON.parse(fs.readFileSync(path.join(__dirname,'package-lock.json'),'utf8'));
const rows=['Research OS desktop — third-party notices','Exact versions/integrities: desktop/package-lock.json and desktop/requirements-build.txt.','Electron/Chromium notices accompany the installed distribution. Frontend notices accompany the bundled workspace.',''];
for(const [folder,entry] of Object.entries(lock.packages)){
 const location=path.join(__dirname,folder);
 if(!folder.startsWith('node_modules/')||entry.dev||!fs.existsSync(location))continue;
 const pkg=JSON.parse(fs.readFileSync(path.join(location,'package.json'),'utf8'));rows.push(`${pkg.name} ${pkg.version} — ${pkg.license||entry.license||'see metadata'}`);
 for(const name of fs.readdirSync(location))if(/^(?:licen[cs]e|copying)(?:[.-].*)?$/i.test(name)&&fs.statSync(path.join(location,name)).isFile())rows.push(fs.readFileSync(path.join(location,name),'utf8'));
}
function include(folder){
 if(!fs.existsSync(folder))throw new Error('Missing bundled dependency notices: '+folder);
 for(const entry of fs.readdirSync(folder,{withFileTypes:true})){
  const file=path.join(folder,entry.name);
  if(entry.isDirectory())include(file);else{rows.push(path.relative(root,file));rows.push(fs.readFileSync(file,'utf8'));}
 }
}
const packages=path.join(root,'.desktop-build/python-packages');
for(const prefix of ['pypdfium2-','pillow-']){
 const name=fs.readdirSync(packages).find(name=>name.startsWith(prefix)&&name.endsWith('.dist-info'));
 if(!name)throw new Error('Install desktop/requirements-build.txt before packaging.');
 include(path.join(packages,name,'licenses'));
}
const executable=process.env.ROS_PYTHON||require('node:child_process').spawnSync(process.platform==='win32'?'python':'python3',['-c','import sys;print(sys.executable)'],{encoding:'utf8',windowsHide:true}).stdout.trim();
const python=path.join(path.dirname(executable),'LICENSE.txt');
if(fs.existsSync(python))rows.push(fs.readFileSync(python,'utf8'));
fs.writeFileSync(path.join(__dirname,'THIRD_PARTY_NOTICES.txt'),rows.join('\n\n').split('\n').map(line=>line.trimEnd()).join('\n').trimEnd()+'\n','utf8');
