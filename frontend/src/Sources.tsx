import {useEffect, useState, type FormEvent} from 'react';
import {call, href, human, preference, savePreference} from './api';
import {useResource} from './hooks';
import {RichText} from './Document';
import {Notice} from './ui';
import type {SourceConnection, SourceRef} from './desktop';
import {SourceTools} from './SourceTools';
import {Transcriptions} from './Transcriptions';

interface Preview {name: string; kind: string; text?: string; revision: string; currentRevision: string; changed: boolean; retained: boolean; localOnly: boolean}
export function Sources({record}: {record: string}) {
  const connections = useResource('sources:' + record, signal => call<SourceConnection[]>('source_list', {}, record, false, signal), record);
  const [selected, setSelected] = useState(''), [path, setPath] = useState(''), [kind, setKind] = useState('file'), [root, setRoot] = useState(''), [localOnly, setLocalOnly] = useState(true);
  const [preview, setPreview] = useState<Preview|null>(null), [status, setStatus] = useState(''), [busy, setBusy] = useState(false), [start, setStart] = useState(1), [end, setEnd] = useState(40);
  const active = connections.data?.find(c => c.id === selected);
  const listing = useResource(`source-children:${record}:${selected}:${path}`, signal => selected ? call<{name: string; path: string; directory: boolean}[]>('source_children', {source: selected, path}, record, false, signal) : Promise.resolve([]));
  useEffect(() => {setSelected(''); setPath(''); setPreview(null);}, [record]);
  async function connect(event?: FormEvent) {
    event?.preventDefault(); setBusy(true); setStatus('');
    try {
      const picked = window.researchDesktop ? await window.researchDesktop.pickSource(kind, record, localOnly) : await human<SourceConnection>('source_register', {root, kind, local_only: localOnly}, record);
      const source = Array.isArray(picked) ? picked[0] : picked;
      if (source) {connections.retry(); setSelected(source.id); setPath(''); setPreview(null); setRoot(''); setStatus('Connected. Files remain on your computer.'); window.dispatchEvent(new Event('ros:records-changed'));}
    } catch (e) {setStatus((e as Error).message);} finally {setBusy(false);}
  }
  async function open(file: string, revision?: string) {setBusy(true); setStatus(''); try {setPreview(await call<Preview>('source_preview', {source: selected, path: file, ...(revision ? {revision} : {})}, record)); setPath(file);} catch (e) {setStatus((e as Error).message);} finally {setBusy(false);}}
  async function attach() {
    setBusy(true); try {const ref = await call<SourceRef>('source_capture', {source: selected, path, start_line: start, end_line: end}, record, true); savePreference('attachment:' + record, JSON.stringify(ref)); setStatus('Passage retained. It is ready to attach to your next message.');} catch (e) {setStatus((e as Error).message);} finally {setBusy(false);}
  }
  async function addToLibrary() {
    setBusy(true); setStatus('');
    try {
      const out = await human<{added: number; existing: number}>('library_add', {source: selected}, record);
      setStatus(out.added ? `Added ${out.added} items to your Library. They are being read now.` : `Everything here is already in your Library (${out.existing} items).`);
      window.dispatchEvent(new Event('ros:library-changed')); window.dispatchEvent(new Event('ros:records-changed'));
    } catch (e) {setStatus((e as Error).message);} finally {setBusy(false);}
  }
  async function change(action: string) {try {await human('source_change', {source: selected, action}, record); connections.retry(); if (action === 'remove') {setSelected(''); setPreview(null);}} catch (e) {setStatus((e as Error).message);}}
  const media = '/source-media?' + new URLSearchParams({source: selected, path, record});
  return <div className="sources-page"><h2>Connected places</h2>
    {<><p className="muted">These are the places your library reads from. Connecting never changes your files. Select a passage separately to include it in a conversation.</p>
    <form className="source-connect" onSubmit={connect}><label>Source Kind<select value={kind} onChange={e => setKind(e.target.value)}><option value="file">File</option><option value="folder">Folder</option><option value="codebase">Codebase</option><option value="vault">Obsidian Vault</option></select></label>
      {!window.researchDesktop && <label>Approved Local Path<input value={root} onChange={e => setRoot(e.target.value)} placeholder="C:/research/paper.md" required /></label>}
      <label className="check-label"><input type="checkbox" checked={localOnly} onChange={e => setLocalOnly(e.target.checked)}/> Keep Content Local</label><button disabled={busy} className="primary">{window.researchDesktop ? 'Choose & Connect' : 'Connect Path'}</button></form>
    {status && <p className="notice" role="status">{status}</p>}
    {!connections.data ? <Notice error={connections.error} retry={connections.retry}/> : !connections.data.length ? <section className="empty-state"><h2>Connect Your Workspace</h2><p>Add a vault, project or source above. No model is needed to read and explore.</p></section> : <div className="source-layout"><nav aria-label="Source connections"><ul className="entry-list">{connections.data.map(c => <li key={c.id}><button aria-pressed={selected === c.id} onClick={() => {setSelected(c.id); setPath(''); setPreview(null);}}><span><strong>{c.label}</strong><small>{c.kind} · {c.status} · {c.localOnly ? 'Local Only' : 'Cloud Context Allowed'}</small></span></button></li>)}</ul></nav>
      <section className="source-reader">{active && <><div className="section-title"><h2>{active.label}</h2><div className="actions"><button disabled={busy || active.status !== 'ready'} onClick={addToLibrary}>Add everything to Library</button><button onClick={() => change(active.status === 'paused' ? 'resume' : 'pause')}>{active.status === 'paused' ? 'Resume' : 'Pause'}</button><button onClick={() => change('remove')}>Disconnect</button></div></div>
        <SourceTools key={active.id} source={active} path={path} record={record} onOpen={open}/>
        {active.kind === 'file' && !preview && <button onClick={() => open('')}>Preview File</button>}
        {active.kind !== 'file' && <><button onClick={() => {setPath(path.split('/').slice(0, -1).join('/')); setPreview(null);}}>↑ Parent Folder</button><span className="source-path">{path || '/'}</span></>}
        {!preview && <ul className="entry-list">{listing.data?.map(file => <li key={file.path}><button onClick={() => file.directory ? (setPath(file.path), setPreview(null)) : open(file.path)}>{file.directory ? '▸ ' : '▤ '}{file.name}</button></li>)}</ul>}
        {listing.error && !preview && <p role="alert">{listing.error}</p>}
        {preview && <><div className="section-title"><h3>{preview.name}</h3>{window.researchDesktop && <div className="actions"><button onClick={() => window.researchDesktop!.openSource(selected, path, record, false).catch(e => setStatus(e.message))}>Open Original</button><button onClick={() => window.researchDesktop!.openSource(selected, path, record, true).catch(e => setStatus(e.message))}>Reveal</button>{active.kind === 'vault' && path.toLowerCase().endsWith('.md') && <button onClick={() => window.researchDesktop!.openSource(selected,path,record,false,true).catch(e=>setStatus(e.message))}>Open in Obsidian</button>}</div>}</div>
          <p className="muted">Revision {preview.revision.slice(0, 12)}{preview.changed ? ' · Source changed' : ''}</p>
          {preview.kind === 'text' ? <><div className="passage-controls"><label>First Line<input type="number" min="1" value={start} onChange={e => setStart(Number(e.target.value))}/></label><label>Last Line<input type="number" min={start} max={start + 300} value={end} onChange={e => setEnd(Number(e.target.value))}/></label><button disabled={busy} onClick={attach}>Attach Passage</button><a href={href('overview', '', record)}>Open Conversation</a></div>{/\.(md|txt)$/.test(preview.name) ? <RichText text={preview.text || ''} record={record}/> : <pre className="source-code">{preview.text}</pre>}</> : /\.pdf$/i.test(preview.name) ? <><object className="source-pdf" data={media} type="application/pdf"><a href={media}>Open PDF</a></object><a href={media} download>Download Original PDF</a></> : /\.(png|jpg|jpeg|webp|gif)$/i.test(preview.name) ? <img className="source-image" src={media} alt={preview.name}/> : <p>This format is preserved. Open the original with its local application.</p>}
          {preview.kind!=='text'&&<p><button disabled={busy} onClick={attach}>Attach Image or PDF</button> <a href={href('overview','',record)}>Open Conversation</a></p>}{preview.name.toLowerCase().endsWith('.pdf')&&<p className="muted">Local PDF vision includes up to the first four pages. Split a longer scan into selected page images for further pages.</p>}<Transcriptions key={selected+path} record={record} source={selected} path={path} revision={preview.revision}/><p><button onClick={() => {setPreview(null); setPath(path.split('/').slice(0, -1).join('/'));}}>Close Preview</button></p></>}
        {active.kind === 'vault' && <p><button onClick={async () => {try {await human('source_use_vault', {source:selected}, record);setStatus('Vault selected for projection. Sync remains an explicit operation.');}catch(e){setStatus((e as Error).message);}}}>Use for Research OS Sync</button> <a href={href('settings', '', record, 'vault-connection')}>Vault Sync & Conflicts</a></p>}
      </>}</section></div>}</>}
  </div>;
}
