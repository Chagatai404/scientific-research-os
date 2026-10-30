import {useState, type FormEvent} from 'react';
import {call, human} from './api';
import {useResource} from './hooks';

interface Status {repo: string | null; git: boolean; branch?: string; changed?: string[]}

/** The repository a Code session works in. Choosing it is the person's act (a human tool): it decides where an agent with a
 * shell may edit files and run commands. */
export function RepoPicker({record}: {record: string}) {
  const status = useResource('workbench:' + record, signal => call<Status>('workbench_status', {}, record, false, signal), record);
  const [folder, setFolder] = useState(''), [editing, setEditing] = useState(false), [error, setError] = useState('');
  async function choose(event: FormEvent) {
    event.preventDefault(); setError('');
    try {await human('record_repo', {folder: folder.trim()}, record); setEditing(false); status.retry();} catch (e) {setError((e as Error).message);}
  }
  const value = status.data;
  return <div className="repo-picker">{value?.repo && !editing ? <p className="muted">Claude Code or Codex will work in <code>{value.repo}</code>{value.git ? <> on <strong>{value.branch}</strong>{value.changed?.length ? ` · ${value.changed.length} files already changed` : ''}</> : ' (not a git repository: changes are recorded without a file list)'}. <button type="button" onClick={() => {setFolder(value.repo || ''); setEditing(true);}}>Change folder</button></p>
    : <form onSubmit={choose}><label htmlFor="repo-folder">Your project’s code folder<small>The agent edits files and runs commands only here. It never pushes or rewrites history.</small></label><input id="repo-folder" value={folder} onChange={e => setFolder(e.target.value)} placeholder="C:\Users\you\projects\ams-ecal-qml" required /><button type="submit">Use this folder</button></form>}
    {(error || status.error) && <p className="notice error" role="alert">{error || status.error}</p>}</div>;
}
