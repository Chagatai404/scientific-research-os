import {useState} from 'react';
import {href, readWorkspace, workHref} from './api';
import type {WorkspaceGroup, WorkspaceOverview as Overview, WorkspaceWork} from './contracts';
import {useResource} from './hooks';
import {Notice} from './ui';

export const refKey = (row: WorkspaceWork) => JSON.stringify(row.ref);
export type DistinctWork = WorkspaceWork & {alternates: WorkspaceWork[]};
const folderOf = (row: WorkspaceWork) => (row.path || '').replaceAll(String.fromCharCode(92), '/');
/** Two rows show one file only when a recorded content hash, or the same registered source and path, says so.
 *  Equal names or titles alone never merge; the other representation stays reachable as an alternate. */
const fileKey = (row: WorkspaceWork) => row.source_hash ? 'hash:' + row.source_hash : row.source && row.path ? `at:${row.source}|${folderOf(row).toLowerCase()}` : 'ref:' + refKey(row);
export function distinctWork(rows: WorkspaceWork[]): DistinctWork[] {
  const out = new Map<string, DistinctWork>(), seen = new Set<string>();
  for (const row of rows) {
    const exact = refKey(row); if (seen.has(exact)) continue; seen.add(exact);
    const key = fileKey(row), first = out.get(key);
    if (first) first.alternates.push(row); else out.set(key, {...row, alternates: []});
  }
  return [...out.values()];
}
export function groupedWork(rows: WorkspaceWork[], group: WorkspaceGroup): [string, DistinctWork[]][] {
  const groups = new Map<string, DistinctWork[]>();
  for (const row of distinctWork(rows)) {
    const path = folderOf(row);
    const folder = path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : 'Top level';
    const label = group === 'handouts' ? ({lecture: 'Lecture notes', recitation: 'Recitations', chapter: 'Chapters'}[row.handout_kind || ''] || 'Other handouts')
      : group === 'sources' ? row.kind === 'material' ? `${row.owner_record} · ${row.source || 'Library'} · ${folder}` : row.kind === 'connection' ? 'Connected places' : 'Other sources' : 'All';
    groups.set(label, [...(groups.get(label) || []), row]);
  }
  return [...groups.entries()];
}

export function WorkspaceCollection({data, groups = ['sessions', 'sources', 'handouts', 'research', 'other']}: {data: Overview; groups?: WorkspaceGroup[]}) {
  const [query, setQuery] = useState('');
  return <><label>Find work<input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Search titles or filenames"/></label>
    {groups.map(group => <section key={group} aria-label={group} className="workspace-group"><h2>{group[0].toUpperCase() + group.slice(1)} <small>{distinctWork(data.groups[group]).length}</small></h2>
      {!data.groups[group].length && <p className="muted">No {group} yet.</p>}
      {groupedWork(data.groups[group].filter(row => `${row.title} ${row.path?.split(/[\\/]/).at(-1) || ''}`.toLowerCase().includes(query.toLowerCase())), group).map(([label, rows]) => <details key={label} open={group !== 'sources' || !!query}>
        <summary>{label} ({rows.length})</summary><ul className="entry-list">{rows.map(row => <li key={refKey(row)}><div className="workspace-work"><a href={workHref(row.ref, data.workspace_id)}><strong>{row.title}</strong><small>{[row.path?.split(/[\\/]/).at(-1), row.format, row.state || row.status].filter(Boolean).join(' · ')}</small></a>
          <details><summary>Details</summary><p>{row.owner_record} · {row.ref.entity_id}</p>{row.path && <p className="provenance-path">{row.path}</p>}{!!row.alternates.length && <><p className="muted">Also stored as {row.alternates.length} other representation{row.alternates.length === 1 ? '' : 's'} of this file:</p><ul className="alternates">{row.alternates.map(alt => <li key={refKey(alt)}><a href={workHref(alt.ref, data.workspace_id)}>{alt.owner_record} · {alt.path || alt.ref.entity_id}</a></li>)}</ul></>}</details>
          {['material', 'source', 'paper', 'handout'].includes(row.kind) && <span className="work-actions">{['learn', 'research'].map(view => <a key={view} href={href(view, '', data.workspace.record, '', {ws: data.workspace_id, ref: JSON.stringify(row.ref)})}>{view === 'learn' ? 'Study' : 'Investigate'}</a>)}</span>}</div></li>)}</ul></details>)}
    </section>)}
    {!!data.missing.length && <p className="notice" role="status">{data.missing.length} references are missing or changed. Select their current versions before continuing.</p>}</>;
}

export function WorkspaceOverview({record, workspaceId}: {record: string; workspaceId: string}) {
  const result = useResource(`workspace-overview:${record}:${workspaceId}`, signal => readWorkspace(record, workspaceId, signal), record);
  if (!result.data) return <Notice error={result.error} retry={result.retry}/>;
  const data = result.data;
  return <div className="workspace-overview"><div className="eyebrow">{data.workspace.kind}</div><h1>{data.workspace.title}</h1>
    <p className="lead muted">Your sessions, material and findings in one place.</p><div className="work-actions">{[['chat', 'Ask'], ['learn', 'Learn'], ['research', 'Research']].map(([view, label]) => <a className="button primary" key={view} href={href(view, '', data.workspace.record, '', {ws: workspaceId})}>{label}</a>)}</div>
    <WorkspaceCollection data={data}/></div>;
}
