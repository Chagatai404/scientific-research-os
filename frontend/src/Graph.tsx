import {useEffect, useMemo, useRef, useState} from 'react';
import {call, entityHref, href, preference, savePreference} from './api';
import type {GraphData} from './contracts';
import {useResource} from './hooks';
import {Notice} from './ui';
import {pointLayout, safeCamera, zoomAt, type Camera} from './graphLayout';
const colors = ['#aaa0d5', '#83b9aa', '#c3ad85', '#8aadc7', '#c49cab'];

export function Graph({focus, record, embedded = false}: {focus: string; record: string; embedded?: boolean}) {
  const [mode, setMode] = useState('knowledge'), [depth, setDepth] = useState(1), [relation, setRelation] = useState('');
  const [selected, setSelected] = useState(''), [list, setList] = useState(false), [lanes, setLanes] = useState(false);
  const [camera, setCamera] = useState<Camera>({x: 0, y: 0, zoom: 1}), [size, setSize] = useState({width: 0, height: 0});
  const canvas = useRef<HTMLCanvasElement>(null), frame = useRef<HTMLDivElement>(null), initialized = useRef('');
  const selectionPanel = useRef<HTMLElement>(null), listPanel = useRef<HTMLElement>(null);
  const viewport = useRef({key: '', width: 0, height: 0}), previousGraph = useRef<GraphData | null>(null);
  const drag = useRef<{x: number; y: number; ox: number; oy: number; moved: boolean} | null>(null);
  const result = useResource(`graph:${record}:${mode}:${focus}:${depth}:${relation}`, signal => call<GraphData>('workspace_graph', {mode, ...(focus ? {focus} : {}), depth, limit: 120, ...(relation ? {relation} : {})}, record, false, signal), record);
  const graphSignature = JSON.stringify(result.data);
  // Event-only updates often leave this bounded graph unchanged. Retain its camera/layout identity.
  const graph = useMemo(() => result.data, [graphSignature]);
  const layout = useMemo(() => graph ? pointLayout(graph) : null, [graph]);
  const points = useMemo(() => layout?.nodes.map(n => lanes ? {...n, px: n.x + n.w / 2, py: n.y + n.h / 2} : n) || [], [layout, lanes]);
  const chosen = points.find(n => n.id === selected), cameraKey = 'camera:' + JSON.stringify([record, mode, focus, relation, depth, lanes]);
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
    if (!graph || !size.width || !size.height) return;
    const previous = viewport.current;
    viewport.current = {key: cameraKey, ...size};
    if (initialized.current !== cameraKey) {initialized.current = cameraKey; setCamera(safeCamera(preference(cameraKey, '')) || fitted());}
    else if (previous.key === cameraKey && (previous.width !== size.width || previous.height !== size.height)) {
      setCamera(c => chosen ? {...c, x: size.width / 2 - chosen.px * c.zoom, y: size.height / 2 - chosen.py * c.zoom} : {...c, x: c.x + (size.width - previous.width) / 2, y: c.y + (size.height - previous.height) / 2});
    } else if (previousGraph.current !== graph) setCamera(fitted());
    previousGraph.current = graph;
  }, [graph, cameraKey, size.width, size.height]);
  useEffect(() => {if (initialized.current === cameraKey) savePreference(cameraKey, JSON.stringify(camera));}, [camera, cameraKey]);
  useEffect(() => {setSelected(''); setList(false);}, [record, mode, focus, relation]);
  useEffect(() => {if (selected) selectionPanel.current?.querySelector('button')?.focus({preventScroll: true});}, [selected]);
  useEffect(() => {if (list) listPanel.current?.querySelector('button')?.focus({preventScroll: true});}, [list]);
  useEffect(() => {
    const element = canvas.current; if (!element || !layout) return;
    const {width, height} = size, ratio = window.devicePixelRatio || 1;
    element.width = Math.round(width * ratio); element.height = Math.round(height * ratio);
    const ctx = element.getContext('2d'); if (!ctx) return;
    ctx.scale(ratio, ratio); ctx.clearRect(0, 0, width, height); ctx.translate(camera.x, camera.y); ctx.scale(camera.zoom, camera.zoom);
    const byId = new Map(points.map(n => [n.id, n]));
    if (!lanes) layout.groups.forEach((g, i) => {const gradient = ctx.createRadialGradient(g.x, g.y, 0, g.x, g.y, g.radius * 1.5); gradient.addColorStop(0, colors[i % colors.length] + '16'); gradient.addColorStop(1, colors[i % colors.length] + '00'); ctx.fillStyle = gradient; ctx.beginPath(); ctx.arc(g.x, g.y, g.radius * 1.5, 0, Math.PI * 2); ctx.fill();});
    for (const edge of graph!.edges) {
      const a = byId.get(edge.src), b = byId.get(edge.dst); if (!a || !b) continue;
      const dx = b.px - a.px, dy = b.py - a.py, distance = Math.hypot(dx, dy); if (!distance) continue;
      const pad = lanes ? 20 : 8 / camera.zoom, bx = b.px - dx / distance * pad, by = b.py - dy / distance * pad, incident = selected === a.id || selected === b.id;
      ctx.strokeStyle = incident ? '#a4bbb6' : '#7c87945c'; ctx.lineWidth = (incident ? 1.2 : .7) / camera.zoom;
      ctx.setLineDash(edge.verified === false ? [4 / camera.zoom, 4 / camera.zoom] : []); ctx.beginPath(); ctx.moveTo(a.px, a.py); ctx.lineTo(bx, by); ctx.stroke(); ctx.setLineDash([]);
      const angle = Math.atan2(dy, dx), arrow = 4 / camera.zoom; ctx.beginPath(); ctx.moveTo(bx, by); ctx.lineTo(bx - Math.cos(angle - .5) * arrow, by - Math.sin(angle - .5) * arrow); ctx.moveTo(bx, by); ctx.lineTo(bx - Math.cos(angle + .5) * arrow, by - Math.sin(angle + .5) * arrow); ctx.stroke();
      if (incident || lanes && camera.zoom > .7) {ctx.font = `${10 / camera.zoom}px system-ui`; ctx.fillStyle = '#b3bdc8'; ctx.fillText(edge.type, (a.px + b.px) / 2 + 4, (a.py + b.py) / 2 - 4);}
    }
    const boxes: {x: number; y: number; w: number}[] = [];
    for (const n of [...points].sort((a, b) => Number(b.id === selected) - Number(a.id === selected))) {
      const active = selected === n.id; ctx.fillStyle = colors[n.group % colors.length]; ctx.strokeStyle = active ? '#edf0f3' : '#121416'; ctx.lineWidth = 1.5 / camera.zoom;
      ctx.beginPath(); if (lanes) ctx.roundRect(n.px - n.w / 2, n.py - n.h / 2, n.w, n.h, 5); else ctx.arc(n.px, n.py, (active ? 6 : 3.8) / camera.zoom, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      const sx = n.px * camera.zoom + camera.x + 10, sy = n.py * camera.zoom + camera.y; ctx.font = `${11 / camera.zoom}px system-ui`;
      const label = n.label.length > 35 ? n.label.slice(0, 33) + '…' : n.label, w = ctx.measureText(label).width * camera.zoom, clear = !boxes.some(b => sx < b.x + b.w + 10 && sx + w > b.x - 10 && Math.abs(sy - b.y) < 20);
      if (active || lanes || camera.zoom > .35 && clear) {ctx.fillStyle = lanes ? '#121416' : active ? '#f0f3f6' : '#adb5bf'; ctx.fillText(label, n.px + (lanes ? -n.w / 2 + 8 : 10 / camera.zoom), n.py + 4 / camera.zoom); boxes.push({x: sx, y: sy, w});}
    }
  }, [graph, layout, points, selected, camera, size, lanes]);
  function zoom(factor: number, x = size.width / 2, y = size.height / 2) {setCamera(c => zoomAt(c, factor, x, y));}
  function select(id: string) {setSelected(id); setList(false); const n = points.find(p => p.id === id); if (n) setCamera(c => ({...c, x: size.width / 2 - n.px * c.zoom, y: size.height / 2 - n.py * c.zoom}));}
  function closeSelection() {setSelected(''); canvas.current?.focus();}
  return <section className={'graph-workspace ' + (embedded ? 'graph-embedded' : '')} aria-label="Knowledge graph"><h1 className="sr-only">Your knowledge graph</h1>
    <div className="graph-chrome"><div className="segmented" role="group" aria-label="Graph lens">{['knowledge', 'research'].map(value => <button key={value} aria-pressed={mode === value} onClick={() => {setMode(value); setLanes(false);}}>{value === 'knowledge' ? 'Knowledge' : 'Research'}</button>)}</div>
      <div className="graph-toolbar"><button onClick={() => zoom(1.25)} aria-label="Zoom in">+</button><button onClick={() => zoom(.8)} aria-label="Zoom out">−</button><button onClick={fit}>Fit graph</button><button aria-expanded={list} aria-controls="graph-node-panel" onClick={() => {setList(!list); setSelected('');}}>Node list</button><details className="graph-settings"><summary aria-label="Graph settings">•••</summary><div className="graph-settings-panel"><button onClick={() => setDepth(x => (x + 1) % 4)} aria-label="Change neighbourhood depth">{depth} {depth === 1 ? 'hop' : 'hops'}</button><label>Filter relations<select value={relation} onChange={e => setRelation(e.target.value)}><option value="">All relations</option>{['requires', 'supports', 'invalidates', 'tests', 'implements', 'cites', 'supersedes', 'part-of', 'addresses', 'decides', 'relates', 'about', 'teaches', 'applied-in'].map(type => <option key={type}>{type}</option>)}</select></label>{mode === 'research' && <button aria-pressed={lanes} onClick={() => setLanes(!lanes)}>Directed lanes</button>}<p>Arrows follow recorded source → target. Spatial groups indicate connections, not verified evidence.</p>{graph?.bounded && <p>This view is bounded. Focus a node to explore more.</p>}</div></details></div>
    </div>{focus && <div className="graph-focus"><a href={href('graph', '', record)}>← All hubs</a><span>{points.find(p => p.id === focus)?.label || focus}</span></div>}
    <div className={'graph-stage ' + (chosen || list ? 'graph-context-open' : '')}><div className="graph-frame" ref={frame}><canvas ref={canvas} tabIndex={0} aria-label="Interactive graph. Drag or use arrow keys to pan; plus and minus zoom, zero fits. Use Node list to select and open evidence."
      onKeyDown={e => {if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', '+', '=', '-', '0', 'Escape'].includes(e.key)) {e.preventDefault(); if (e.key === '0') fit(); else if (e.key === '+' || e.key === '=') zoom(1.25); else if (e.key === '-') zoom(.8); else if (e.key === 'Escape') closeSelection(); else setCamera(c => ({...c, x: c.x + (e.key === 'ArrowLeft' ? 30 : e.key === 'ArrowRight' ? -30 : 0), y: c.y + (e.key === 'ArrowUp' ? 30 : e.key === 'ArrowDown' ? -30 : 0)}));}}}
      onWheel={e => {const rect = e.currentTarget.getBoundingClientRect(); zoom(Math.exp(-Math.max(-100, Math.min(100, e.deltaY)) * .003), e.clientX - rect.left, e.clientY - rect.top);}}
      onPointerDown={e => {e.currentTarget.setPointerCapture(e.pointerId); drag.current = {x: e.clientX, y: e.clientY, ox: camera.x, oy: camera.y, moved: false};}}
      onPointerMove={e => {const d = drag.current; if (!d) return; if (Math.hypot(e.clientX - d.x, e.clientY - d.y) > 5) d.moved = true; if (d.moved) setCamera(c => ({...c, x: d.ox + e.clientX - d.x, y: d.oy + e.clientY - d.y}));}}
      onPointerCancel={() => {drag.current = null;}} onLostPointerCapture={() => {drag.current = null;}}
      onPointerUp={e => {const d = drag.current; drag.current = null; if (!d || d.moved) return; const rect = e.currentTarget.getBoundingClientRect(), x = e.clientX - rect.left, y = e.clientY - rect.top; const hit = points.map(n => ({n, distance: Math.hypot(n.px * camera.zoom + camera.x - x, n.py * camera.zoom + camera.y - y)})).sort((a, b) => a.distance - b.distance)[0]; const laneHit = lanes ? points.find(n => Math.abs((x - camera.x) / camera.zoom - n.px) <= n.w / 2 + 4 / camera.zoom && Math.abs((y - camera.y) / camera.zoom - n.py) <= n.h / 2 + 4 / camera.zoom) : null; if (laneHit) select(laneHit.id); else if (hit && !lanes && hit.distance <= 22) select(hit.n.id); else setSelected('');}} />
      {!graph && <div className="graph-state"><Notice error={result.error} retry={result.retry} /></div>}{graph && !points.length && <div className="graph-state"><p>No nodes in this lens yet.</p><p className="muted">Start with a question below or explore another lens.</p></div>}{graph && <span className="graph-count">{graph.nodes.length} nodes · {graph.edges.length} relations{graph.bounded ? ' · bounded view' : ''}</span>}
    </div>{chosen && <aside ref={selectionPanel} className="graph-selection" aria-label="Selected node" onKeyDown={e => {if (e.key === 'Escape') closeSelection();}}><button className="graph-close" aria-label="Close node details" onClick={closeSelection}>×</button><small>{chosen.kind}</small><h2>{chosen.label}</h2><a className="button primary" href={entityHref(chosen.id, record)}>Open evidence</a><a className="button" href={href('graph', chosen.id, record)}>Focus neighbourhood</a><h3>Recorded connections</h3><ul className="relation-list">{graph?.edges.filter(e => e.src === chosen.id || e.dst === chosen.id).map((e, i) => <li key={i}><span>{e.src === chosen.id ? '→' : '←'} {e.type}</span><a href={entityHref(e.src === chosen.id ? e.dst : e.src, record)}>{points.find(n => n.id === (e.src === chosen.id ? e.dst : e.src))?.label || (e.src === chosen.id ? e.dst : e.src)}</a><small>{e.provenance || 'Provenance not recorded'}{e.verified == null ? '' : e.verified ? ' · verified' : ' · unverified'}</small></li>)}</ul>{!graph?.edges.some(e => e.src === chosen.id || e.dst === chosen.id) && <p className="muted">No incident relations in this bounded view.</p>}</aside>}
    <aside onKeyDown={e => {if (e.key === 'Escape') {setList(false); canvas.current?.focus();}}} ref={listPanel} id="graph-node-panel" className="graph-list-panel" hidden={!list} aria-label="Accessible node list"><button className="graph-close" aria-label="Close node list" onClick={() => {setList(false); canvas.current?.focus();}}>×</button><h2>Nodes in this view</h2><ul className="graph-node-list">{points.map(n => <li key={n.id}><button onClick={() => select(n.id)} aria-label={'Select ' + n.label}>{n.label}<small>{n.kind}</small></button><a href={entityHref(n.id, record)} aria-label={'Open ' + n.label}>Open</a><a href={href('graph', n.id, record)} aria-label={'Focus ' + n.label}>Focus</a></li>)}</ul></aside></div>
  </section>;
}
