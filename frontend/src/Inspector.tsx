import {call, entityHref} from './api';
import type {DocumentData, Entity, Relation} from './contracts';
import {useResource} from './hooks';
import {Notice} from './ui';

export function Inspector({id, record, document: doc}: {id: string; record: string; document: DocumentData | null}) {
  const resource = useResource('references:' + record + ':' + id, signal => id ? call<Entity>('workspace_entity', {subject: id, limit: 40}, record, false, signal) : Promise.resolve(null));
  function links(rows: Relation[], incoming: boolean) {
    return rows.length ? <ul className="relation-list">{rows.map((r, i) => <li key={i}><span className="relation-type">{incoming ? '← ' : '→ '}{r.edge.type}</span>{r.missing ? <span>{r.title} <small>Missing target</small></span> : <a href={entityHref(r.id, r.record)}>{r.title}</a>}
      <small>{r.edge.provenance ? String(r.edge.provenance) : r.edge.source ? String(r.edge.source) : 'Provenance not recorded'}{r.edge.verified != null ? ' · ' + (r.edge.verified ? 'verified' : 'unverified') : ''}</small></li>)}</ul> : <p className="muted">No recorded links.</p>;
  }
  return <><div className="inspector-title">Context</div>{doc && <><h2>On this page</h2><nav aria-label="Document outline"><ol className="outline">{doc.sections.filter(s => s.text.trim()).map(s => <li key={s.id}><a href={entityHref(doc.id, record, 'section-' + s.id)}>{s.title}</a></li>)}{doc.sources.length > 0 && <li><a href={entityHref(doc.id, record, 'sources')}>Sources</a></li>}</ol></nav></>}
    {id ? !resource.data ? <Notice error={resource.error} retry={resource.retry} /> : <><h2>Referenced in</h2>{links(resource.data.incoming, true)}<h2>Connects to</h2>{links(resource.data.outgoing, false)}{resource.data.truncated > 0 && <p className="muted">{resource.data.truncated} more links. Open Graph to explore.</p>}
      <details className="identity"><summary>Identity</summary><code>{id}</code><p>{record || resource.data.record}</p></details></> : <div className="inspector-empty"><p>Follow the connections.</p><p className="muted">Open a document or concept to see its outline, sources and typed references here.</p><div className="connection-sketch" aria-hidden="true">○ ── ◉<br />│　　╱<br />○ ── ○</div></div>}
  </>;
}
