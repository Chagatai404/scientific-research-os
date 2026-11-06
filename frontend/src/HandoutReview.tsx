import {useState} from 'react';
import {human} from './api';
import type {DocumentData} from './contracts';

/** What the person can do with a handout version: accept it into the vault, ask for changes, or take an unaccepted note out. */
export function HandoutReview({doc, record, onDone}: {doc: DocumentData; record: string; onDone?: () => void}) {
  const state = doc.acceptance?.state;
  const [text, setText] = useState(''), [message, setMessage] = useState(''), [busy, setBusy] = useState(false);
  if (doc.kind !== 'handout' || !state || state === 'draft') return null;
  async function act(name: string, args: Record<string, unknown>, done: string) {
    setBusy(true); setMessage('');
    try {await human(name, {handout: doc.id, ...args}, record); setMessage(done); setText(''); onDone?.();}
    catch (error) {setMessage((error as Error).message);}
    finally {setBusy(false);}
  }
  if (state === 'accepted') return <p className="notice" role="status">You accepted this version. It is in your vault.</p>;
  return <section className="notice handout-review" aria-label="Your decision on this handout">
    <h2>{state === 'in-vault' ? 'This note is in your vault, but you have not accepted it' : 'Ready for you to read'}</h2>
    <p>{state === 'in-vault' ? 'An agent wrote it before you could read it. Accept it to keep it, or take it out of your vault.' : 'Read it below. It reaches your Obsidian vault only when you accept this version.'}</p>
    <div className="actions">
      <button className="primary" disabled={busy} onClick={() => act('handout_accept', {source_hash: doc.source_hash}, 'Accepted. It is being written into your vault.')}>Accept into my vault</button>
      {doc.acceptance?.in_vault && <button disabled={busy} onClick={() => act('handout_take_out', {}, 'Taken out of your vault, unless you had edited it.')}>Take it out of my vault</button>}
    </div>
    <label>Ask for changes<textarea value={text} onChange={event => setText(event.target.value)} rows={3} placeholder="What should be different?" /></label>
    <button disabled={busy || !text.trim()} onClick={() => act('handout_request_changes', {text: text.trim()}, 'Sent. An agent will revise it and you will see the new version here.')}>Ask for changes</button>
    {message && <p role="status">{message}</p>}
  </section>;
}
