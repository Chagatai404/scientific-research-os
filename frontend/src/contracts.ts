export interface RecordInfo {name: string; title?: string; current: boolean; role: string; hub?: string}
export interface NodeData {id: string; type: string; title?: string; text?: string; status?: string; [key: string]: unknown}
export interface Relation {id: string; record: string; title: string; missing: boolean; edge: {src: string; dst: string; type: string; [key: string]: unknown}}
export interface Entity {id: string; record: string; node: NodeData; incoming: Relation[]; outgoing: Relation[]; truncated: number}
export interface Section {id: string; title: string; text: string; by?: string; locators?: unknown[]}
export interface DocumentData {schema: 'ros.document.v1'; id: string; record: string; title: string; kind: string; status: string; sections: Section[]; sources: {key: string; text: string}[]; source_hash: string; media_base: string; legacy: boolean}
export interface SearchResult {id: string; record: string; title: string; type: string; source: string}
export interface Resolution {status: 'resolved' | 'ambiguous' | 'missing'; matches: {id: string; record: string; title: string; anchor: string}[]}
export interface LibraryItem {id: string; title: string; status?: string; kind?: string; started?: string; closed?: boolean; ready?: boolean}
export interface Today {due: number; waiting_answers: number; waiting_questions: number; agent_tasks: number; next_lesson: {title: string; bundle: string; ready: boolean; missing?: string[]} | null}
export interface GraphNode {id: string; label: string; kind: string; cls?: string; tip?: string; canonical?: boolean; x: number; y: number; w: number; h: number; role?: string; parent?: string; cluster?: string; weight?: number; record?: string}
export interface GraphData {nodes: GraphNode[]; edges: {src: string; dst: string; type: string; provenance?: string | null; verified?: boolean | null; structure?: boolean}[]; width: number; height: number; title: string; focus?: string; progress?: {weeks: {week:string;answers:number;unaided_correct:number;reviews:number}[];due:number}; truncated?: number; bounded?: boolean}
export interface LessonStep {action: string; title?: string; reason?: string; item?: string; capability?: string; mode?: string; question?: {kind: string; prompt: string; options?: string[]}; content?: {animation?:import('./MediaArtifacts').PreparedAnimation;clip?:import('./MediaArtifacts').PreparedClip;live?: boolean; note?: string; segments?: {id: string; text: string; audio?: string}[]; visuals?: {path: string}[]; base?: string}}
export interface AnswerResult {verdict?: string; feedback?: string; explanation?: string; next?: LessonStep; pending?: boolean}
export interface QueueItem {kind: string; subject: string; title?: string; text?: string; headline?: string; record?: string; reason?: string}
export interface Evidence {subject: string; kind: string; node?: NodeData; title?: string; text?: string; verdict?: string; ownership?: string; assurance?: string; can_accept?: boolean; required?: string[]; steps?: Record<string, {verdict: string; by: string; notes?: string}>; artifacts?: string[]; citations?: {citation: string}[]; adversary_memo?: string; authorizes?: string; plan?: Record<string, unknown>; links?: {vault?: {obsidian: string}; handouts?: LibraryItem[]}; [key: string]: unknown}

export interface Folder {id: string; title: string; kind: 'course' | 'project' | 'collection'; parent: string}
export interface SessionRow {id: string; title: string; kind: string; parent: string}
export interface Material {id: string; title: string; kind: string; parent: string; state: 'added' | 'reading' | 'ready' | 'attention'; detail: string; source: string; path: string; indexed: boolean; added: string}
export interface Organization {workspace: {name: string; title: string}; folders: Folder[]; sessions: SessionRow[]; library: Material[]; names: Record<string, string>; parents: Record<string, string>}
export interface MapNode {id: string; label: string; kind: string; role: 'center' | 'hub' | 'topic' | 'source'; tip: string; parent: string; cluster: string; weight: number; record: string; canonical: boolean}
export interface MapEdge {src: string; dst: string; type: string; structure: boolean; provenance?: string | null; verified?: boolean | null}
export interface OrganizationMap {center: string; title: string; nodes: MapNode[]; edges: MapEdge[]; needs_organization: {id: string; kind: string; reason: string; record: string}[]; needs_count: number; omitted: Record<string, number>; counts: {nodes: number; hubs: number}}

export function validateDocument(value: unknown): DocumentData {
  if (!value || typeof value !== 'object') throw new Error('Invalid document response');
  const doc = value as DocumentData;
  if (doc.schema !== 'ros.document.v1' || typeof doc.id !== 'string' || typeof doc.source_hash !== 'string'
      || !Array.isArray(doc.sections) || !doc.sections.every(s => typeof s.id === 'string' && typeof s.text === 'string' && typeof s.title === 'string')) {
    throw new Error('This document format is unsupported. Update Research OS to read it.');
  }
  return doc;
}
