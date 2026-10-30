import {MaterialPick} from './controls';
import {PreparedReading} from './PreparedReading';
import {MediaArtifacts} from './MediaArtifacts';
import {Pedagogy} from './Pedagogy';
import {AgentAction} from './AgentAction';
import {useEffect, useRef, useState, type FormEvent} from 'react';
import {call, href, preference, readDocument, savePreference} from './api';
import type {AnswerResult, DocumentData, Entity, LibraryItem, LessonStep, Organization, Today} from './contracts';
import {Classroom, DependencyPlan, type ClassroomMap} from './Classroom';
import './classroom.css';
import {RichText, safeUrl} from './Document';
import {useRecordRevision, useResource} from './hooks';
import {Empty, Notice} from './ui';

export function Learn({id, record, material = ''}: {id: string; record: string; material?: string}) {
  const [version, setVersion] = useState(0);
  const resource = useResource(`learn:${record}:${version}`, async signal => {
    const [bundles, today, org] = await Promise.all([call<LibraryItem[]>('bundles', {}, record, false, signal), call<Today>('today', {}, record, false, signal), call<Organization>('workspace_organization', {}, record, false, signal)]);
    return {bundles, today, org};
  }, record);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [goal, setGoal] = useState(''), [picked, setPicked] = useState(material), [setup, setSetup] = useState('');
  const ready = (resource.data?.org.library || []).filter(m => m.state === 'ready');
  const chosen = ready.find(m => m.id === picked);
  useEffect(() => {setPicked(material);}, [material]);
  async function start(bundle: string) {
    setBusy(true); setError('');
    try {const result = await call<{lesson: string}>('start', {bundle}, record, true); location.hash = href('session', result.lesson, record);}
    catch (e) {setError((e as Error).message);} finally {setBusy(false);}
  }
  async function review() {
    setBusy(true); setError('');
    try {
      const target = await call<{scope: string} | null>('review_scope', {}, record);
      if (!target) {setError('Nothing is due for review right now. Your list will refresh.'); setVersion(v => v + 1); return;}
      const result = await call<{lesson: string}>('start', {scope: target.scope, title: 'Review'}, record, true); location.hash = href('session', result.lesson, record);
    } catch (e) {setError((e as Error).message);} finally {setBusy(false);}
  }
  async function plan(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(''); setSetup('Setting up your study plan…');
    try {
      const wanted = goal.trim() || `Teach me ${chosen?.title || ''}`;
      const out = await call<{kind: string; for_you?: string[]}>('engage', {intent: chosen && goal.trim() ? `${wanted} Use ${chosen.title} as the material.` : wanted}, record, true);
      setSetup(`Your plan is set up. ${out.for_you?.join(' ') || 'Your agent is preparing the first lesson; you will see it here when it is ready.'}`); setGoal(''); setVersion(v => v + 1);
    } catch (e) {setSetup(''); setError((e as Error).message);} finally {setBusy(false);}
  }
  if (id) return <Player key={record + id} id={id} record={record} />;
  if (!resource.data) return <Notice error={resource.error} retry={resource.retry} />;
  const {today, bundles} = resource.data, nextReady = bundles.find(b => b.ready), lastSession = preference('last', '');
  return <div className="learn-page"><div className="eyebrow">Build understanding, one step at a time</div><h1>Learn</h1>
    <p className="lead muted">Say what you want to understand. You get a short check of what you know, a study path, and practice with feedback.</p>
    {error && <p className="notice error" role="alert">{error}</p>}
    <section className="next-card" aria-label="Recommended next step"><div className="eyebrow">Recommended next step</div>
      {today.due > 0 ? <><h2>Review {today.due} {today.due === 1 ? 'idea' : 'ideas'} you are about to forget</h2><p className="muted">Short retrieval practice now keeps what you learned. It takes a few minutes.</p><button className="primary" disabled={busy} onClick={review}>Start review</button></>
        : nextReady ? <><h2>{nextReady.title}</h2><p className="muted">Prepared and ready for you.</p><button className="primary" disabled={busy} onClick={() => start(nextReady.id)}>Start lesson</button></>
        : today.next_lesson ? <><h2>{today.next_lesson.title}</h2><p className="muted">Your agent is still preparing this lesson{today.next_lesson.missing?.length ? ': ' + today.next_lesson.missing.slice(0, 3).join('; ') : ''}.</p><a className="button" href={href('activity', '', record)}>See progress</a></>
        : <><h2>What do you want to understand?</h2><p className="muted">Describe it below, or pick something from your Library.</p></>}
      {lastSession.startsWith('#session') && <p><a href={lastSession}>Resume your last lesson →</a></p>}</section>
    <form className="goal-composer" onSubmit={plan}><label htmlFor="learn-goal">What do you want to understand?</label>
      <textarea id="learn-goal" rows={3} value={goal} onChange={e => setGoal(e.target.value)} required={!chosen} maxLength={4000} placeholder={chosen ? `Teach me ${chosen.title}` : 'Teach me mathematical statistics, or explain quantum teleportation'}/>
      <div className="composer-footer"><MaterialPick label="Learn from" items={ready} picked={picked} onPick={setPicked} none="Your own words only"/>
        <button className="primary" disabled={busy || (!goal.trim() && !chosen)}>{busy ? 'Setting up…' : 'Plan my study'}</button></div>
      {!ready.length && <p className="muted">No readable material yet. <a href={href('library', '', record)}>Add material in the Library</a> to study from it.</p>}</form>
    {setup && <p className="notice" role="status">{setup}</p>}
    <div className="summary-grid"><div><strong>{today.due}</strong><span>reviews due</span></div><div><strong>{today.waiting_answers}</strong><span>answers waiting for feedback</span></div></div>
    <div className="section-title"><h2>Prepared lessons</h2><span>{bundles.length}</span></div>{bundles.length ? <ul className="entry-list">{bundles.map(bundle => <li key={bundle.id}><div className="lesson-entry"><div><strong>{bundle.title}</strong><small>{bundle.ready ? 'Ready to begin' : 'Being prepared. See Activity for progress.'}</small></div><button className={bundle.ready ? 'primary' : ''} disabled={!bundle.ready || busy} onClick={() => start(bundle.id)}>Start lesson</button></div></li>)}</ul> : <Empty title="No lessons yet"><p>Describe what you want to understand above. Preparation runs in the background and shows in Activity.</p></Empty>}
    <a className="text-link" href={href('library', '', record, '', {tab: 'notes'})}>Read past sessions →</a></div>;
}

// How sure the learner is, asked with every answer before any feedback. A self-report for calibration, never evidence.
export const CONFIDENCE = ['Guessing', 'Unsure', 'Fairly sure', 'Sure', 'Certain'];
const PHASES = [['probe', 'Probe'], ['teach', 'Teach'], ['practice', 'Practise'], ['close', 'Close']];
const phaseOf = (action: string) => action === 'teach' ? 'teach' : action === 'close' ? 'close' : action === 'probe' ? 'probe' : 'practice';

/** One lesson's current step: the question with an answer box and a confidence scale, or the prepared teaching (text,
 * figures, narration, animation), with the pedagogy actions. On the Learn page it fills the classroom; in a Learn
 * conversation it is the card above the composer, and `onAnswered` tells the tutor about the attempt it recorded. */
export function Player({id, record, embedded = false, refresh = 0, onAnswered}: {id: string; record: string; embedded?: boolean; refresh?: number; onAnswered?: (attempt: string, said: string) => void}) {
  const initial = useResource('step:' + record + ':' + id + (embedded ? ':' + refresh : ''), signal => call<LessonStep>('next', {lesson: id}, record, false, signal));
  const [confidence, setConfidence] = useState(0);
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
  function advance(next: LessonStep) {setStep(next); setResult(null); setSegment(0); setAnswer(''); setConfidence(0); savePreference('draft:' + record + ':' + id, '');}
  function answered(out: AnswerResult, said: string) {
    if (out.attempt && onAnswered) onAnswered(out.attempt, said + (confidence ? ` (confidence: ${CONFIDENCE[confidence - 1].toLowerCase()})` : ''));
  }
  async function submit(event: FormEvent) {
    event.preventDefault(); if (!current) return;
    await perform(async () => {
      if (current.action === 'close') {await call('close', {lesson: id, summary: current.reason || ''}, record, true); if (embedded) setStatus('Lesson closed. Its log is in your Library.'); else location.hash = href('library', '', record); return;}
      if (result?.next) {advance(result.next); return;}
      if (current.action === 'teach') {
        if (segment < (current.content?.segments?.length || 0) - 1) {setSegment(x => x + 1); return;}
        await call('teach', {lesson: id, capability: current.capability, mode: current.mode || 'explain'}, record, true);
        advance(await call<LessonStep>('next', {lesson: id}, record)); return;
      }
      if (current.action === 'wait') {advance(await call<LessonStep>('next', {lesson: id}, record)); return;}
      const response = current.question?.kind === 'choice' ? Number(answer) : answer;
      const next = await call<AnswerResult>('answer', {lesson: id, item: current.item, response, ...(confidence ? {confidence} : {})}, record, true);
      setResult(next); answered(next, current.question?.kind === 'choice' ? (current.question.options?.[Number(answer)] ?? answer) : answer); setAnswer(value => {if (value !== answer) return value; savePreference('draft:' + record + ':' + id, ''); return '';});
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
  const body = <>
    {current.title && context.title !== current.title && <h2>{current.title}</h2>}
    {current.action === 'wait' && <p>Your written answer is waiting for your tutor’s assessment. Check again when your tutor has graded it.</p>}
    {current.action === 'close' && <p className="lead">{current.reason}</p>}
    <form className="player" onSubmit={submit}>
      {current.action === 'teach' && <>{seg ? <><RichText text={seg.text} prefix={id + '-' + seg.id} record={record} />{image && <img className="lesson-figure" src={safeUrl(mediaBase + image, true, '', record)} alt={current.title || 'Lesson figure'} />}{seg.audio && <audio controls preload="metadata" src={safeUrl(mediaBase + seg.audio, true, '', record)} aria-label="Lesson narration" />}<p className="muted">{segment + 1} of {current.content?.segments?.length}</p></> : <p className="notice">This step needs a live explanation from your tutor. Prepared content is not available yet.</p>}</>}
      {current.question && <div className="prompt"><RichText text={current.question.prompt} record={record} /></div>}
      {result ? <div className={'feedback ' + result.verdict} role="status"><h2>{result.verdict === 'correct' ? 'Correct' : result.verdict === 'pending' ? 'Saved for your tutor' : 'Let’s work through it'}</h2><RichText text={result.feedback || result.explanation || ''} record={record} /></div> : answering && (current.question?.kind === 'choice' ? <fieldset className="choices"><legend>Choose one</legend>{current.question.options?.map((option, index) => <label key={index}><input type="radio" name="answer" value={index} checked={answer === String(index)} required onChange={e => {setAnswer(e.target.value); savePreference('draft:' + record + ':' + id, e.target.value);}} /><RichText text={option} record={record} /></label>)}</fieldset> : <div><label htmlFor="lesson-answer">Your answer</label><textarea id="lesson-answer" value={answer} required onChange={e => {setAnswer(e.target.value); savePreference('draft:' + record + ':' + id, e.target.value);}} inputMode={current.question?.kind === 'numeric' ? 'decimal' : 'text'} /></div>)}
      {answering && <fieldset className="confidence-scale"><legend>How sure are you?</legend>{CONFIDENCE.map((label, index) => <label key={label}><input type="radio" name="confidence" value={index + 1} checked={confidence === index + 1} onChange={() => setConfidence(index + 1)} />{label}</label>)}</fieldset>}
      <div className="player-controls">{answering && <button type="button" disabled={busy} onClick={() => perform(async () => {const out = await call<AnswerResult>('answer', {lesson: id, item: current.item, dont_know: true}, record, true); setResult(out); answered(out, 'I don’t know.'); savePreference('draft:' + record + ':' + id, '');})}>I don’t know</button>}<button type="button" aria-expanded={asking} onClick={() => setAsking(!asking)}>Ask a question</button><button className="primary" disabled={busy}>{busy ? 'Saving…' : current.action === 'wait' ? 'Check for feedback' : 'Continue'}</button></div>
    </form>
    {current.action==='teach'&&<MediaArtifacts animation={current.content?.animation} clip={current.content?.clip} base={mediaBase} record={record}/>}<PreparedReading key={id} record={record} lesson={id} item={current.item}/><Pedagogy key={id+current.item} record={record} lesson={id} item={current.item}/><AgentAction record={record} text={"Work on the pending tutoring tasks for lesson " + id + ". Use the exact saved attempt for grading, preserve assistance attribution, answer saved questions, and finish tasks only after committing their results."}/>{status && <p className="notice" role="status">{status}</p>}
    <p className="quiet-note">Only assessed answers contribute to learning evidence. Reading and confidence do not establish mastery.</p>
  </>;
  const phase = phaseOf(current.action);
  const stepper = <ol className="lesson-phases" aria-label="Lesson phases">{PHASES.map(([key, label]) => <li key={key} aria-current={phase === key ? 'step' : undefined}>{label}</li>)}</ol>;
  if (embedded) return <section className="lesson-card" aria-label="Lesson card"><header><div><div className="eyebrow">{current.action === 'wait' ? 'Waiting for your tutor' : active}</div><h2>{current.title || context.title || 'Lesson'}</h2></div>{stepper}</header>{current.reason && <p className="classroom-reason muted">{current.reason}</p>}{body}{asking && questionDock}<details className="lesson-plan"><summary>Study plan</summary><DependencyPlan map={context.map} active={current.capability} record={record} /></details></section>;
  return <Classroom title={context.title || current.title || 'Learning session'} phase={current.action === 'wait' ? 'Waiting for your tutor' : current.action === 'close' ? 'Session complete' : active} reason={current.reason} lesson={id} record={record} map={context.map} transcript={context.transcript} contextError={context.error} active={current.capability} question={questionDock} questionOpen={asking}>
    {stepper}{body}
  </Classroom>;
}
