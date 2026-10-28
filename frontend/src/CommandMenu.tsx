import {useEffect, useState} from 'react';
import {href} from './api';
import {Modal, useOverlay} from './overlay';

const commands = [['overview', 'Home'], ['learn', 'Learn'], ['research', 'Research'], ['library', 'Library'], ['graph', 'Graph'], ['activity', 'Activity'], ['settings', 'Settings'], ['tools', 'Developer tools']];

export function CommandMenu({record}: {record: string}) {
  const palette = useOverlay('modal', 'commands');
  const [query, setQuery] = useState('');
  const {show} = palette;
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.isComposing || !(e.ctrlKey || e.metaKey) || !['k', 'p'].includes(e.key.toLowerCase())) return;
      e.preventDefault(); setQuery(e.key.toLowerCase() === 'p' ? 'Library' : ''); show();
    };
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  }, [show]);
  return <Modal id="commands" title="Go to">{close => {
    const found = commands.filter(([, name]) => name.toLowerCase().includes(query.toLowerCase()));
    return <><label>Find a page<input value={query} onChange={e => setQuery(e.target.value)} autoComplete="off"/></label>
      <nav aria-label="Pages">{found.map(([view, name]) => <a key={view} href={href(view, '', record)} onClick={close}>{name}</a>)}{!found.length && <p className="muted">No page matches.</p>}</nav>
      <div className="modal-actions"><button onClick={close} aria-label="Close commands">Close</button></div></>;
  }}</Modal>;
}
