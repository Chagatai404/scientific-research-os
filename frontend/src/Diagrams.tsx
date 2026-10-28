import {useEffect, useId, useState} from 'react';
export function Mermaid({text}: {text: string}) {
  const id = useId().replaceAll(':', ''), [svg, setSvg] = useState(''), [error, setError] = useState(''), [open, setOpen] = useState(false);
  useEffect(() => {if (!open) return; let active = true; import('mermaid').then(async ({default: mermaid}) => {
    mermaid.initialize({startOnLoad: false, securityLevel: 'strict', theme: document.documentElement.dataset.theme === 'light' ? 'default' : 'dark', maxTextSize: 20000, suppressErrorRendering: true, flowchart: {htmlLabels: false}});
    const result = await mermaid.render('diagram-' + id, text.slice(0, 20000));
    const doc = new DOMParser().parseFromString(result.svg, 'image/svg+xml');
    doc.querySelectorAll('script,foreignObject,iframe,object,use,image,a').forEach(node => node.remove());
    doc.querySelectorAll('*').forEach(node => {for (const attr of [...node.attributes]) if (/^on/i.test(attr.name) || /href/i.test(attr.name)) node.removeAttribute(attr.name);});
    if (active) setSvg(new XMLSerializer().serializeToString(doc.documentElement));
  }).catch(error => {if (active) setError('Diagram unavailable: ' + (error instanceof Error ? error.message.slice(0,300) : 'invalid source') + '. Its source is preserved below.');}); return () => {active = false;};}, [open, text, id]);
  return <span className="diagram"><button onClick={() => setOpen(!open)}>{open ? 'Hide Diagram' : 'Load Diagram'}</button>{open && <>{svg ? <img alt="Mermaid diagram" src={'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg)}/> : <span role="status">{error || 'Rendering diagram…'}</span>}<code className="diagram-source">{text}</code></>}</span>;
}
interface Shape {id: string; type: string; x: number; y: number; width: number; height: number; text?: string; strokeColor?: string; backgroundColor?: string; points?: number[][]; isDeleted?: boolean}
export function Excalidraw({src, alt}: {src: string; alt: string}) {
  const [shapes, setShapes] = useState<Shape[]|null>(null), [error, setError] = useState('');
  useEffect(() => {const abort = new AbortController(); fetch(src, {signal: abort.signal}).then(async response => {
    if (!response.ok || Number(response.headers.get('Content-Length')) > 2 * 1024 * 1024) throw new Error();
    const text = await response.text(); if (text.length > 2 * 1024 * 1024) throw new Error(); const doc = JSON.parse(text);
    if (doc.type !== 'excalidraw' || !Array.isArray(doc.elements)) throw new Error();
    setShapes(doc.elements.filter((s: Shape) => !s.isDeleted && ['rectangle','ellipse','diamond','text','line','arrow','freedraw'].includes(s.type) && [s.x,s.y,s.width,s.height].every(v => Number.isFinite(v) && Math.abs(v) < 100000)).slice(0, 1000));
  }).catch(() => {if (!abort.signal.aborted) setError('Preview unavailable. Open the original drawing.');}); return () => abort.abort();}, [src]);
  const color = (value?: string) => value && /^(#[0-9a-f]{3,8}|transparent)$/i.test(value) ? value : 'currentColor';
  const left = Math.min(0, ...(shapes || []).map(s => s.x)), top = Math.min(0, ...(shapes || []).map(s => s.y));
  const width = Math.max(200, ...(shapes || []).map(s => s.x + s.width - left)), height = Math.max(100, ...(shapes || []).map(s => s.y + s.height - top));
  return <span className="drawing-preview">{shapes ? <svg role="img" aria-label={alt} viewBox={`${left-20} ${top-20} ${width+40} ${height+40}`}>{shapes.map(s => <g key={s.id} transform={`translate(${s.x} ${s.y})`} stroke={color(s.strokeColor)} fill={s.backgroundColor === 'transparent' ? 'none' : color(s.backgroundColor)} strokeWidth="2">{s.type === 'text' ? <text stroke="none" fill={color(s.strokeColor)}>{(s.text || '').split('\n').map((line,i) => <tspan x="0" dy={i ? '1.3em' : '1em'} key={i}>{line}</tspan>)}</text> : s.type === 'ellipse' ? <ellipse cx={s.width/2} cy={s.height/2} rx={Math.abs(s.width/2)} ry={Math.abs(s.height/2)}/> : s.type === 'diamond' ? <polygon points={`${s.width/2},0 ${s.width},${s.height/2} ${s.width/2},${s.height} 0,${s.height/2}`}/> : ['line','arrow','freedraw'].includes(s.type) ? <polyline fill="none" points={(s.points || []).filter(p => p.length === 2 && p.every(Number.isFinite)).map(p => p.join(',')).join(' ')}/> : <rect width={Math.abs(s.width)} height={Math.abs(s.height)} rx="4"/>}</g>)}</svg> : <span>{error || 'Loading drawing…'}</span>}<a href={src} download>Open / Edit Original Drawing</a></span>;
}
