import {PreparedReading} from './PreparedReading';
import {MediaArtifacts} from './MediaArtifacts';
import {Pedagogy} from './Pedagogy';
import {AgentAction} from './AgentAction';
import {useEffect, useRef, useState, type FormEvent} from 'react';
import {call, href, preference, readDocument, savePreference} from './api';
import type {AnswerResult, DocumentData, Entity, LibraryItem, LessonStep, Today} from './contracts';
import {Classroom, type ClassroomMap} from './Classroom';
import './classroom.css';
import {RichText, safeUrl} from './Document';
import {useRecordRevision, useResource} from './hooks';
import {Empty, Notice} from './ui';

export function Learn({id, record}: {id: string; record: string}) {
  const resource = useResource('learn:' + record, async signal => {
    const [bundles, today] = await Promise.all([call<LibraryItem[]>('bundles', {}, record, false, signal), call<Today>('today', {}, record, false, signal)]);
    return {bundles, today};
  });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function start(bundle: string) {
    setBusy(true); setError('');
    try {const result = await call<{lesson: string}>('start', {bundle}, record, true); location.hash = href('session', result.lesson, record);}
    catch (e) {setError((e as Error).message);} finally {setBusy(false);}
  }
  if (id) return <Player key={record + id} id={id} record={record} />;
  return <><div className="eyebrow">Build understanding, one step at a time</div><h1>Learning workspace</h1><p className="lead muted">Probe your understanding, follow a dependency plan, practise and return for review.</p>
    {error && <p className="notice error" role="alert">{error}</p>}
    {!resource.data ? <Notice error={resource.error} retry={resource.retry} /> : <><div className="summary-grid"><div><strong>{resource.data.today.due}</strong><span>reviews due</span></div><div><strong>{resource.data.today.waiting_answers}</strong><span>written answers awaiting a tutor</span></div></div>
      <div className="section-title"><h2>Prepared lessons</h2><span>{resource.data.bundles.length}</span></div>{resource.data.bundles.length ? <ul className="entry-list">{resource.data.bundles.map(bundle => <li key={bundle.id}><div className="lesson-entry"><div><strong>{bundle.title}</strong><small>{bundle.ready ? 'Ready to begin' : 'Preparation in progress'}</small></div><button className={bundle.ready ? 'primary' : ''} disabled={!bundle.ready || busy} onClick={() => start(bundle.id)}>Start lesson</button></div></li>)}</ul> : <Empty title="What would you like to understand?"><p>Describe your learning goal in Overview. Your agent will outline and prepare the material.</p></Empty>}
      <a className="text-link" href={href('library', '', record)}>Read past sessions →</a></>}
  </>;
}

function Player({id, record}: {id: string; record: string}) {
  const initial = useResource('step:' + record + ':' + id, signal => call<LessonStep>('next', {lesson: id}, record, false, signal));
  const [step, setStep] = useState<LessonStep | null>(null);
  const [answer, setAnswer] = useState(() => preference('draft:' + record + ':' + id, ''));
  const [question, setQuestion] = useState(() => preference('question:' + record + ':' + id, ''));
  const [asking, setAsking] = useState(false);
  const [result, setResult] = useState<AnswerResult | null>(null);
  const [segment, setSegment] = useState(()=>Number(preference('segment:'+record+':'+id,'0')) || 0);
  useEffect(()=>savePreference('segment:'+record+':'+id,String(segment)),[segment,record,id]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('');
  const [context, setContext] = useState<{map?: ClassroomMap; transcript?: DocumentData; title?: string; error?: string}>({});
  const revision = useRecordRevision(record);
  const generation = useRef(0);
  const currentRef = useRef(step);
  const busyRef = useRef(busy);
  currentRef.current = step; busyRef.current = busy;
  useEffect(() => {if (initial.data) setStep(initial.data);}, [initial.data]);
  useEffect(() => {
    const controller = new AbortController();
    const signal = controller.signal;
    async function refresh() {
      try {
        const [entity, transcript] = await Promise.all([call<Entity>('workspace_entity', {subject: id}, record, false, signal), readDocument(id, record, signal)]);
        const scope = typeof entity.node.scope === 'string' ? entity.node.scope : '';
        const map = scope ? await call<ClassroomMap>('map', {scope}, record, false, signal) : undefined;
        if (!signal.aborted) setContext({map, transcript, title: entity.node.title});
      } catch (error) {if (!signal.aborted) setContext(previous => ({...previous, error: 'Session context could not refresh: ' + (error as Error).message}));}
    }
    void refresh();
    // A tutor grade can release a pending answer. Other active steps remain learner-controlled.
    if (revision && currentRef.current?.action === 'wait' && !busyRef.current) {
      const expected = generation.current;
      call<LessonStep>('next', {lesson: id}, record, false, signal).then(next => {
        if (!signal.aborted && generation.current === expected && !busyRef.current && currentRef.current?.action === 'wait') setStep(next);
      }).catch(() => {/* Context refresh reports connectivity; the manual check remains available. */});
    }
    return () => controller.abort();
  }, [id, record, revision]);
  const current = step;
  async function perform(action: () => Promise<void>) {
    if (busy) return;
    generation.current += 1;
    busyRef.current = true;
    setBusy(true); setStatus('');
    try {await action();} catch (e) {setStatus((e as Error).message);} finally {setBusy(false); busyRef.current = false;}
  }
  function advance(next: LessonStep) {setStep(next); setResult(null); setSegment(0); setAnswer(''); savePreference('draft:' + record + ':' + id, '');}
  async function submit(event: FormEvent) {
    event.preventDefault(); if (!current) return;
    await perform(async () => {
      if (current.action === 'close') {await call('close', {lesson: id, summary: current.reason || ''}, record, true); location.hash = href('library', '', record); return;}
      if (result?.next) {advance(result.next); return;}
      if (current.action === 'teach') {
        if (segment < (current.content?.segments?.length || 0) - 1) {setSegment(x => x + 1); return;}
        await call('teach', {lesson: id, capability: current.capability, mode: current.mode || 'explain'}, record, true);
        advance(await call<LessonStep>('next', {lesson: id}, record)); return;
      }
      if (current.action === 'wait') {advance(await call<LessonStep>('next', {lesson: id}, record)); return;}
      const response = current.question?.kind === 'choice' ? Number(answer) : answer;
      const next = await call<AnswerResult>('answer', {lesson: id, item: current.item, response}, record, true);
      setResult(next); setAnswer(value => {if (value !== answer) return value; savePreference('draft:' + record + ':' + id, ''); return '';});
    });
  }
  async function ask(event: FormEvent) {
    event.preventDefault();
    const submitted = question;
    await perform(async () => {await call('ask', {lesson: id, text: submitted}, record, true); setQuestion(value => {if (value !== submitted) return value; savePreference('question:' + record + ':' + id, ''); return '';}); setStatus('Your question is saved for your tutor.');});
  }
  if (!current) return <Notice error={initial.error} retry={initial.retry} />;
  const active = current.action === 'probe' ? 'Probe' : current.action === 'teach' ? 'Teach' : current.action === 'review' ? 'Review' : 'Practice';
  const seg = current.content?.segments?.[segment];
  const mediaBase = '/media/' + (current.content?.base || '');
  const image = current.content?.visuals?.[segment]?.path || (segment === 0 ? current.content?.visuals?.[0]?.path : '');
  const answering = !result && !!current.question;
  const questionDock = <aside className="question-dock"><h2>Keep your question in context</h2><form onSubmit={ask}><label htmlFor="lesson-question">Your question</label><textarea id="lesson-question" required value={question} onChange={e => {setQuestion(e.target.value); savePreference('question:' + record + ':' + id, e.target.value);}} /><button disabled={busy}>Save question</button></form></aside>;
  return <Classroom title={context.title || current.title || 'Learning session'} phase={current.action === 'wait' ? 'Waiting for your tutor' : current.action === 'close' ? 'Session complete' : active} reason={current.reason} lesson={id} record={record} map={context.map} transcript={context.transcript} contextError={context.error} active={current.capability} question={questionDock} questionOpen={asking}>
    {current.title && context.title !== current.title && <h2>{current.title}</h2>}
    {current.action === 'wait' && <p>Your written answer is waiting for your tutor’s assessment. Check again when your tutor has graded it.</p>}
    {current.action === 'close' && <p className="lead">{current.reason}</p>}
    <form className="player" onSubmit={submit}>
      {current.action === 'teach' && <>{seg ? <><RichText text={seg.text} prefix={id + '-' + seg.id} record={record} />{image && <img className="lesson-figure" src={safeUrl(mediaBase + image, true, '', record)} alt={current.title || 'Lesson figure'} />}{seg.audio && <audio controls preload="metadata" src={safeUrl(mediaBase + seg.audio, true, '', record)} aria-label="Lesson narration" />}<p className="muted">{segment + 1} of {current.content?.segments?.length}</p></> : <p className="notice">This step needs a live explanation from your tutor. Prepared content is not available yet.</p>}</>}
      {current.question && <div className="prompt"><RichText text={current.question.prompt} record={record} /></div>}
      {result ? <div className={'feedback ' + result.verdict} role="status"><h2>{result.verdict === 'correct' ? 'Correct' : result.verdict === 'pending' ? 'Saved for your tutor' : 'Let’s work through it'}</h2><RichText text={result.feedback || result.explanation || ''} record={record} /></div> : answering && (current.question?.kind === 'choice' ? <fieldset className="choices"><legend>Choose one</legend>{current.question.options?.map((option, index) => <label key={index}><input type="radio" name="answer" value={index} checked={answer === String(index)} required onChange={e => {setAnswer(e.target.value); savePreference('draft:' + record + ':' + id, e.target.value);}} /><RichText text={option} record={record} /></label>)}</fieldset> : <div><label htmlFor="lesson-answer">Your answer</label><textarea id="lesson-answer" value={answer} required onChange={e => {setAnswer(e.target.value); savePreference('draft:' + record + ':' + id, e.target.value);}} inputMode={current.question?.kind === 'numeric' ? 'decimal' : 'text'} /></div>)}
      <div className="player-controls">{answering && <button type="button" disabled={busy} onClick={() => perform(async () => {setResult(await call<AnswerResult>('answer', {lesson: id, item: current.item, dont_know: true}, record, true)); savePreference('draft:' + record + ':' + id, '');})}>I don’t know</button>}<button type="button" aria-expanded={asking} onClick={() => setAsking(!asking)}>Ask a question</button><button className="primary" disabled={busy}>{busy ? 'Saving…' : current.action === 'wait' ? 'Check for feedback' : 'Continue'}</button></div>
    </form>
    {current.action==='teach'&&<MediaArtifacts animation={current.content?.animation} clip={current.content?.clip} base={mediaBase} record={record}/>}<PreparedReading key={id} record={record} lesson={id} item={current.item}/><Pedagogy key={id+current.item} record={record} lesson={id} item={current.item}/><AgentAction record={record} text={"Work on the pending tutoring tasks for lesson " + id + ". Use the exact saved attempt for grading, preserve assistance attribution, answer saved questions, and finish tasks only after committing their results."}/>{status && <p className="notice" role="status">{status}</p>}
    <p className="quiet-note">Only assessed answers contribute to learning evidence. Reading and confidence do not establish mastery.</p>
  </Classroom>;
}
