import {useEffect, useRef, useState} from 'react';
import {human} from './api';
import {changed} from './SessionsPane';

/** The workspace name in the top strip: click it to rename in place, Enter to save, Escape to cancel. */
export function InlineTitle({title, record}: {title: string; record: string}) {
  const [editing, setEditing] = useState(false), [value, setValue] = useState(title), [error, setError] = useState('');
  const input = useRef<HTMLInputElement>(null), saving = useRef(false);
  useEffect(() => {if (!editing) setValue(title);}, [title, editing]);
  useEffect(() => {if (editing) input.current?.select();}, [editing]);
  async function save() {
    const name = value.trim();
    if (saving.current) return;
    if (!name || name === title) {setEditing(false); setError(''); return;}
    saving.current = true;
    try {await human('workspace_rename', {title: name}, record); changed(); setEditing(false); setError('');}
    catch (e) {setError((e as Error).message);}
    finally {saving.current = false;}
  }
  if (!editing) return <button type="button" className="inline-title" title="Click to rename this workspace" aria-label={`Rename workspace ${title}`} onClick={() => setEditing(true)}>{title}</button>;
  return <span className="inline-title-edit"><input ref={input} aria-label="Workspace name" value={value} maxLength={200} autoComplete="off" onChange={e => setValue(e.target.value)} onBlur={save}
    onKeyDown={e => {if (e.key === 'Enter') {e.preventDefault(); void save();} else if (e.key === 'Escape') {e.preventDefault(); setValue(title); setEditing(false); setError('');}}} />
    {error && <small role="alert" className="inline-title-error">{error}</small>}</span>;
}
