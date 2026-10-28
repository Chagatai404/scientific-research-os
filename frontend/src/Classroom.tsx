import {useEffect, useState, type ReactNode} from 'react';
import {entityHref} from './api';
import {RichText} from './Document';
import type {DocumentData} from './contracts';

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
