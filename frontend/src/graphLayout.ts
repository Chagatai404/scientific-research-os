import type {MapNode, OrganizationMap} from './contracts';

export interface Camera {x: number; y: number; zoom: number}
export interface MapPoint extends MapNode {px: number; py: number; r: number; color: string}

/* The central map: workspace in the middle, then Knowledge, Research and Goals, then their places, then topics.
   Position comes only from the tree and sorted ids, so it is stable and needs no simulation. Colour says which of the
   three a node belongs to. Size is organizational prominence (role first, then connections), never a truth or mastery score. */
export const CATEGORY_COLOR: Record<string, string> = {knowledge: '#6aa9ff', research: '#4fd1a5', goals: '#f4c150'};
export const CENTER_COLOR = '#e8ecf0';
export const colorFor = (category: string) => CATEGORY_COLOR[category] || '#9aa5b1';
const log = (n: number, cap: number) => Math.min(cap, Math.log2(1 + Math.max(0, n)));
export function radiusFor(role: string, weight: number, children: number) {
  return role === 'center' ? 22 : role === 'category' ? 16 : role === 'hub' ? 9 + log(children, 4) : role === 'topic' ? 4 + log(weight, 3) : 3 + log(weight, 2);
}
const ORDER: Record<string, number> = {category: 0, hub: 1, topic: 2, source: 3};
const CATEGORY_ORDER = ['knowledge', 'research', 'goals'];

/* Rings for the structure, clusters for the detail: the workspace sits in the middle, its three branches on a ring around it, the places
   (courses, projects, goals) on a larger ring, and everything filed in a place is packed in a sunflower cluster just outside it, so a big
   course never smears across the whole map. */
const GOLDEN = 2.399963229728653;
const clusterRadius = (n: number) => n ? 9 * Math.sqrt(n) + 8 : 0;
export function mapLayout(map: OrganizationMap): MapPoint[] {
  const byId = new Map(map.nodes.map(n => [n.id, n]));
  const children = new Map<string, string[]>();
  for (const n of map.nodes) {
    if (n.role === 'center') continue;
    const parent = byId.has(n.parent) ? n.parent : map.center;
    children.set(parent, [...(children.get(parent) || []), n.id]);
  }
  for (const list of children.values()) list.sort((a, b) => ORDER[byId.get(a)!.role] - ORDER[byId.get(b)!.role] || byId.get(a)!.label.localeCompare(byId.get(b)!.label) || a.localeCompare(b));
  const points = new Map<string, MapPoint>();
  const put = (id: string, px: number, py: number) => {
    const n = byId.get(id)!;
    points.set(id, {...n, px, py, r: radiusFor(n.role, n.weight, (children.get(id) || []).length), color: n.role === 'center' ? CENTER_COLOR : colorFor(n.category)});
  };
  put(map.center, 0, 0);
  const cats = (children.get(map.center) || []).filter(id => byId.get(id)!.role === 'category').sort((a, b) => CATEGORY_ORDER.indexOf(byId.get(a)!.category) - CATEGORY_ORDER.indexOf(byId.get(b)!.category));
  const stray = (children.get(map.center) || []).filter(id => !cats.includes(id));
  // A slot is one place plus the cluster of what is filed in it; a category's own loose topics form a slot with no place node.
  interface Slot {id: string; cat: string; kids: string[]; width: number}
  const slots: Slot[] = [];
  for (const cat of cats) {
    const own = children.get(cat) || [];
    for (const id of own.filter(i => byId.get(i)!.role === 'hub')) {const kids = children.get(id) || []; slots.push({id, cat, kids, width: 2 * clusterRadius(kids.length) + 44});}
    const loose = own.filter(i => byId.get(i)!.role !== 'hub');
    if (loose.length) slots.push({id: '', cat, kids: loose, width: 2 * clusterRadius(loose.length) + 44});
  }
  const total = slots.reduce((sum, s) => sum + s.width, 0) || 1;
  const outer = Math.max(260, total / (2 * Math.PI)), inner = Math.min(130, outer - 120);
  let cursor = -Math.PI / 2;
  const cluster = (kids: string[], cx: number, cy: number, radius: number) => kids.forEach((id, k) => {
    const rr = radius * Math.sqrt((k + .5) / kids.length), a = k * GOLDEN;
    put(id, cx + Math.cos(a) * rr, cy + Math.sin(a) * rr);
  });
  for (const cat of cats) {
    const mine = slots.filter(s => s.cat === cat), span = mine.reduce((sum, s) => sum + s.width, 0) / total * 2 * Math.PI;
    const mid = cursor + span / 2;
    put(cat, Math.cos(mid) * inner, Math.sin(mid) * inner);
    let at = cursor;
    for (const slot of mine) {
      const share = slot.width / total * 2 * Math.PI, angle = at + share / 2, cr = clusterRadius(slot.kids.length);
      const hx = Math.cos(angle) * outer, hy = Math.sin(angle) * outer;
      const hubR = slot.id ? radiusFor('hub', 0, slot.kids.length) : 0, out = hubR + cr + 10;
      if (slot.id) put(slot.id, hx, hy);
      cluster(slot.kids, hx + Math.cos(angle) * out, hy + Math.sin(angle) * out, cr);
      at += share;
    }
    cursor += span;
  }
  stray.forEach((id, k) => put(id, 0, 60 + k * 30));
  return [...points.values()];
}

export function safeCamera(raw: string): Camera | null {
  try {const c = JSON.parse(raw); return c && typeof c.x === 'number' && typeof c.y === 'number' && typeof c.zoom === 'number' && Number.isFinite(c.x) && Number.isFinite(c.y) && Number.isFinite(c.zoom) && Math.abs(c.x) < 100000 && Math.abs(c.y) < 100000 && c.zoom >= .12 && c.zoom <= 4 ? {x: c.x, y: c.y, zoom: c.zoom} : null;} catch {return null;}
}
export function zoomAt(camera: Camera, factor: number, x: number, y: number): Camera {
  const zoom = Math.min(4, Math.max(.12, camera.zoom * factor)), ratio = zoom / camera.zoom;
  return {x: x - (x - camera.x) * ratio, y: y - (y - camera.y) * ratio, zoom};
}
