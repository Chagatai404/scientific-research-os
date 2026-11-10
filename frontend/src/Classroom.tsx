import {useEffect, useState, type ReactNode} from 'react';
import {entityHref} from './api';
import {RichText} from './Document';
import type {DocumentData, LessonStep} from './contracts';

export interface ClassroomMap {nodes: {id: string; title: string; state?: string; prerequisites: string[]; blocked_by: string[]; next_review?: string; ready: boolean}[]; edges: {src: string; dst: string}[]}

export function DependencyPlan({map, active, record}: {map?: ClassroomMap; active?: string; record: string}) {
  if (!map?.nodes.length) return <p className="muted">No capability dependencies have been recorded for this session.</p>;
  const titles = new Map(map.nodes.map(node => [node.id, node.title]));
  return <><p className="muted">Recorded evidence and prerequisites. An active step does not establish mastery.</p><ol className="dependency-plan">{map.nodes.map(node => <li key={node.id} aria-current={node.id === active ? 'step' : undefined}>
    <a href={entityHref(node.id, record)}>{node.title}</a><small>{node.id === active ? 'Current step · ' : ''}{node.state || 'Unknown'}{node.ready ? ' · Ready' : ''}</small>
    {node.prerequisites.length > 0 && <p>Requires {node.prerequisites.map((id, index) => <span key={id}>{index > 0 && ', '}<a href={entityHref(id, record)}>{titles.get(id) || id}</a></span>)}</p>}
    {node.blocked_by.length > 0 && <p>Waiting on {node.blocked_by.map(id => titles.get(id) || id).join(', ')}</p>}
    {node.next_review && <small>Review: {node.next_review}</small>}
  </li>)}</ol></>;
}

export function Classroom({title, phase, reason, record, lesson, map, transcript, contextError, question, children, active, questionOpen}: {title: string; phase: string; reason?: string; record: string; lesson: string; map?: ClassroomMap; transcript?: DocumentData; contextError?: string; question: ReactNode; children: ReactNode; active?: string; questionOpen?: boolean}) {
  const [panel, setPanel] = useState<'plan' | 'questions' | null>(null);
  useEffect(() => {if (questionOpen !== undefined) setPanel(questionOpen ? 'questions' : null);}, [questionOpen]);
  return <div className="learning-session classroom"><header className="classroom-heading"><div><div className="eyebrow">{phase}</div><h1>{title}</h1></div><nav aria-label="Session context"><button aria-expanded={panel === 'plan'} aria-controls="classroom-context" onClick={() => setPanel(panel === 'plan' ? null : 'plan')}>Plan</button><button aria-expanded={panel === 'questions'} aria-controls="classroom-context" onClick={() => setPanel(panel === 'questions' ? null : 'questions')}>Questions</button></nav></header>
    <div className={'classroom-layout' + (panel ? ' has-panel' : '')}><div className="classroom-reading">
      {transcript && <details className="classroom-history"><summary>Session history</summary>{transcript.sections.filter(section => section.text.trim()).map(section => <RichText key={section.id} text={section.text} prefix={lesson + '-history-' + section.id} record={record} />)}</details>}
      {reason && <p className="classroom-reason muted">{reason}</p>}{children}
    </div>{panel && <aside className="classroom-context" id="classroom-context" aria-label={panel === 'plan' ? 'Dependency plan' : 'Questions for your tutor'}><h2>{panel === 'plan' ? 'Dependency plan' : 'Questions for your tutor'}</h2>{contextError && panel === 'plan' && <p className="notice" role="status">{contextError}</p>}{panel === 'plan' ? <DependencyPlan map={map} active={active} record={record} /> : question}</aside>}</div>
  </div>;
}

/** What the lesson tool adds to a step: the chosen teaching medium with its reason, and an unsent draft saved by any client. */
export interface StepExtras {medium?: {chosen: string; delivered: string; reason: string; notes?: string[]}; draft?: {id: string; text: string} | null; answer_key?: string; after?: {outcome: string}}
export type Step = LessonStep & StepExtras;
const MEDIA_LABEL: Record<string, string> = {text: 'an explanation in words', 'static-visual': 'a figure', animation: 'an animation', code: 'a code example'};
/** Say honestly which medium teaches this part and, when it is not ready, that the lesson goes on in words. Nothing blocks. */
export function mediumNotice(step: StepExtras): string {
  const m = step.medium;
  if (!m || (m.chosen === 'text' && m.delivered === 'text')) return '';
  const wanted = MEDIA_LABEL[m.chosen] || m.chosen, shown = MEDIA_LABEL[m.delivered] || m.delivered;
  if (m.chosen === m.delivered) return `Shown as ${wanted}. ${m.reason}`;
  const why = m.notes?.length ? ` (${m.notes.join('; ')})` : '';
  return `${wanted[0].toUpperCase()}${wanted.slice(1)} would teach this best, but it is not ready${why}. This part is ${shown}, and the lesson continues.`;
}
/** One key per presented question until it is answered: a retry or a second client sends the same key and writes nothing twice. */
export function newAnswerKey(): string {
  const c = (globalThis as {crypto?: {randomUUID?: () => string}}).crypto;
  return c?.randomUUID ? c.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2);
}
export const DRAFT_DELAY = 600;

/** A bundle can be taught when its words and questions pass, even while voice, figures or animation are still being made. */
export const isTeachable = (bundle: {ready?: boolean; teachable?: boolean}) => bundle.ready || bundle.teachable === true;
