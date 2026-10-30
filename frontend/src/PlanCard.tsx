import {call} from './api';
import {DependencyPlan, type ClassroomMap} from './Classroom';
import {useResource} from './hooks';

interface Waiting {id: string; kind: string; state: string; brief?: string; hub?: string; ref?: string; bundle?: string}
const KIND_LABELS: Record<string, string> = {outline: 'Outline the capabilities', scout: 'Find the sources', item: 'Write probe and practice questions', narration: 'Write the narration', job: 'Record the audio', visual: 'Draw the figures', animation: 'Animate it', bundle: 'Assemble the lesson', handout: 'Write the handout', review: 'Review'};

/** What is being prepared for the goal a session started, until its lesson begins: the dependency map so far and the
 * preparation still waiting. Read-only; the dispatcher works the focused tasks first. */
export function PlanCard({hub, record}: {hub: string; record: string}) {
  const plan = useResource('plan:' + record + ':' + hub, async signal => {
    const [map, waiting] = await Promise.all([call<ClassroomMap>('map', {scope: hub}, record, false, signal).catch(() => undefined), call<Waiting[]>('tasks', {}, record, false, signal)]);
    const nodes = new Set([hub, ...(map?.nodes.map(n => n.id) || [])]);
    const mine = waiting.filter(t => nodes.has(t.hub || '') || nodes.has(t.ref || '') || (t.bundle && nodes.has('capability:' + t.bundle)));
    return {map, mine};
  }, record);
  if (!plan.data) return null;
  const {map, mine} = plan.data;
  return <section className="lesson-card plan-card" aria-label="Study plan being prepared"><header><div><div className="eyebrow">Preparing your lesson</div><h2>Study plan</h2></div></header>
    <p className="muted">Built from your notes, your paper library and your projects' code and records. What you asked for is prepared before other background work.</p>
    <DependencyPlan map={map} record={record} />
    {mine.length > 0 ? <><h3>Still being prepared</h3><ul className="prep-list">{mine.map(t => <li key={t.id}><strong>{KIND_LABELS[t.kind] || t.kind}</strong> <small>{t.state === 'claimed' ? 'An agent is on it' : 'Waiting'}{['visual', 'animation'].includes(t.kind) ? ' · needs a shell-capable agent (Claude Code or Codex)' : ''}</small></li>)}</ul></> : <p className="muted">Nothing is waiting: the tutor can start the first lesson.</p>}
  </section>;
}
