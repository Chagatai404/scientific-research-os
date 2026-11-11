export interface RecordInfo {name: string; title?: string; current: boolean; role: string; hub?: string; workspace_id?: string}
/** Physical provenance stays separate from the logical workspace currently selected. */
export interface QualifiedRef {owner_record: string; entity_id: string; revision?: string | number}
export interface WorkspaceIdentity {
  schema: 'ros.workspace.v1'; workspace_id: string; kind: 'course' | 'project' | 'general' | 'record';
  hub: QualifiedRef | null; record: string; owner_record: string; title: string; aliases: QualifiedRef[]; selected_record?: string;
}
export type WorkspaceGroup = 'sessions' | 'sources' | 'handouts' | 'research' | 'other';
export interface WorkspaceWork {
  ref: QualifiedRef; owner_record: string; workspace_id: string; kind: string; title: string;
  provenance: {basis: string[]; assignment: 'legacy' | 'person'};
  handout_kind?: 'lecture' | 'recitation' | 'chapter' | string; source_hash?: string;
  state?: string; status?: string; source?: string; format?: string; path?: string;
}
export interface WorkspaceCatalog {schema: 'ros.workspace-catalog.v1'; workspaces: WorkspaceIdentity[]}
export interface WorkspaceOverview {
  schema: 'ros.workspace-overview.v1'; workspace: WorkspaceIdentity; workspace_id: string;
  groups: Record<WorkspaceGroup, WorkspaceWork[]>; counts: Record<WorkspaceGroup, number>; missing: QualifiedRef[];
}
export interface WorkspaceResolution {
  schema: 'ros.workspace-resolution.v1'; status: 'resolved' | 'ambiguous' | 'missing'; matches: WorkspaceIdentity[];
}
export interface CapabilityIdentity {
  schema: 'ros.capability-identity.v1'; ref: QualifiedRef; canonical: QualifiedRef;
  equivalence_status: 'distinct' | 'verified' | 'stale'; evidence_refs: QualifiedRef[];
}
export interface NodeData {id: string; type: string; title?: string; text?: string; status?: string; [key: string]: unknown}
export interface Relation {id: string; record: string; title: string; missing: boolean; edge: {src: string; dst: string; type: string; [key: string]: unknown}}
export interface Entity {id: string; record: string; node: NodeData; incoming: Relation[]; outgoing: Relation[]; truncated: number}
export interface Section {id: string; title: string; text: string; by?: string; locators?: unknown[]}
export interface DocumentData {schema: 'ros.document.v1'; id: string; record: string; title: string; kind: string; status: string; sections: Section[]; sources: {key: string; text: string}[]; source_hash: string; media_base: string; legacy: boolean; acceptance?: {state: 'draft' | 'read' | 'in-vault' | 'accepted'; source_hash: string; in_vault: boolean}}
export interface SearchResult {id: string; record: string; title: string; type: string; source: string}
export interface Resolution {status: 'resolved' | 'ambiguous' | 'missing'; matches: {id: string; record: string; title: string; anchor: string}[]}
export interface LibraryItem {id: string; title: string; status?: string; kind?: string; started?: string; closed?: boolean; ready?: boolean}
export interface Today {due: number; waiting_answers: number; waiting_questions: number; agent_tasks: number; next_lesson: {title: string; bundle: string; ready: boolean; missing?: string[]} | null}
export interface GraphNode {id: string; label: string; kind: string; cls?: string; tip?: string; canonical?: boolean; x: number; y: number; w: number; h: number; role?: string; parent?: string; cluster?: string; weight?: number; record?: string}
export interface GraphData {nodes: GraphNode[]; edges: {src: string; dst: string; type: string; provenance?: string | null; verified?: boolean | null; structure?: boolean}[]; width: number; height: number; title: string; focus?: string; progress?: {weeks: {week:string;answers:number;unaided_correct:number;reviews:number}[];due:number}; truncated?: number; bounded?: boolean}
export interface LessonStep {action: string; title?: string; reason?: string; item?: string; capability?: string; mode?: string; question?: {kind: string; prompt: string; options?: string[]}; content?: {animation?:import('./MediaArtifacts').PreparedAnimation;clip?:import('./MediaArtifacts').PreparedClip;live?: boolean; note?: string; segments?: {id: string; text: string; audio?: string}[]; visuals?: {path: string}[]; base?: string}}
export interface AnswerResult {attempt?: string; verdict?: string; feedback?: string; explanation?: string; next?: LessonStep; pending?: boolean}
export interface QueueItem {kind: string; subject: string; title?: string; text?: string; headline?: string; record?: string; reason?: string; source_hash?: string}
export interface Evidence {subject: string; kind: string; node?: NodeData; title?: string; text?: string; verdict?: string; ownership?: string; assurance?: string; can_accept?: boolean; required?: string[]; steps?: Record<string, {verdict: string; by: string; notes?: string}>; artifacts?: string[]; citations?: {citation: string}[]; adversary_memo?: string; authorizes?: string; plan?: Record<string, unknown>; links?: {vault?: {obsidian: string}; handouts?: LibraryItem[]}; [key: string]: unknown}

export interface Folder {id: string; title: string; kind: 'course' | 'project' | 'collection'; parent: string}
/** `record` and `workspace` are set only on a session listed from another (linked) workspace, e.g. a project's session in Knowledge. */
export interface SessionRow {id: string; title: string; kind: string; parent: string; record?: string; workspace?: string}
export interface Material {id: string; title: string; kind: string; parent: string; state: 'added' | 'reading' | 'ready' | 'attention'; detail: string; source: string; path: string; indexed: boolean; added: string}
export interface Organization {workspace: {name: string; title: string}; folders: Folder[]; sessions: SessionRow[]; library: Material[]; archived?: {id: string; title: string; kind: string; record?: string; workspace?: string}[]; names: Record<string, string>; parents: Record<string, string>}
export interface MapNode {id: string; label: string; kind: string; role: 'center' | 'category' | 'hub' | 'topic' | 'source'; category: string; tip: string; parent: string; cluster: string; weight: number; record: string; canonical: boolean; material: number; decision?: string}
export interface MapEdge {src: string; dst: string; type: string; structure: boolean; cross: boolean; provenance?: string | null; verified?: boolean | null}
export interface OrganizationMap {center: string; title: string; nodes: MapNode[]; edges: MapEdge[]; needs_organization: {id: string; kind: string; reason: string; record: string}[]; needs_count: number; counts: {nodes: number; hubs: number}}

export function validateDocument(value: unknown): DocumentData {
  if (!value || typeof value !== 'object') throw new Error('Invalid document response');
  const doc = value as DocumentData;
  if (doc.schema !== 'ros.document.v1' || typeof doc.id !== 'string' || typeof doc.source_hash !== 'string'
      || !Array.isArray(doc.sections) || !doc.sections.every(s => typeof s.id === 'string' && typeof s.text === 'string' && typeof s.title === 'string')) {
    throw new Error('This document format is unsupported. Update Research OS to read it.');
  }
  return doc;
}

/** A configured model connection (`provider_profiles`): never holds a key, only where the key is stored. */
export type CredentialReference = {store: 'env' | 'os'; name: string};
export interface ProviderProfile {
  schema: string; id: string; provider: 'codex' | 'claude' | 'ollama' | 'compatible' | 'api'; kind: 'subscription' | 'local' | 'remote'; auth: string; transport: string;
  endpoint: string; model: string; tools: boolean; vision: boolean; context_limit: number; credential: CredentialReference | null;
  capabilities: Record<'streaming' | 'tools' | 'vision' | 'cancel', boolean>;
}
export type EvidenceStatus = 'declared' | 'tested' | 'live-verified' | 'unsupported';
export interface ProviderCapabilities {
  schema: string; statuses: EvidenceStatus[];
  profiles: {id: string; provider: string; kind: string; declared: Record<string, boolean>; evidence: Record<string, EvidenceStatus>; credential: CredentialReference | null}[];
}
export type CredentialStatus = 'present' | 'missing' | 'unavailable' | 'invalid';
/** A custom agent manifest as `agent_list` returns it (instructions are left out). */
export interface AgentManifestRow {id: string; version: number; title: string; base: string; tools: string[]; profile: string; hash: string; requires: string[]; limits: Record<string, number>}

/** The four reading states are separate facts: a stored scan is never "read" until a person accepts a transcription of that revision. */
export interface ReadingStates {stored: boolean; text_readable: boolean; indexed: boolean; verified: boolean}
export interface LibraryMaterial {
  id: string; ref: QualifiedRef; title: string; path: string; source: string; place: string; format: string; state: Material['state']; detail: string;
  local_only: boolean; states: ReadingStates; read_basis: 'extracted_text' | 'reviewed_transcription' | null; stale: boolean; label: string; same_name_as: string[];
}
export interface LiteratureOrigin {
  origin: 'library' | 'scholarly' | 'web'; operation?: string; engine?: string; url?: string; retrieved_at?: string; ref?: QualifiedRef; place?: string; path?: string;
  snippet?: string; captured?: boolean; untrusted?: boolean; local_only?: boolean; access?: string; verification_status?: string; fetched_at?: string;
}
/** One deduplicated discovery result. A candidate is never evidence; `local_only` is true if any component is. */
export interface LiteratureCandidate {
  schema: string; key: string; title: string; doi: string | null; arxiv_id: string | null; year?: number | null; urls: string[]; refs: QualifiedRef[];
  origins: LiteratureOrigin[]; states: ReadingStates; local_only: boolean; evidence: false; note: string;
}
export interface LiteratureCandidates {schema: string; query: string; workspace_id: string | null; candidates: LiteratureCandidate[]; counts: {candidates: number; items_before_merge: number}}
export interface WebEngines {
  schema: string; status: 'configured' | 'none_configured'; message: string;
  engines: {id: string; engine: string; label: string; endpoint: string; credential: CredentialReference | null; enabled: boolean; evidence: string}[];
}
export interface OperationRow {id: string; kind: string; state: string; result?: {ok: boolean; error?: string}}

/** `graph_view`: the living graph, derived on every read. Agents keep its notes; the person only reads it. */
export interface LivingNode {
  id: string; kind: string; title: string; ref: QualifiedRef; group?: string; state?: string; status?: string; workspace_kind?: string;
  signal?: 'known' | 'shaky' | 'new'; due?: boolean; ready?: boolean; frontier?: boolean; blocked_by?: string[]; next_review?: string | null;
  last_retrieval?: string | null; evidence?: string; reference?: boolean;
  note_kind?: string; text?: string; revision?: number; added_by?: string; updated_by?: string; updated_at?: string; workspace_id?: string;
  cites?: {owner_record: string; event: string; type: string}[]; work?: QualifiedRef[];
}
export interface LivingEdge {src: string; dst: string; type: string; origin: 'record' | 'note' | string}
export interface LivingGraph {
  schema: 'ros.living-graph.v1'; scope: 'workspace' | 'personal'; workspace_id: string | null; as_of: string;
  nodes: LivingNode[]; edges: LivingEdge[]; counts: Record<string, number>; truncated: {nodes?: number; shown?: number; workspaces_omitted?: number} | null; digest: string;
}
export interface TeachingCap {id: string; title: string; state: string; next_review: string | null; ref: QualifiedRef; blocked_by?: string[]; evidence?: string; notes?: {note: string; kind: string; title: string; revision: number; ref: QualifiedRef}[]}
/** `graph_teaching`: bounded lists with their own totals, so a view can say what it leaves out. */
export interface TeachingSignals {
  schema: 'ros.teaching-signals.v1'; workspace_id: string | null; as_of: string;
  known: TeachingCap[]; shaky: TeachingCap[]; due: TeachingCap[];
  goal_gaps: {goal: string; title: string; source: 'note' | 'record'; ref: QualifiedRef; targets: number; missing: TeachingCap[]}[];
  misconceptions: {note: string; title: string; text: string; revision: number; about: string[]; cites: {owner_record: string; event: string; type: string}[]; updated_at: string; ref: QualifiedRef}[];
  next: {id: string; why: string; ref: QualifiedRef}[]; totals: Record<'known' | 'shaky' | 'due' | 'goal_gaps' | 'misconceptions' | 'next', number>;
  limits: {per_list: number; graph_truncated: boolean}; digest: string;
}
/** What `research_journey` adds to each question: the ids of the hypotheses, experiments and claims its stage is read from. */
export interface JourneyEvidence {hypotheses: string[]; experiments: string[]; claims: string[]}
