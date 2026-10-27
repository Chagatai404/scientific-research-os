import type {GraphData, GraphNode} from './contracts';
export interface PointNode extends GraphNode {px: number; py: number; group: number}
export interface Camera {x: number; y: number; zoom: number}
export function pointLayout(graph: GraphData) {
  const sorted = [...graph.nodes].sort((a, b) => a.id.localeCompare(b.id));
  const parent = new Map(sorted.map(n => [n.id, n.id]));
  function root(id: string): string {const p = parent.get(id)!; if (p !== id) parent.set(id, root(p)); return parent.get(id)!;}
  for (const e of graph.edges) if (parent.has(e.src) && parent.has(e.dst)) {const a = root(e.src), b = root(e.dst); if (a !== b) parent.set(a < b ? b : a, a < b ? a : b);}
  const components = new Map<string, GraphNode[]>();
  for (const n of sorted) {const key = root(n.id); if (!components.has(key)) components.set(key, []); components.get(key)!.push(n);}
  const clusters = [...components.values()].sort((a, b) => b.length - a.length || a[0].id.localeCompare(b[0].id));
  const columns = Math.max(1, Math.ceil(Math.sqrt(clusters.length * 1.5)));
  const cell = Math.max(210, ...clusters.map(c => Math.sqrt(c.length) * 70 + 120));
  const nodes: PointNode[] = [], groups: {x: number; y: number; radius: number; label: string}[] = [];
  // Sorted IDs and a bounded sunflower layout avoid an idle simulation or server lane geometry.
  // Connected components are presentation groups, never new domain relations.
  clusters.forEach((cluster, group) => {
    const x = cell * (group % columns + .5), y = cell * (Math.floor(group / columns) + .5);
    const radius = Math.max(58, Math.sqrt(cluster.length) * 31);
    groups.push({x, y, radius: radius + 32, label: (cluster.find(n => /course|project|question|bundle/.test(n.kind)) || cluster[0]).label});
    cluster.forEach((n, i) => {const angle = i * 2.399963229728653, r = cluster.length === 1 ? 0 : Math.sqrt((i + .4) / cluster.length) * radius; nodes.push({...n, px: x + Math.cos(angle) * r, py: y + Math.sin(angle) * r, group});});
  });
  return {nodes, groups};
}
export function safeCamera(raw: string): Camera | null {
  try {const c = JSON.parse(raw); return c && typeof c.x === 'number' && typeof c.y === 'number' && typeof c.zoom === 'number' && Number.isFinite(c.x) && Number.isFinite(c.y) && Number.isFinite(c.zoom) && Math.abs(c.x) < 100000 && Math.abs(c.y) < 100000 && c.zoom >= .12 && c.zoom <= 4 ? {x: c.x, y: c.y, zoom: c.zoom} : null;} catch {return null;}
}
export function zoomAt(camera: Camera, factor: number, x: number, y: number): Camera {
  const zoom = Math.min(4, Math.max(.12, camera.zoom * factor)), ratio = zoom / camera.zoom;
  return {x: x - (x - camera.x) * ratio, y: y - (y - camera.y) * ratio, zoom};
}
