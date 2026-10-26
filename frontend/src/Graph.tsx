import {useEffect, useRef, useState} from 'react';
import {call, entityHref, href} from './api';
import type {GraphData} from './contracts';
import {useResource} from './hooks';
import {Empty, Notice} from './ui';

export function Graph({focus, record, embedded = false}: {focus: string; record: string; embedded?: boolean}) {
  const [mode, setMode] = useState('knowledge');
  const [depth, setDepth] = useState(1);
  const [relation, setRelation] = useState('');
  const [selected, setSelected] = useState('');
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({x: 24, y: 24});
  const canvas = useRef<HTMLCanvasElement>(null);
  const frame = useRef<HTMLDivElement>(null);
  const drag = useRef<{x: number; y: number; ox: number; oy: number; moved: boolean} | null>(null);
  const result = useResource(`graph:${record}:${mode}:${focus}:${depth}:${relation}`, signal => call<GraphData>('workspace_graph', {mode, ...(focus ? {focus} : {}), depth, limit: 120, ...(relation ? {relation} : {})}, record, false, signal));
  const graph = result.data;
  useEffect(() => {setSelected(''); setOffset({x: 24, y: 24}); setZoom(1);}, [focus, mode]);
  useEffect(() => {
    if (!canvas.current || !frame.current || !graph) return;
    function draw() {
      const element = canvas.current; if (!element || !frame.current || !graph) return;
      const width = frame.current.clientWidth, height = Math.max(200, frame.current.clientHeight - 2), ratio = window.devicePixelRatio || 1;
      element.width = width * ratio; element.height = height * ratio;
      const ctx = element.getContext('2d'); if (!ctx) return;
      ctx.scale(ratio, ratio); ctx.clearRect(0, 0, width, height); ctx.save(); ctx.translate(offset.x, offset.y); ctx.scale(zoom, zoom);
      const nodes = new Map(graph.nodes.map(n => [n.id, n]));
      for (const edge of graph.edges) {
        const a = nodes.get(edge.src), b = nodes.get(edge.dst); if (!a || !b) continue;
        const x1 = a.x + a.w, y1 = a.y + a.h / 2, x2 = b.x, y2 = b.y + b.h / 2;
        ctx.strokeStyle = '#536873'; ctx.lineWidth = 1.2 / zoom;
        ctx.beginPath(); ctx.moveTo(x1, y1); ctx.bezierCurveTo((x1 + x2) / 2, y1, (x1 + x2) / 2, y2, x2, y2); ctx.stroke();
        ctx.fillStyle = '#748b96'; ctx.beginPath(); ctx.moveTo(x2, y2); ctx.lineTo(x2 - 7, y2 - 4); ctx.lineTo(x2 - 7, y2 + 4); ctx.fill();
        if (zoom > 0.75) {ctx.font = '10px system-ui'; ctx.fillText(edge.type, (x1 + x2) / 2 - 12, (y1 + y2) / 2 - 7);}
      }
      for (const node of graph.nodes) {
        ctx.fillStyle = node.id === selected ? '#25443e' : '#1d2b34'; ctx.strokeStyle = node.id === selected ? '#79cbbb' : '#455b68'; ctx.lineWidth = node.id === selected ? 2.5 : 1;
        ctx.beginPath(); ctx.roundRect(node.x, node.y, node.w, node.h, 7); ctx.fill(); ctx.stroke();
        ctx.fillStyle = '#d6e6ed'; ctx.font = '12px system-ui';
        if (zoom > 0.4) {let label = node.label; while (ctx.measureText(label).width > node.w - 26 && label.length > 3) label = label.slice(0, -2); ctx.fillText(label + (label !== node.label ? '…' : ''), node.x + 12, node.y + 24);}
      }
      ctx.restore();
    }
    draw(); const observer = new ResizeObserver(draw); observer.observe(frame.current); return () => observer.disconnect();
  }, [graph, selected, zoom, offset]);
  useEffect(() => {if (graph && frame.current) fit();}, [graph]);
  function fit() {
    if (!graph || !frame.current) return;
    const scale = Math.min(1.5, (frame.current.clientWidth - 48) / Math.max(1, graph.width), (frame.current.clientHeight - 48) / Math.max(1, graph.height));
    setZoom(scale);
    setOffset({x: (frame.current.clientWidth - graph.width * scale) / 2, y: (frame.current.clientHeight - graph.height * scale) / 2});
  }
  return <>{embedded ? <div className="section-title"><div><div className="eyebrow">Explore what you know</div><h2>Your knowledge map</h2></div><a href={href('graph', '', record)}>Explore map ↗</a></div> : <><div className="eyebrow">See how ideas connect</div><h1>Graph explorer</h1><p className="lead muted">Start with a neighbourhood. Follow a typed relation back to its evidence.</p></>}
    <div className="graph-filters"><div className="segmented" role="group" aria-label="Graph lens">{['knowledge', 'research'].map(value => <button key={value} aria-pressed={mode === value} onClick={() => setMode(value)}>{value === 'knowledge' ? 'Knowledge' : 'Research'}</button>)}</div>{!embedded && <><button onClick={() => setDepth(x => (x + 1) % 4)} aria-label="Change neighbourhood depth">{depth} {depth === 1 ? 'hop' : 'hops'}</button><details className="relation-picker"><summary>{relation || 'Filter relations'}</summary><div className="filter-chips"><button aria-pressed={!relation} onClick={() => setRelation('')}>All relations</button>{['requires', 'supports', 'invalidates', 'tests', 'implements', 'cites', 'supersedes', 'part-of', 'addresses', 'decides', 'relates', 'about', 'teaches', 'applied-in'].map(type => <button key={type} aria-pressed={relation === type} onClick={() => setRelation(type)}>{type}</button>)}</div></details></>}</div>
    {focus && <p><a href={href('graph', '', record)}>← All hubs</a><span className="muted"> · Focus: {focus}</span></p>}
    {!graph ? <Notice error={result.error} retry={result.retry} /> : !graph.nodes.length ? <Empty title="No nodes in this lens"><p>Try another lens or add a course or research question from Overview.</p></Empty> : <>
      <div className="graph-toolbar"><button onClick={() => setZoom(x => Math.min(3, x * 1.25))} aria-label="Zoom in">+</button><button onClick={() => setZoom(x => Math.max(0.1, x / 1.25))} aria-label="Zoom out">−</button><button onClick={fit}>Fit graph</button><span className="muted">{graph.nodes.length} nodes · {graph.edges.length} relations</span></div>
      <div className="graph-frame" ref={frame}><canvas ref={canvas} tabIndex={0} aria-label="Interactive graph. Drag or use arrow keys to pan; plus and minus zoom, zero fits the map. The equivalent node list follows below."
        onKeyDown={e => {if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', '+', '-', '0', 'Escape'].includes(e.key)) {e.preventDefault(); if (e.key === '0') fit(); else if (e.key === '+') setZoom(x => Math.min(3, x * 1.25)); else if (e.key === '-') setZoom(x => Math.max(.1, x / 1.25)); else if (e.key === 'Escape') setSelected(''); else setOffset(p => ({x: p.x + (e.key === 'ArrowLeft' ? 30 : e.key === 'ArrowRight' ? -30 : 0), y: p.y + (e.key === 'ArrowUp' ? 30 : e.key === 'ArrowDown' ? -30 : 0)}));}}}
        onPointerDown={e => {e.currentTarget.setPointerCapture(e.pointerId); drag.current = {x: e.clientX, y: e.clientY, ox: offset.x, oy: offset.y, moved: false};}}
        onPointerMove={e => {if (drag.current) {const d = drag.current; if (Math.abs(e.clientX - d.x) + Math.abs(e.clientY - d.y) > 4) d.moved = true; if (d.moved) setOffset({x: d.ox + e.clientX - d.x, y: d.oy + e.clientY - d.y});}}}
        onPointerCancel={() => {drag.current = null;}}
        onPointerUp={e => {const d = drag.current; drag.current = null; if (d?.moved) return; const rect = e.currentTarget.getBoundingClientRect(), x = (e.clientX - rect.left - offset.x) / zoom, y = (e.clientY - rect.top - offset.y) / zoom; const n = graph.nodes.find(n => x >= n.x && x <= n.x + n.w && y >= n.y && y <= n.y + n.h); setSelected(n?.id || '');}} />
      </div><p className="graph-legend">Arrows follow the recorded source → target. Relation labels describe the connection; a link alone does not verify evidence.</p>
      {graph.bounded && <p className="notice">This view is bounded. Focus a node or reduce hops to explore the remaining connections.</p>}
      {selected && <section className="card"><h2>{graph.nodes.find(n => n.id === selected)?.label}</h2><p className="muted">{graph.nodes.find(n => n.id === selected)?.kind}</p><a className="button primary" href={entityHref(selected, record)}>Open evidence</a><a className="button" href={href('graph', selected, record)}>Focus neighbourhood</a></section>}
      <details open={!embedded}><summary>Accessible node list</summary><ul className="graph-node-list">{graph.nodes.map(n => <li key={n.id}><a href={entityHref(n.id, record)}>{n.label}</a><span>{n.kind}</span><a className="button" href={href('graph', n.id, record)} aria-label={'Focus ' + n.label}>Focus</a></li>)}</ul></details>
      <details><summary>Directed relations & provenance</summary><ul className="relation-list">{graph.edges.map((e, i) => <li key={i}><a href={entityHref(e.src, record)}>{graph.nodes.find(n => n.id === e.src)?.label || e.src}</a><strong> → {e.type} → </strong><a href={entityHref(e.dst, record)}>{graph.nodes.find(n => n.id === e.dst)?.label || e.dst}</a><small>{e.provenance || 'Provenance not recorded'}{e.verified == null ? '' : e.verified ? ' · verified' : ' · unverified'}</small></li>)}</ul></details>
    </>}
  </>;
}
