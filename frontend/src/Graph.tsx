import {useEffect, useMemo, useRef, useState} from 'react';
import {call, entityHref, href, preference, savePreference} from './api';
import type {GraphData, OrganizationMap} from './contracts';
import {useResource} from './hooks';
import {Menu} from './overlay';
import {Notice} from './ui';
import {mapLayout, pointLayout, safeCamera, zoomAt, NEUTRAL, type Camera, type PointNode} from './graphLayout';
import {startLayout, type GraphLayout} from './layoutJob';
const colors = ['#aaa0d5', '#83b9aa', '#c3ad85', '#8aadc7', '#c49cab'];
const LENSES: [string, string][] = [['map', 'Map'], ['knowledge', 'Knowledge'], ['research', 'Research'], ['evidence', 'Evidence'], ['progress', 'Progress']];
const clip = (text: string, n: number) => text.length > n ? text.slice(0, n - 1) + '…' : text;

function asGraph(map: OrganizationMap): GraphData {
  return {title: map.title, width: 0, height: 0, bounded: Object.keys(map.omitted).length > 0,
    nodes: map.nodes.map(n => ({id: n.id, label: n.label, kind: n.kind, tip: n.tip, canonical: n.canonical, x: 0, y: 0, w: 0, h: 0, role: n.role, parent: n.parent, cluster: n.cluster, weight: n.weight, record: n.record})),
    edges: map.edges.map(e => ({src: e.src, dst: e.dst, type: e.type, provenance: e.provenance, verified: e.verified, structure: e.structure}))};
}

export function Graph({focus, record, embedded = false}: {focus: string; record: string; embedded?: boolean}) {
  const [mode, setMode] = useState(focus ? 'knowledge' : 'map'), [depth, setDepth] = useState(1), [relation, setRelation] = useState(''), [expand, setExpand] = useState('');
  const [selected, setSelected] = useState(''), [list, setList] = useState(false), [lanes, setLanes] = useState(false), [hover, setHover] = useState('');
  const [camera, setCamera] = useState<Camera>({x: 0, y: 0, zoom: 1}), [size, setSize] = useState({width: 0, height: 0});
  const canvas = useRef<HTMLCanvasElement>(null), frame = useRef<HTMLDivElement>(null), initialized = useRef('');
  const selectionPanel = useRef<HTMLElement>(null), listPanel = useRef<HTMLElement>(null);
  const viewport = useRef({key: '', width: 0, height: 0}), previousGraph = useRef<GraphData | null>(null);
  const drag = useRef<{x: number; y: number; ox: number; oy: number; moved: boolean} | null>(null);
  const isMap = mode === 'map';
  const mapResult = useResource(`map:${record}:${expand}`, signal => isMap ? call<OrganizationMap>('workspace_map', {per_hub: 24, ...(expand ? {expand} : {})}, record, false, signal) : Promise.resolve(null), record);
  const result = useResource(`graph:${record}:${mode}:${focus}:${depth}:${relation}`, signal => !isMap ? call<GraphData>('workspace_graph', {mode, ...(focus ? {focus} : {}), depth, limit: 120, ...(relation ? {relation} : {})}, record, false, signal) : Promise.resolve(null), record);
  const source = isMap ? mapResult : result;
  const mapSignature = JSON.stringify(mapResult.data), graphSignature = JSON.stringify(result.data);
  // Event-only updates often leave this bounded graph unchanged. Retain its camera/layout identity.
  const map = useMemo(() => mapResult.data, [mapSignature]);
  const lensGraph = useMemo(() => result.data, [graphSignature]);
  const graph = useMemo(() => isMap ? (map ? asGraph(map) : null) : lensGraph, [isMap, map, lensGraph]);
  const [computed, setComputed] = useState<{graph: GraphData; layout: GraphLayout} | null>(null), [layoutError, setLayoutError] = useState('');
  useEffect(() => {
    setLayoutError('');
    if (!graph) return;
    if (isMap && map) {setComputed({graph, layout: mapLayout(map)}); return;}
    if (typeof Worker === 'undefined') {
      if (graph.nodes.length <= 150) setComputed({graph, layout: pointLayout(graph)});
      else setLayoutError('Graph layout is unavailable. Use Node list to explore.');
      return;
    }
    try {
      const worker = new Worker(new URL('./graphLayout.worker.ts', import.meta.url), {type: 'module'});
      return startLayout(worker, graph, layout => setComputed({graph, layout}), () => setLayoutError('Graph layout stopped. Use Node list to explore.'));
    } catch {setLayoutError('Graph layout is unavailable. Use Node list to explore.');}
  }, [graph]);
  const layout = computed && computed.graph === graph ? computed.layout : null;
  const listNodes = layout?.nodes || graph?.nodes || [];
  const canonicalId = (id: string) => graph?.nodes.find(n => n.id === id)?.canonical === false ? graph?.focus || id : id;
  const points = useMemo<(PointNode & {px: number; py: number})[]>(() => layout?.nodes.map(n => lanes ? {...n, px: n.x + n.w / 2, py: n.y + n.h / 2} : n) || [], [layout, lanes]);
  const byId = useMemo(() => new Map(points.map(n => [n.id, n])), [points]);
  const chosen = byId.get(selected), shown = byId.get(hover || selected);
  const cameraKey = 'camera:' + JSON.stringify([record, mode, focus, relation, depth, lanes, expand]);
  useEffect(() => {
    if (!frame.current) return;
    const observer = new ResizeObserver(([entry]) => setSize({width: entry.contentRect.width, height: entry.contentRect.height}));
    observer.observe(frame.current); return () => observer.disconnect();
  }, []);
  function fitted(): Camera {
    if (!points.length) return {x: size.width / 2, y: size.height / 2, zoom: 1};
    const minX = Math.min(...points.map(n => n.px)) - (lanes ? 120 : 65), maxX = Math.max(...points.map(n => n.px)) + (lanes ? 120 : 65);
    const minY = Math.min(...points.map(n => n.py)) - 50, maxY = Math.max(...points.map(n => n.py)) + 50;
    const zoom = Math.max(.12, Math.min(1.5, (size.width - 32) / Math.max(1, maxX - minX), (size.height - 32) / Math.max(1, maxY - minY)));
    return {x: (size.width - (maxX + minX) * zoom) / 2, y: (size.height - (maxY + minY) * zoom) / 2, zoom};
  }
  function fit() {setCamera(fitted());}
  useEffect(() => {
    if (!graph || !layout || !size.width || !size.height) return;
    const previous = viewport.current;
    viewport.current = {key: cameraKey, ...size};
    if (initialized.current !== cameraKey) {initialized.current = cameraKey; setCamera(safeCamera(preference(cameraKey, '')) || fitted());}
    else if (previous.key === cameraKey && (previous.width !== size.width || previous.height !== size.height)) {
      setCamera(c => chosen ? {...c, x: size.width / 2 - chosen.px * c.zoom, y: size.height / 2 - chosen.py * c.zoom} : {...c, x: c.x + (size.width - previous.width) / 2, y: c.y + (size.height - previous.height) / 2});
    } else if (previousGraph.current !== graph && !isMap) setCamera(fitted());
    previousGraph.current = graph;
  }, [graph, layout, cameraKey, size.width, size.height]);
  useEffect(() => {if (initialized.current === cameraKey) savePreference(cameraKey, JSON.stringify(camera));}, [camera, cameraKey]);
  useEffect(() => {setSelected(''); setHover(''); setList(false);}, [record, mode, focus, relation]);
  useEffect(() => {if (selected) selectionPanel.current?.querySelector('button')?.focus({preventScroll: true});}, [selected]);
  useEffect(() => {if (list) listPanel.current?.querySelector('button')?.focus({preventScroll: true});}, [list]);
  useEffect(() => {
    const element = canvas.current; if (!element) return; if (!layout) {element.width = element.width; return;}
    const {width, height} = size, ratio = window.devicePixelRatio || 1;
    element.width = Math.round(width * ratio); element.height = Math.round(height * ratio);
    const ctx = element.getContext('2d'); if (!ctx) return;
    ctx.scale(ratio, ratio); ctx.clearRect(0, 0, width, height); ctx.translate(camera.x, camera.y); ctx.scale(camera.zoom, camera.zoom);
    if (!lanes) layout.groups.forEach((g, i) => {const gradient = ctx.createRadialGradient(g.x, g.y, 0, g.x, g.y, g.radius * 1.5); gradient.addColorStop(0, colors[i % colors.length] + '16'); gradient.addColorStop(1, colors[i % colors.length] + '00'); ctx.fillStyle = gradient; ctx.beginPath(); ctx.arc(g.x, g.y, g.radius * 1.5, 0, Math.PI * 2); ctx.fill();});
    const active = hover || selected;
    for (const edge of graph!.edges) {
      const a = byId.get(edge.src), b = byId.get(edge.dst); if (!a || !b) continue;
      const dx = b.px - a.px, dy = b.py - a.py, distance = Math.hypot(dx, dy); if (!distance) continue;
      const incident = active === a.id || active === b.id;
      if (edge.structure) {
        // Organization: where something sits. It is navigation, not a claim about the science.
        ctx.strokeStyle = (b.color || NEUTRAL) + (incident ? 'cc' : '4d'); ctx.lineWidth = (incident ? 1.6 : 1) / camera.zoom;
        ctx.beginPath(); ctx.moveTo(a.px, a.py); ctx.lineTo(b.px, b.py); ctx.stroke(); continue;
      }
      if (isMap && !incident && camera.zoom < 1.1) continue;   // at overview scale only the filing branches are drawn
      const pad = lanes ? 20 : ((b.r || 3.8) + 3) / camera.zoom, bx = b.px - dx / distance * pad, by = b.py - dy / distance * pad;
      ctx.strokeStyle = incident ? '#a4bbb6' : isMap ? '#cfd8e0a0' : '#7c87945c'; ctx.lineWidth = (incident ? 1.4 : isMap ? 1 : .7) / camera.zoom;
      ctx.setLineDash(edge.verified === false ? [4 / camera.zoom, 4 / camera.zoom] : []); ctx.beginPath(); ctx.moveTo(a.px, a.py); ctx.lineTo(bx, by); ctx.stroke(); ctx.setLineDash([]);
      const angle = Math.atan2(dy, dx), arrow = 5 / camera.zoom; ctx.beginPath(); ctx.moveTo(bx, by); ctx.lineTo(bx - Math.cos(angle - .5) * arrow, by - Math.sin(angle - .5) * arrow); ctx.moveTo(bx, by); ctx.lineTo(bx - Math.cos(angle + .5) * arrow, by - Math.sin(angle + .5) * arrow); ctx.stroke();
      if (incident || lanes && camera.zoom > .7) {ctx.font = `${10 / camera.zoom}px system-ui`; ctx.fillStyle = '#b3bdc8'; ctx.fillText(edge.type, (a.px + b.px) / 2 + 4, (a.py + b.py) / 2 - 4);}
    }
    const boxes: {x: number; y: number; w: number}[] = [];
    const order = [...points].sort((a, b) => (Number(a.id === selected) + Number(a.id === hover)) - (Number(b.id === selected) + Number(b.id === hover)));
    const labelled = new Set<string>();
    if (isMap && !lanes) {
      // Biggest and focused labels claim space first; a label that would sit on another is left for hover or zoom.
      const rank = (n: (typeof points)[number]) => n.id === selected || n.id === hover ? 1e9 : n.role === 'center' ? 1e8 : (n.r || 0) * 100 + (n.weight || 0);
      for (const n of [...points].sort((x, y) => rank(y) - rank(x))) {
        const role = n.role, focused = n.id === selected || n.id === hover;
        if (!(focused || role === 'center' || role === 'hub' || (role === 'topic' ? camera.zoom > .55 : camera.zoom > .95))) continue;
        ctx.font = `${(role === 'center' ? 14 : role === 'hub' ? 12.5 : 11) / camera.zoom}px system-ui`;
        const text = clip(n.label, role === 'hub' || role === 'center' ? 40 : 35) + (role === 'hub' && map?.omitted[n.id] ? ` +${map.omitted[n.id]}` : '');
        const w = ctx.measureText(text).width * camera.zoom, cx = n.px * camera.zoom + camera.x, cy = n.py * camera.zoom + camera.y + (n.r || 6) * (focused ? 1.25 : 1) * camera.zoom + 15;
        if (focused || role === 'center' || !boxes.some(o => Math.abs(cx - o.x) < (w + o.w) / 2 + 6 && Math.abs(cy - o.y) < 16)) {labelled.add(n.id); boxes.push({x: cx, y: cy, w});}
      }
    }
    for (const n of order) {
      const focused = selected === n.id || hover === n.id, role = n.role;
      const color = isMap ? n.color || NEUTRAL : colors[n.group % colors.length], radius = isMap ? (n.r || 4) * (focused ? 1.25 : 1) : (focused ? 6 : 3.8) / camera.zoom;
      ctx.fillStyle = color; ctx.strokeStyle = focused ? '#edf0f3' : '#121416'; ctx.lineWidth = 1.5 / camera.zoom;
      // A restrained, static glow; stronger for the item under the pointer or keyboard focus. Nothing animates.
      ctx.shadowColor = color; ctx.shadowBlur = isMap ? (focused ? 26 : role === 'center' ? 18 : role === 'hub' ? 14 : role === 'topic' ? 7 : 0) : 0;
      ctx.beginPath(); if (lanes) ctx.roundRect(n.px - n.w / 2, n.py - n.h / 2, n.w, n.h, 5);
      else if (isMap && role === 'hub') {const r = radius; ctx.moveTo(n.px, n.py - r); ctx.lineTo(n.px + r, n.py); ctx.lineTo(n.px, n.py + r); ctx.lineTo(n.px - r, n.py); ctx.closePath();}
      else if (isMap && role === 'source') ctx.rect(n.px - radius * .85, n.py - radius * .85, radius * 1.7, radius * 1.7);
      else ctx.arc(n.px, n.py, radius, 0, Math.PI * 2);
      ctx.fill(); ctx.shadowBlur = 0; ctx.stroke();
      const sx = n.px * camera.zoom + camera.x + 10, sy = n.py * camera.zoom + camera.y; ctx.font = `${(role === 'center' ? 14 : role === 'hub' ? 12.5 : 11) / camera.zoom}px system-ui`;
      const label = clip(n.label, role === 'hub' || role === 'center' ? 40 : 35), w = ctx.measureText(label).width * camera.zoom, clear = !boxes.some(b => sx < b.x + b.w + 10 && sx + w > b.x - 10 && Math.abs(sy - b.y) < 20);
      const persistent = isMap && (role === 'center' || role === 'hub');
      const wanted = isMap && !lanes ? labelled.has(n.id) : focused || lanes || (camera.zoom > .35 && clear);
      if (wanted) {
        ctx.fillStyle = lanes ? '#121416' : focused || persistent ? '#f0f3f6' : '#adb5bf';
        const omitted = isMap && role === 'hub' && map?.omitted[n.id] ? ` +${map.omitted[n.id]}` : '';
        if (isMap && !lanes) {ctx.textAlign = 'center'; ctx.fillText(label + omitted, n.px, n.py + (n.r || 6) * (focused ? 1.25 : 1) + 15 / camera.zoom); ctx.textAlign = 'start';}
        else ctx.fillText(label, n.px + (lanes ? -n.w / 2 + 8 : 10 / camera.zoom), n.py + 4 / camera.zoom);
        if (!isMap || lanes) boxes.push({x: sx, y: sy, w});
      }
    }
  }, [graph, layout, points, selected, hover, camera, size, lanes]);
  function zoom(factor: number, x = size.width / 2, y = size.height / 2) {setCamera(c => zoomAt(c, factor, x, y));}
  function select(id: string) {setSelected(id); setList(false); const n = byId.get(id); if (n) setCamera(c => ({...c, x: size.width / 2 - n.px * c.zoom, y: size.height / 2 - n.py * c.zoom}));}
  function closeSelection() {setSelected(''); canvas.current?.focus();}
  function nearest(x: number, y: number, slack = 6) {
    let best: {n: PointNode & {px: number; py: number}; d: number} | null = null;
    for (const n of points) {
      const d = Math.hypot(n.px * camera.zoom + camera.x - x, n.py * camera.zoom + camera.y - y), reach = isMap ? (n.r || 4) * Math.min(camera.zoom, 1.5) + slack : 22;
      if (d <= reach && (!best || d < best.d)) best = {n, d};
    }
    return best?.n;
  }
  const edgeLabel = (id: string) => byId.get(id)?.label || id;
  const link = (n: {id: string; record?: string; kind: string}) => n.kind === 'library' ? href('library', '', record) : entityHref(canonicalId(n.id), n.record || record);
  const relations = graph?.edges.filter(e => !e.structure && chosen && (e.src === chosen.id || e.dst === chosen.id)) || [];
  const placement = chosen && isMap && chosen.parent ? byId.get(chosen.parent) : null;
  const hiddenInHub = chosen && map?.omitted[chosen.id];
  const tipBox = shown && size.width ? {left: Math.min(Math.max(8, shown.px * camera.zoom + camera.x + 14), Math.max(8, size.width - 250)), top: Math.min(Math.max(8, shown.py * camera.zoom + camera.y - 8), Math.max(8, size.height - 110))} : null;
  return <section className={'graph-workspace ' + (embedded ? 'graph-embedded' : '')} aria-label="Knowledge graph"><h1 className="sr-only">Your knowledge graph</h1>
    <div className="graph-chrome">{mode === 'progress' && graph?.progress && <details className="progress-summary"><summary>{graph.progress.due} Reviews Due · Weekly Progress</summary><div className="table-wrap"><table><thead><tr><th>Week</th><th>Answers</th><th>Unaided Correct</th><th>Reviews</th></tr></thead><tbody>{graph.progress.weeks.map(w => <tr key={w.week}><td>{w.week}</td><td>{w.answers}</td><td>{w.unaided_correct}</td><td>{w.reviews}</td></tr>)}</tbody></table></div></details>}<div className="segmented" role="group" aria-label="Graph lens">{LENSES.map(([value, label]) => <button key={value} aria-pressed={mode === value} onClick={() => {setMode(value); setLanes(false); setExpand('');}}>{label}</button>)}</div>
      <div className="graph-toolbar"><button onClick={() => zoom(1.25)} aria-label="Zoom in">+</button><button onClick={() => zoom(.8)} aria-label="Zoom out">−</button><button onClick={fit}>Fit graph</button><button aria-expanded={list} aria-controls="graph-node-panel" onClick={() => {setList(!list); setSelected('');}}>Node list</button>
        {isMap && <Menu kind="graph" id="legend" label="How to read this map" buttonLabel="How to read this map" button={<span aria-hidden="true">?</span>} buttonClassName="graph-menu" align="right">{() => <div className="graph-legend"><h2>How to read this map</h2>
          <ul><li><strong>Centre</strong>: this workspace. <strong>◆ Diamonds</strong>: courses and projects, each in its own colour. <strong>● Circles</strong>: topics. <strong>■ Squares</strong>: material and sessions.</li>
            <li><strong>Size</strong> shows organizational prominence: role first, then how many recorded links an item has. It is not a score for how true or mastered something is.</li>
            <li><strong>Plain lines</strong> show where something is filed. They are for finding your way and say nothing about the science. <strong>Arrows</strong> are relations that were actually recorded; dashed means not yet verified.</li>
            <li>Hover or focus an item to read its name and meaning. Press Node list for an accessible outline.</li></ul>
          <ul className="legend-swatches">{points.filter(p => p.role === 'hub').map(p => <li key={p.id}><span style={{background: p.color}} aria-hidden="true"/>◆ {p.label}</li>)}</ul></div>}</Menu>}
        <Menu kind="graph" id="settings" label="Display options" buttonLabel="Graph settings" button={<span aria-hidden="true">•••</span>} buttonClassName="graph-menu" align="right">{() => <div className="graph-settings-panel">
          {!isMap && <button onClick={() => setDepth(x => (x + 1) % 4)} aria-label="Change neighbourhood depth">{depth} {depth === 1 ? 'hop' : 'hops'}</button>}
          {!isMap && <label>Filter relations<select value={relation} onChange={e => setRelation(e.target.value)}><option value="">All relations</option>{['requires', 'supports', 'invalidates', 'tests', 'implements', 'cites', 'supersedes', 'part-of', 'addresses', 'decides', 'relates', 'about', 'teaches', 'applied-in'].map(type => <option key={type}>{type}</option>)}</select></label>}
          {mode === 'research' && <button aria-pressed={lanes} onClick={() => setLanes(!lanes)}>Directed lanes</button>}
          {isMap && expand && <button onClick={() => setExpand('')}>Show fewer items per course</button>}
          <p>{isMap ? 'Plain lines show where things are filed, not scientific support. Arrows follow recorded source → target.' : 'Arrows follow recorded source → target. Spatial groups indicate connections, not verified evidence.'}</p>{graph?.bounded && <p>{isMap ? 'Some courses show only their most connected items. Choose a course, then Show everything in it.' : 'This view is bounded. Focus a node to explore more.'}</p>}</div>}</Menu></div>
    </div>{focus && <div className="graph-focus"><a href={href('graph', '', record)}>← All hubs</a><span>{points.find(p => p.id === focus)?.label || 'Selected item'}</span></div>}
    <div className={'graph-stage ' + (chosen || list ? 'graph-context-open' : '')}><div className="graph-frame" ref={frame}><canvas ref={canvas} tabIndex={0} aria-label="Interactive graph. Drag or use arrow keys to pan; plus and minus zoom, zero fits. Use Node list to select and open evidence."
      onKeyDown={e => {if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', '+', '=', '-', '0', 'Escape'].includes(e.key)) {e.preventDefault(); if (e.key === '0') fit(); else if (e.key === '+' || e.key === '=') zoom(1.25); else if (e.key === '-') zoom(.8); else if (e.key === 'Escape') closeSelection(); else setCamera(c => ({...c, x: c.x + (e.key === 'ArrowLeft' ? 30 : e.key === 'ArrowRight' ? -30 : 0), y: c.y + (e.key === 'ArrowUp' ? 30 : e.key === 'ArrowDown' ? -30 : 0)}));}}}
      onWheel={e => {const rect = e.currentTarget.getBoundingClientRect(); zoom(Math.exp(-Math.max(-100, Math.min(100, e.deltaY)) * .003), e.clientX - rect.left, e.clientY - rect.top);}}
      onPointerDown={e => {e.currentTarget.setPointerCapture(e.pointerId); drag.current = {x: e.clientX, y: e.clientY, ox: camera.x, oy: camera.y, moved: false};}}
      onPointerMove={e => {const d = drag.current; if (!d) {if (!isMap || lanes) return; const rect = e.currentTarget.getBoundingClientRect(), hit = nearest(e.clientX - rect.left, e.clientY - rect.top); const next = hit?.id || ''; if (next !== hover) setHover(next); return;} if (Math.hypot(e.clientX - d.x, e.clientY - d.y) > 5) d.moved = true; if (d.moved) setCamera(c => ({...c, x: d.ox + e.clientX - d.x, y: d.oy + e.clientY - d.y}));}}
      onPointerLeave={() => setHover('')}
      onPointerCancel={() => {drag.current = null;}} onLostPointerCapture={() => {drag.current = null;}}
      onPointerUp={e => {const d = drag.current; drag.current = null; if (!d || d.moved) return; const rect = e.currentTarget.getBoundingClientRect(), x = e.clientX - rect.left, y = e.clientY - rect.top; const hit = nearest(x, y, isMap ? 8 : 22); const laneHit = lanes ? points.find(n => Math.abs((x - camera.x) / camera.zoom - n.px) <= n.w / 2 + 4 / camera.zoom && Math.abs((y - camera.y) / camera.zoom - n.py) <= n.h / 2 + 4 / camera.zoom) : null; if (laneHit) select(laneHit.id); else if (hit && !lanes) select(hit.id); else setSelected('');}} />
      {tipBox && shown && isMap && <div className="graph-tip" role="tooltip" style={tipBox}><strong>{shown.label}</strong><small>{shown.kind === 'workspace' ? 'Workspace' : shown.kind}{shown.role === 'topic' || shown.role === 'source' ? ' · in ' + (byId.get(shown.parent || '')?.label || 'Inbox') : ''}</small>{shown.tip && <span>{clip(shown.tip, 160)}</span>}</div>}
      {!graph && <div className="graph-state"><Notice error={source.error} retry={source.retry} /></div>}{graph && !layout && <div className="graph-state" role={layoutError ? 'alert' : 'status'}>{layoutError || 'Preparing graph…'}</div>}{graph && layout && !points.length && <div className="graph-state"><h2>Connect Your Workspace</h2><p className="muted">Add material or create a course or project. You can explore without a model.</p><a className="button" href={href('library', '', record)}>Open Library</a></div>}{graph && <span className="graph-count">{isMap ? `${map?.counts.hubs ?? 0} courses and projects · ${graph.nodes.length} items` : `${graph.nodes.length} nodes · ${graph.edges.length} relations`}{graph.bounded ? ' · bounded view' : ''}</span>}
    </div>{chosen && <aside ref={selectionPanel} className="graph-selection" aria-label="Selected node" onKeyDown={e => {if (e.key === 'Escape') closeSelection();}}><button className="graph-close" aria-label="Close node details" onClick={closeSelection}>×</button><small>{chosen.kind === 'workspace' ? 'Workspace' : chosen.kind}</small><h2>{chosen.label}</h2>
      {isMap && chosen.tip && <p>{chosen.tip}</p>}
      {isMap && placement && <p className="muted">Filed under <strong>{placement.label}</strong>.</p>}
      {(!isMap || chosen.canonical !== false || chosen.kind === 'library') && chosen.role !== 'center' && <a className="button primary" href={isMap ? link(chosen) : entityHref(chosen.canonical === false ? graph?.focus || chosen.id : chosen.id, record)}>{chosen.kind === 'library' ? 'Open in Library' : 'Open evidence'}</a>}
      {isMap && chosen.role === 'hub' && chosen.kind !== 'inbox' && <a className="button" href={href('graph', chosen.id, chosen.record || record)}>Focus on this {chosen.kind}</a>}
      {isMap && hiddenInHub ? <button onClick={() => {setExpand(chosen.id); setSelected('');}}>Show everything in it ({hiddenInHub} more)</button> : null}
      {!isMap && <a className="button" href={href('graph', canonicalId(chosen.id), record)}>Focus neighbourhood</a>}<h3>Recorded connections</h3><ul className="relation-list">{relations.map((e, i) => <li key={i}><span>{e.src === chosen.id ? '→' : '←'} {e.type}</span><a href={entityHref(canonicalId(e.src === chosen.id ? e.dst : e.src), (byId.get(e.src === chosen.id ? e.dst : e.src)?.record) || record)}>{edgeLabel(e.src === chosen.id ? e.dst : e.src)}</a><small>{e.provenance || 'Provenance not recorded'}{e.verified == null ? '' : e.verified ? ' · verified' : ' · unverified'}</small></li>)}</ul>{!relations.length && <p className="muted">No recorded relations in this view{isMap ? '. Where it is filed is shown above.' : '.'}</p>}</aside>}
    <aside onKeyDown={e => {if (e.key === 'Escape') {setList(false); canvas.current?.focus();}}} ref={listPanel} id="graph-node-panel" className="graph-list-panel" hidden={!list} aria-label="Accessible node list"><button className="graph-close" aria-label="Close node list" onClick={() => {setList(false); canvas.current?.focus();}}>×</button><h2>Nodes in this view</h2><ul className="graph-node-list">{listNodes.map(n => <li key={n.id} onMouseLeave={() => setHover('')}><button onClick={() => select(n.id)} onFocus={() => isMap && setHover(n.id)} onBlur={() => setHover('')} aria-label={'Select ' + n.label}>{n.label}<small>{n.kind}</small></button>{(!isMap || n.canonical !== false) && n.role !== 'center' && <a href={link(n)} aria-label={'Open ' + n.label}>Open</a>}{!isMap && <a href={href('graph', canonicalId(n.id), record)} aria-label={'Focus ' + n.label}>Focus</a>}</li>)}</ul>
      {isMap && map && map.needs_count > 0 && <section aria-label="Needs organization"><h2>Needs organization ({map.needs_count})</h2><p className="muted">These have no name or description, so they are not drawn. Nothing was deleted.</p><ul className="graph-node-list">{map.needs_organization.slice(0, 40).map(n => <li key={n.id}><a href={entityHref(n.id, n.record || record)}>{n.kind} · {n.reason}</a></li>)}</ul></section>}</aside></div>
  </section>;
}
