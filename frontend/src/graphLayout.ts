import type {GraphData, GraphNode, OrganizationMap} from './contracts';
export interface PointNode extends GraphNode {px: number; py: number; group: number; r?: number; color?: string}

/* Organizational map: workspace at the centre, courses and projects around it, topics and material branching outward.
   Position comes only from the tree and sorted ids, so it is stable and needs no simulation. Colour is keyed to the
   course or project's identity, never to array order. Size is organizational prominence, never a truth or mastery score. */
export const PALETTE = ['#8db8ff', '#7fd1b9', '#e6b86a', '#d78fb8', '#a3a8ff', '#e49479', '#7fcfe0', '#b6d57b'];
export const NEUTRAL = '#9aa5b1';
export const colorFor = (id: string) => {let h = 2166136261; for (const c of id) h = Math.imul(h ^ c.charCodeAt(0), 16777619); return PALETTE[(h >>> 0) % PALETTE.length];};
const log = (n: number, cap: number) => Math.min(cap, Math.log2(1 + Math.max(0, n)));
export function radiusFor(role: string, weight: number, children: number) {
  return role === 'center' ? 22 : role === 'hub' ? 13 + log(children, 5) : role === 'topic' ? 7 + log(weight, 5) : 4 + log(weight, 3);
}
const ORDER: Record<string, number> = {hub: 0, topic: 1, source: 2};
export function mapLayout(map: OrganizationMap) {
  const byId = new Map(map.nodes.map(n => [n.id, n]));
  const children = new Map<string, string[]>();
  for (const n of map.nodes) {
    if (n.role === 'center') continue;
    const parent = n.role === 'hub' || !byId.has(n.parent) ? map.center : n.parent;
    children.set(parent, [...(children.get(parent) || []), n.id]);
  }
  for (const list of children.values()) list.sort((a, b) => ORDER[byId.get(a)!.role] - ORDER[byId.get(b)!.role] || byId.get(a)!.label.localeCompare(byId.get(b)!.label) || a.localeCompare(b));
  const leaves = new Map<string, number>();
  const count = (id: string, seen = new Set<string>()): number => {
    if (leaves.has(id)) return leaves.get(id)!;
    if (seen.has(id)) return 1;
    seen.add(id);
    const kids = children.get(id) || [];
    const value = kids.length ? kids.reduce((sum, k) => sum + count(k, seen), 0) : 1;
    leaves.set(id, value); return value;
  };
  count(map.center);
  const depth = new Map<string, number>([[map.center, 0]]), perDepth = new Map<number, number>();
  const walk = (id: string) => {for (const k of children.get(id) || []) {if (depth.has(k)) continue; depth.set(k, depth.get(id)! + 1); perDepth.set(depth.get(k)!, (perDepth.get(depth.get(k)!) || 0) + 1); walk(k);}};
  walk(map.center);
  const ring = (d: number) => {let r = 0; for (let i = 1; i <= d; i++) r = Math.max(r + (i === 1 ? 250 : 130), (perDepth.get(i) || 0) * 40 / (2 * Math.PI)); return r;};
  const points = new Map<string, PointNode>();
  const place = (id: string, a0: number, a1: number) => {
    const n = byId.get(id)!, angle = (a0 + a1) / 2, r = ring(depth.get(id) || 0);
    const kids = children.get(id) || [], color = n.role === 'center' ? '#e8ecf0' : n.kind === 'inbox' ? NEUTRAL : colorFor(n.cluster);
    points.set(id, {id, label: n.label, kind: n.kind, tip: n.tip, canonical: n.canonical, x: 0, y: 0, w: 0, h: 0, role: n.role, parent: n.parent, cluster: n.cluster, weight: n.weight, record: n.record,
      px: n.role === 'center' ? 0 : Math.cos(angle) * r, py: n.role === 'center' ? 0 : Math.sin(angle) * r, group: 0, r: radiusFor(n.role, n.weight, kids.length), color});
    const total = kids.reduce((sum, k) => sum + Math.pow(leaves.get(k) || 1, .75), 0);
    let cursor = a0;
    for (const k of kids) {const share = Math.pow(leaves.get(k) || 1, .75) / total * (a1 - a0); place(k, cursor, cursor + share); cursor += share;}
  };
  place(map.center, -Math.PI / 2, Math.PI * 1.5);
  return {nodes: [...points.values()], groups: [] as {x: number; y: number; radius: number; label: string}[]};
}
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
