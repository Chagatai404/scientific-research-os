import fs from 'node:fs';
import path from 'node:path';

const lock = JSON.parse(fs.readFileSync('package-lock.json', 'utf8'));
const notices = ['Research OS workspace — third-party notices', 'Exact dependency versions and integrity hashes: frontend/package-lock.json.', 'No LearnHarness source code or assets are included.', ''];
for (const [folder, entry] of Object.entries(lock.packages)) {
  if (!folder.startsWith('node_modules/') || entry.dev || !fs.existsSync(folder)) continue;
  const manifest = JSON.parse(fs.readFileSync(path.join(folder, 'package.json'), 'utf8'));
  notices.push(`${manifest.name} ${manifest.version} — ${manifest.license || entry.license || 'see package metadata'}`);
  const files = fs.readdirSync(folder).filter(file => /^(?:licen[cs]e|copying)(?:[.-].*)?$/i.test(file));
  for (const file of files) if (fs.statSync(path.join(folder, file)).isFile()) notices.push(fs.readFileSync(path.join(folder, file), 'utf8'));
  notices.push('');
}
fs.writeFileSync('../ros/portal/workspace/THIRD_PARTY_NOTICES.txt', notices.join('\n').split('\n').map(line => line.trimEnd()).join('\n').trimEnd() + '\n', 'utf8');
