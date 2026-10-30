import {useEffect, useMemo, useRef, useState} from 'react';
import {call, entityHref, href, preference, savePreference} from './api';
import type {OrganizationMap} from './contracts';
import {useResource} from './hooks';
import {Menu} from './overlay';
import {Notice} from './ui';
import {CATEGORY_COLOR, mapLayout, safeCamera, zoomAt, type Camera, type MapPoint} from './graphLayout';

const CATEGORIES: [string, string][] = [['knowledge', 'Knowledge'], ['research', 'Research'], ['goals', 'Goals']];
// A decided claim or plan carries a ring in the colour of what was decided.
const DECISION_COLOR: Record<string, string> = {accepted: '#5cc28a', revise: '#e3b341', rejected: '#e0645c', retracted: '#e0645c'};
const clip = (text: string, n: number) => text.length > n ? text.slice(0, n - 1) + '…' : text;
const rgba = (hex: string, alpha: number) => `rgba(${parseInt(hex.slice(1, 3), 16)},${parseInt(hex.slice(3, 5), 16)},${parseInt(hex.slice(5, 7), 16)},${alpha})`;

export function Graph({focus, record, embedded = false}: {focus: string; record: string; embedded?: boolean}) {
  const [expand, setExpand] = useState(''), [only, setOnly] = useState(''), [selected, setSelected] = useState(''), [hover, setHover] = useState(''), [list, setList] = useState(false);
  const [camera, setCamera] = useState<Camera>({x: 0, y: 0, zoom: 1}), [size, setSize] = useState({width: 0, height: 0});
  const canvas = useRef<HTMLCanvasElement>(null), frame = useRef<HTMLDivElement>(null), initialized = useRef(''), selectionPanel = useRef<HTMLElement>(null), listPanel = useRef<HTMLElement>(null);
  const viewport = useRef({key: '', width: 0, height: 0}), drag = useRef<{x: number; y: number; ox: number; oy: number; moved: boolean} | null>(null);
  // Whether the person has moved the view since it was last fitted: a graph that grows is refitted only when they have not.
  const steered = useRef(false), seenCount = useRef(0);
  const result = useResource(`map:${record}:${expand}`, signal => call<OrganizationMap>('workspace_map', expand ? {expand} : {}, record, false, signal), record);
  const signature = JSON.stringify(result.data);
  const map = useMemo(() => result.data, [signature]);
  const points = useMemo<MapPoint[]>(() => map ? mapLayout(map) : [], [map]);
  const byId = useMemo(() => new Map(points.map(n => [n.id, n])), [points]);
  const cameraKey = 'camera:' + JSON.stringify([record, 'map', expand]);
  const chosen = byId.get(selected), shown = byId.get(hover || selected);
  const active = hover || selected;
  // What stays bright while something is focused: the item, where it is filed, what is filed in it, and what it is recorded to relate to.
  const related = useMemo(() => {
    const set = new Set<string>();
    if (!active || !map) return set;
    set.add(active);
    for (let id = byId.get(active)?.parent; id && !set.has(id); id = byId.get(id)?.parent) set.add(id);
    for (const e of map.edges) {if (e.src === active) set.add(e.dst); if (e.dst === active) set.add(e.src);}
    return set;
  }, [active, map, byId]);
  useEffect(() => {
    if (!frame.current) return;
    const observer = new ResizeObserver(([entry]) => setSize({width: entry.contentRect.width, height: entry.contentRect.height}));
    observer.observe(frame.current); return () => observer.disconnect();
  }, []);
  function fitted(): Camera {
    if (!points.length) return {x: size.width / 2, y: size.height / 2, zoom: 1};
    const minX = Math.min(...points.map(n => n.px)) - 40, maxX = Math.max(...points.map(n => n.px)) + 40, minY = Math.min(...points.map(n => n.py)) - 40, maxY = Math.max(...points.map(n => n.py)) + 40;
    const zoom = Math.max(.12, Math.min(1.6, (size.width - 32) / Math.max(1, maxX - minX), (size.height - 32) / Math.max(1, maxY - minY)));
    return {x: (size.width - (maxX + minX) * zoom) / 2, y: (size.height - (maxY + minY) * zoom) / 2, zoom};
  }
  useEffect(() => {
    if (!map || !size.width || !size.height) return;
    const previous = viewport.current;
    viewport.current = {key: cameraKey, ...size};
    if (initialized.current !== cameraKey) {initialized.current = cameraKey; setCamera(safeCamera(preference(cameraKey, '')) || fitted());}
    else if (previous.key === cameraKey && (previous.width !== size.width || previous.height !== size.height)) setCamera(c => ({...c, x: c.x + (size.width - previous.width) / 2, y: c.y + (size.height - previous.height) / 2}));
  }, [map, cameraKey, size.width, size.height]);
  useEffect(() => {if (initialized.current === cameraKey) savePreference(cameraKey, JSON.stringify(camera));}, [camera, cameraKey]);
  // Something added or removed (by you, an agent or a decision): refit when the view was not moved, and drop a selection that is gone.
  useEffect(() => {
    if (!map || !size.width) return;
    const count = points.length, before = seenCount.current; seenCount.current = count;
    if (before && count !== before && !steered.current) setCamera(fitted());
    if (selected && !byId.has(selected)) setSelected('');
    if (hover && !byId.has(hover)) setHover('');
  }, [points]);
  // A change made in this window (a delete, a move, a new course) redraws the map at once, without waiting for the live stream.
  useEffect(() => {const again = () => result.retry(); window.addEventListener('ros:organization-changed', again); return () => window.removeEventListener('ros:organization-changed', again);}, [result.retry]);
  useEffect(() => {setSelected(''); setHover(''); setList(false);}, [record]);
  useEffect(() => {if (focus && byId.has(focus)) setSelected(focus);}, [focus, byId]);
  useEffect(() => {if (selected) selectionPanel.current?.querySelector('button')?.focus({preventScroll: true});}, [selected]);
  useEffect(() => {if (list) listPanel.current?.querySelector('button')?.focus({preventScroll: true});}, [list]);
  useEffect(() => {
    const element = canvas.current; if (!element) return; if (!map) {element.width = element.width; return;}
    const {width, height} = size, ratio = window.devicePixelRatio || 1;
    element.width = Math.round(width * ratio); element.height = Math.round(height * ratio);
    const ctx = element.getContext('2d'); if (!ctx) return;
    ctx.scale(ratio, ratio); ctx.clearRect(0, 0, width, height); ctx.translate(camera.x, camera.y); ctx.scale(camera.zoom, camera.zoom);
    // A node is bright when nothing is focused, or when it belongs to the focus; a chosen branch dims the other two.
    const bright = (n: MapPoint) => (!only || n.category === only || n.role === 'center') && (!active || related.has(n.id));
    for (const edge of map.edges) {
      const a = byId.get(edge.src), b = byId.get(edge.dst); if (!a || !b) continue;
      const incident = !!active && (edge.src === active || edge.dst === active);
      if (edge.structure) {
        ctx.strokeStyle = rgba(b.color, bright(a) && bright(b) ? (active ? .55 : .38) : .05); ctx.lineWidth = 1 / camera.zoom;
        ctx.beginPath(); ctx.moveTo(a.px, a.py); ctx.lineTo(b.px, b.py); ctx.stroke(); continue;
      }
      // Recorded relations: the links between what you know, what you research and what you aim for stay faintly visible.
      if (!incident && !(edge.cross && !active && (!only || a.category === only || b.category === only))) continue;
      const dx = b.px - a.px, dy = b.py - a.py, distance = Math.hypot(dx, dy); if (!distance) continue;
      const pad = (b.r + 3) / camera.zoom, bx = b.px - dx / distance * pad, by = b.py - dy / distance * pad;
      ctx.strokeStyle = incident ? 'rgba(240,243,246,.85)' : 'rgba(190,205,225,.13)'; ctx.lineWidth = (incident ? 1.4 : .8) / camera.zoom;
      ctx.setLineDash(edge.verified === false ? [4 / camera.zoom, 4 / camera.zoom] : []); ctx.beginPath(); ctx.moveTo(a.px, a.py); ctx.lineTo(bx, by); ctx.stroke(); ctx.setLineDash([]);
      if (incident) {const angle = Math.atan2(dy, dx), arrow = 5 / camera.zoom; ctx.beginPath(); ctx.moveTo(bx, by); ctx.lineTo(bx - Math.cos(angle - .5) * arrow, by - Math.sin(angle - .5) * arrow); ctx.moveTo(bx, by); ctx.lineTo(bx - Math.cos(angle + .5) * arrow, by - Math.sin(angle + .5) * arrow); ctx.stroke();}
    }
    const order = [...points].sort((a, b) => Number(bright(a)) - Number(bright(b)) || Number(a.id === active) - Number(b.id === active));
    const boxes: {x: number; y: number; w: number}[] = [];
    const named = new Set<string>();
    // Names: the centre and the three branches always; everything else only for the focused item and what is related to it.
    const crowd = new Set(active && (byId.get(active)?.role === 'hub' || byId.get(active)?.role === 'category') && points.filter(n => n.parent === active).length > 6 ? points.filter(n => n.parent === active).map(n => n.id) : []);
    const wanted = [...points].filter(n => n.role === 'center' || n.role === 'category' || (active && related.has(n.id) && !crowd.has(n.id))).sort((a, b) => Number(b.id === active) - Number(a.id === active) || b.r - a.r);
    for (const n of wanted) {
      ctx.font = `${(n.role === 'center' ? 14 : n.role === 'category' ? 13 : 12) / camera.zoom}px system-ui`;
      const w = ctx.measureText(clip(n.label, 36)).width * camera.zoom, cx = n.px * camera.zoom + camera.x, cy = n.py * camera.zoom + camera.y + n.r * camera.zoom + 15;
      if (n.id === active || n.role === 'center' || n.role === 'category' || !boxes.some(o => Math.abs(cx - o.x) < (w + o.w) / 2 + 6 && Math.abs(cy - o.y) < 16)) {named.add(n.id); boxes.push({x: cx, y: cy, w});}
    }
    for (const n of order) {
      const lit = bright(n), focused = n.id === active, radius = n.r * (focused ? 1.3 : 1);
      ctx.globalAlpha = lit ? 1 : .12;
      ctx.fillStyle = n.color; ctx.strokeStyle = focused ? '#f4f7fa' : '#121416'; ctx.lineWidth = (focused ? 2 : 1.2) / camera.zoom;
      ctx.shadowColor = n.color; ctx.shadowBlur = lit ? (focused ? 24 : n.role === 'center' || n.role === 'category' ? 14 : n.role === 'hub' ? 8 : 0) : 0;
      ctx.beginPath();
      if (n.role === 'hub') {ctx.moveTo(n.px, n.py - radius); ctx.lineTo(n.px + radius, n.py); ctx.lineTo(n.px, n.py + radius); ctx.lineTo(n.px - radius, n.py); ctx.closePath();}
      else if (n.role === 'source') ctx.rect(n.px - radius * .85, n.py - radius * .85, radius * 1.7, radius * 1.7);
      else ctx.arc(n.px, n.py, radius, 0, Math.PI * 2);
      ctx.fill(); ctx.shadowBlur = 0; ctx.stroke();
      if (n.decision && DECISION_COLOR[n.decision]) {ctx.strokeStyle = DECISION_COLOR[n.decision]; ctx.lineWidth = 2 / camera.zoom; ctx.beginPath(); ctx.arc(n.px, n.py, radius + 3 / camera.zoom, 0, Math.PI * 2); ctx.stroke();}
      if (named.has(n.id) && lit) {
        ctx.font = `${(n.role === 'center' ? 14 : n.role === 'category' ? 13 : 12) / camera.zoom}px system-ui`; ctx.fillStyle = '#f0f3f6'; ctx.textAlign = 'center';
        ctx.fillText(clip(n.label, 36), n.px, n.py + radius + 15 / camera.zoom); ctx.textAlign = 'start';
      }
    }
    ctx.globalAlpha = 1;
  }, [map, points, byId, active, related, only, camera, size]);
  const zoom = (factor: number, x = size.width / 2, y = size.height / 2) => {steered.current = true; setCamera(c => zoomAt(c, factor, x, y));};
  const fit = () => {steered.current = false; setCamera(fitted());};
  function select(id: string) {setSelected(id); setList(false); const n = byId.get(id); if (n) setCamera(c => ({...c, x: size.width / 2 - n.px * c.zoom, y: size.height / 2 - n.py * c.zoom}));}
  function closeSelection() {setSelected(''); canvas.current?.focus();}
  function nearest(x: number, y: number, slack = 6) {
    let best: {n: MapPoint; d: number} | null = null;
    for (const n of points) {
      if (only && n.category !== only && n.role !== 'center') continue;
      const d = Math.hypot(n.px * camera.zoom + camera.x - x, n.py * camera.zoom + camera.y - y);
      if (d <= n.r * Math.min(camera.zoom, 1.5) + slack && (!best || d < best.d)) best = {n, d};
    }
    return best?.n;
  }
  const edgeLabel = (id: string) => byId.get(id)?.label || id;
  const relations = map?.edges.filter(e => !e.structure && chosen && (e.src === chosen.id || e.dst === chosen.id)) || [];
  const filedUnder = chosen?.parent ? byId.get(chosen.parent) : null;
  const tipBox = shown && size.width ? {left: Math.min(Math.max(8, shown.px * camera.zoom + camera.x + 14), Math.max(8, size.width - 250)), top: Math.min(Math.max(8, shown.py * camera.zoom + camera.y - 8), Math.max(8, size.height - 120))} : null;
  const empty = map && points.length <= 1;
  return <section className={'graph-workspace ' + (embedded ? 'graph-embedded' : '')} aria-label="Knowledge graph"><h1 className="sr-only">Your knowledge graph</h1>
    <div className="graph-chrome"><div className="segmented" role="group" aria-label="Focus on">{CATEGORIES.map(([value, label]) => <button key={value} aria-pressed={only === value} className={'legend-chip ' + value} onClick={() => setOnly(only === value ? '' : value)}><span className="dot" style={{background: CATEGORY_COLOR[value]}} aria-hidden="true"/>{label}</button>)}</div>
      <div className="graph-toolbar"><button onClick={() => zoom(1.25)} aria-label="Zoom in">+</button><button onClick={() => zoom(.8)} aria-label="Zoom out">−</button><button onClick={fit}>Fit graph</button><button aria-expanded={list} aria-controls="graph-node-panel" onClick={() => {setList(!list); setSelected('');}}>Node list</button>
        <Menu kind="graph" id="legend" label="How to read this map" buttonLabel="How to read this map" button={<span aria-hidden="true">?</span>} buttonClassName="graph-menu" align="right">{() => <div className="graph-legend"><h2>How to read this map</h2>
          <ul><li>The centre is your workspace. <strong style={{color: CATEGORY_COLOR.knowledge}}>Knowledge</strong> is what you know and are learning, <strong style={{color: CATEGORY_COLOR.research}}>Research</strong> is the work you are doing, and <strong style={{color: CATEGORY_COLOR.goals}}>Goals</strong> is what you are working toward.</li>
            <li>◆ is a course, subject or project; ● is a skill or idea. Size shows how much is connected to it, not how true or mastered it is.</li>
            <li>Hover or select anything to see its name and what it connects to; the rest fades. Faint lines between colours are recorded links between what you know, what you research and what you aim for.</li>
            <li>Choose a colour above to look at one branch. Files and notes are in the Library; select a place to show them here.</li></ul></div>}</Menu></div>
    </div>
    <div className={'graph-stage ' + (chosen || list ? 'graph-context-open' : '')}><div className="graph-frame" ref={frame}><canvas ref={canvas} tabIndex={0} aria-label="Interactive graph. Drag or use arrow keys to pan; plus and minus zoom, zero fits. Use Node list to select and open evidence."
      onKeyDown={e => {if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', '+', '=', '-', '0', 'Escape'].includes(e.key)) {e.preventDefault(); if (e.key === '0') fit(); else if (e.key === '+' || e.key === '=') zoom(1.25); else if (e.key === '-') zoom(.8); else if (e.key === 'Escape') closeSelection(); else {steered.current = true; setCamera(c => ({...c, x: c.x + (e.key === 'ArrowLeft' ? 30 : e.key === 'ArrowRight' ? -30 : 0), y: c.y + (e.key === 'ArrowUp' ? 30 : e.key === 'ArrowDown' ? -30 : 0)}));}}}}
      onWheel={e => {const rect = e.currentTarget.getBoundingClientRect(); zoom(Math.exp(-Math.max(-100, Math.min(100, e.deltaY)) * .003), e.clientX - rect.left, e.clientY - rect.top);}}
      onPointerDown={e => {e.currentTarget.setPointerCapture(e.pointerId); drag.current = {x: e.clientX, y: e.clientY, ox: camera.x, oy: camera.y, moved: false};}}
      onPointerMove={e => {const d = drag.current; if (!d) {const rect = e.currentTarget.getBoundingClientRect(), next = nearest(e.clientX - rect.left, e.clientY - rect.top)?.id || ''; if (next !== hover) setHover(next); return;} if (Math.hypot(e.clientX - d.x, e.clientY - d.y) > 5) d.moved = true; if (d.moved) {steered.current = true; setCamera(c => ({...c, x: d.ox + e.clientX - d.x, y: d.oy + e.clientY - d.y}));}}}
      onPointerLeave={() => setHover('')}
      onPointerCancel={() => {drag.current = null;}} onLostPointerCapture={() => {drag.current = null;}}
      onPointerUp={e => {const d = drag.current; drag.current = null; if (!d || d.moved) return; const rect = e.currentTarget.getBoundingClientRect(), hit = nearest(e.clientX - rect.left, e.clientY - rect.top, 8); if (hit) select(hit.id); else setSelected('');}} />
      {tipBox && shown && <div className="graph-tip" role="tooltip" style={tipBox}><strong>{shown.label}</strong><small>{shown.role === 'center' ? 'Workspace' : shown.role === 'category' ? 'Branch' : shown.kind}{shown.parent && byId.get(shown.parent) && shown.role !== 'category' ? ' · in ' + byId.get(shown.parent)!.label : ''}</small>{shown.tip && <span>{clip(shown.tip, 160)}</span>}{shown.material > 0 && <small>{shown.material} {shown.material === 1 ? 'file' : 'files'} in the Library</small>}</div>}
      {!map && <div className="graph-state"><Notice error={result.error} retry={result.retry} /></div>}
      {empty && <div className="graph-state"><h2>Start with a course or a project</h2><p className="muted">Create one in the sidebar, then add its material in the Library. Your map grows from what you build.</p><a className="button" href={href('library', '', record)}>Open Library</a></div>}
      {map && <span className="graph-count">{map.counts.hubs} places · {points.length} items</span>}
    </div>{chosen && <aside ref={selectionPanel} className="graph-selection" aria-label="Selected node" onKeyDown={e => {if (e.key === 'Escape') closeSelection();}}><button className="graph-close" aria-label="Close node details" onClick={closeSelection}>×</button><small>{chosen.role === 'center' ? 'Workspace' : chosen.role === 'category' ? 'Branch' : chosen.kind}</small><h2>{chosen.label}</h2>
      {chosen.decision && <p className="graph-decision" style={{borderColor: DECISION_COLOR[chosen.decision]}}>Your decision: <strong>{chosen.decision}</strong></p>}{chosen.tip && <p>{chosen.tip}</p>}{filedUnder && chosen.role !== 'category' && <p className="muted">In <strong>{filedUnder.label}</strong>.</p>}
      {chosen.canonical && <a className="button primary" href={entityHref(chosen.id, chosen.record || record)}>Open evidence</a>}
      {chosen.material > 0 && chosen.role === 'hub' && <><a className="button" href={href('library', '', record)}>{chosen.material} {chosen.material === 1 ? 'file' : 'files'} in the Library</a><button onClick={() => {setExpand(expand === chosen.id ? '' : chosen.id); setSelected('');}}>{expand === chosen.id ? 'Hide its files here' : 'Show its files here'}</button></>}
      <h3>Recorded connections</h3><ul className="relation-list">{relations.map((e, i) => <li key={i}><span>{e.src === chosen.id ? '→' : '←'} {e.type}</span><a href={entityHref(e.src === chosen.id ? e.dst : e.src, byId.get(e.src === chosen.id ? e.dst : e.src)?.record || record)}>{edgeLabel(e.src === chosen.id ? e.dst : e.src)}</a><small>{e.provenance || 'Provenance not recorded'}{e.verified == null ? '' : e.verified ? ' · verified' : ' · unverified'}</small></li>)}</ul>{!relations.length && <p className="muted">No recorded connections to other items yet.</p>}</aside>}
    <aside onKeyDown={e => {if (e.key === 'Escape') {setList(false); canvas.current?.focus();}}} ref={listPanel} id="graph-node-panel" className="graph-list-panel" hidden={!list} aria-label="Accessible node list"><button className="graph-close" aria-label="Close node list" onClick={() => {setList(false); canvas.current?.focus();}}>×</button><h2>Nodes in this view</h2>
      {CATEGORIES.map(([cat, label]) => {const rows = points.filter(n => n.category === cat && n.role !== 'category'); return rows.length ? <section key={cat} aria-label={label}><h3>{label}</h3><ul className="graph-node-list">{rows.map(n => <li key={n.id} onMouseLeave={() => setHover('')}><button onClick={() => select(n.id)} onFocus={() => setHover(n.id)} onBlur={() => setHover('')} aria-label={'Select ' + n.label}>{n.label}<small>{n.kind}</small></button>{n.canonical && <a href={entityHref(n.id, n.record || record)} aria-label={'Open ' + n.label}>Open</a>}</li>)}</ul></section> : null;})}
      <ul className="graph-node-list">{points.filter(n => n.role === 'center').map(n => <li key={n.id}><button onClick={() => select(n.id)} aria-label={'Select ' + n.label}>{n.label}<small>workspace</small></button></li>)}</ul>
      {map && map.needs_count > 0 && <section aria-label="Needs organization"><h3>Not shown ({map.needs_count})</h3><p className="muted">These have no name or are not connected to any course, project or goal yet. Nothing was deleted.</p><ul className="graph-node-list">{map.needs_organization.slice(0, 40).map(n => <li key={n.id}><a href={entityHref(n.id, n.record || record)}>{n.kind} · {n.reason}</a></li>)}</ul></section>}</aside></div>
  </section>;
}
