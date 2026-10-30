import {EffortSlider} from './controls';
import {useEffect, useRef, useState, type FormEvent} from 'react';
import {call, human, href, preference, savePreference, service} from './api';
import {RichText} from './Document';
import {Graph} from './Graph';
import {Menu} from './overlay';
import {AttachMenu, chipKind, chipName, loadAttachments, saveAttachments, MAX_ATTACHMENTS, type Attached} from './AttachMenu';
import {useResource} from './hooks';
import type {SourceRef} from './desktop';
import type {Run} from './Workbench';
import {modelLabel, useModelPreferences, type ModelCatalog} from './modelPreferences';
import {Player} from './Learn';
import {RunSteps} from './RunSteps';
import './classroom.css';

const SESSION_MODES = [{id: 'chat', label: 'Ask', hint: 'Look things up and talk it through. Nothing is started or changed.'},
  {id: 'learn', label: 'Learn', hint: 'A guided lesson: probe what you know, teach, then ask again, with reviews kept for later.'},
  {id: 'research', label: 'Research', hint: 'Work on a question: find your earlier plans and sources, then build claims and evidence.'},
  {id: 'defend', label: 'Defend', hint: 'Practise defending a claim until you own it.'}];

interface Chat {conversation: string; title: string; mode?: string; messages: {id: string; role: string; text: string; model?: string;scope?:SourceRef[]}[]; pending: string[]; interrupted: number; lesson?: {lesson: string; record?: string | null} | null}

export function Conversation({id, record}: {id: string; record: string}) {
  const capabilities = useResource('conversation-capabilities:' + record, () => service<ModelCatalog>('catalog?record=' + encodeURIComponent(record)));
  const models = useModelPreferences(capabilities.data?.models);
  const draftKey = 'composer:' + JSON.stringify([record, id || 'new']);
  const [text, setText] = useState(() => preference(draftKey, ''));
  const [mode, setModeState] = useState(() => { const saved = preference('session-mode', 'learn'); return SESSION_MODES.some(m => m.id === saved) ? saved : 'learn'; });
  const setMode = (next: string) => {setModeState(next); savePreference('session-mode', next);};
  const [chat, setChat] = useState<Chat | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [attachments, setAttachmentList] = useState<Attached[]>(() => loadAttachments(record));
  const setAttachments = (next: Attached[]) => {setAttachmentList(next); saveAttachments(record, next);};
  const [note, setNote] = useState('');
  // Several files can arrive back to back, so each must build on the latest list, not on this render's copy.
  const addAttachment = (ref: Attached) => setAttachmentList(previous => {const next = previous.length < MAX_ATTACHMENTS ? [...previous, ref] : previous; saveAttachments(record, next); return next;});
  const runs = useResource('conversation-runs:' + record, signal => call<Run[]>('run_list', {}, record, false, signal), record);
  const activeRun = runs.data?.find(r => r.conversation === id);
  const follow = useRef(true);
  const [newOutput,setNewOutput] = useState(false);
  const turnKey = useRef(crypto.randomUUID());
  const [recording, setRecording] = useState(false);
  const [openingMicrophone, setOpeningMicrophone] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [speaking, setSpeaking] = useState('');
  const [audioUrl, setAudioUrl] = useState('');
  const [voiceAuto, setVoiceAuto] = useState(() => preference('read-replies', 'off') === 'on');
  const recorder = useRef<MediaRecorder | null>(null);
  const mounted = useRef(true), acquisition = useRef(0);
  const audio = useRef<HTMLAudioElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const seen = useRef('');
  const submitting = useRef(false);
  const currentDraft = useRef(draftKey); currentDraft.current = draftKey;
  const currentModel = models.model;
  async function permitAttachment(index: number) {
    const target = attachments[index];
    if (!target) return;
    try {
      const grant = await human<{permission:string}>('vision_permission', {source:target.sourceId,path:target.relativePath,revision:target.revision,model:currentModel}, record);
      setAttachments(attachments.map((a, i) => i === index ? {...a,visionPermission:grant.permission,permissionModel:currentModel} : a));setError('');
    } catch(e) {setError((e as Error).message);}
  }
  const pending = sending || (!!chat?.pending.length && (!activeRun || !['completed','failed','cancelled','interrupted'].includes(activeRun.state)));
  async function stop() {try {if (activeRun) {await service('run-cancel', {run: activeRun.id, record}); runs.retry();}} catch (e) {setError((e as Error).message);}}
  function releaseMicrophone() {
    acquisition.current++;
    const capture = recorder.current;
    if (capture) {
      capture.onstop = null; capture.ondataavailable = null;
      if (capture.state !== 'inactive') capture.stop();
      capture.stream.getTracks().forEach(track => track.stop()); recorder.current = null;
    }
  }
  useEffect(() => {releaseMicrophone(); setRecording(false); setOpeningMicrophone(false); setTranscribing(false); setText(preference(draftKey, '')); setError('');}, [draftKey]);
  useEffect(() => {setChat(null);}, [id]);
  useEffect(() => {
    if (!id) return;
    let cancelled = false; let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {const value = await call<Chat>('workspace_chat', {conversation: id}, record); if (!cancelled) {setChat(value); if (value.pending.length) timer = setTimeout(refresh, 1100);}}
      catch (e) {if (!cancelled) setError((e as Error).message);}
    }
    refresh(); return () => {cancelled = true; clearTimeout(timer);};
  }, [id, record, sending, activeRun?.state]);
  useEffect(() => {const container=end.current?.closest('main');if(!container)return;const scrolled=()=>{follow.current=container.scrollTop+container.clientHeight>=container.scrollHeight-160;if(follow.current)setNewOutput(false);};container.addEventListener('scroll',scrolled,{passive:true});return()=>container.removeEventListener('scroll',scrolled);}, [id,!!chat]);
  useEffect(() => {if (follow.current) end.current?.scrollIntoView({block: 'nearest', behavior: 'auto'});else setNewOutput(true);}, [chat?.messages.length, activeRun?.output]);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false; releaseMicrophone();
    };
  }, []);
  useEffect(() => {
    const last = chat?.messages.at(-1);
    if (last?.role === 'assistant' && voiceAuto && capabilities.data?.voice.kokoro && last.id !== seen.current) {seen.current = last.id; speak(last.id, last.text);}
  }, [chat?.messages, voiceAuto, capabilities.data]);
  async function send(event: FormEvent) {
    event.preventDefault(); if (!text.trim() || pending || submitting.current || !models.selected || openingMicrophone || recording || transcribing) return;
    submitting.current = true;
    setSending(true); setError('');
    const value = text.trim(), submittedDraft = text;
    try {
      const result = await call<{conversation: string; request: string}>('workspace_chat_send', {text: value, model: currentModel, key: turnKey.current, ...(attachments.length ? {scope: attachments} : {}), ...(models.selectedEffort ? {effort: models.selectedEffort} : {}), ...(id ? {conversation: id} : {mode})}, record, true);
      // A request can finish while the person is writing the next message or navigating.
      // Preserve that newer draft and never steal the new page's input/focus.
      turnKey.current = crypto.randomUUID(); setAttachments([]);
      const latest = preference(draftKey, submittedDraft), remaining = latest === submittedDraft ? '' : latest;
      const destinationDraft = 'composer:' + JSON.stringify([record, result.conversation]);
      savePreference(destinationDraft, remaining); if (destinationDraft !== draftKey) savePreference(draftKey, '');
      if (mounted.current && currentDraft.current === draftKey) setText(remaining);
      let recent: {id: string; title: string}[] = [];
      try {const saved = JSON.parse(preference('recent-chats:' + record, '[]')); if (Array.isArray(saved)) recent = saved.filter(x => typeof x?.id === 'string' && typeof x?.title === 'string');} catch { /* optional local navigation index */ }
      savePreference('recent-chats:' + record, JSON.stringify([{id: result.conversation, title: chat?.title || value.slice(0, 100)}, ...recent.filter(x => x.id !== result.conversation)].slice(0, 12)));
      window.dispatchEvent(new Event('ros:records-changed'));
      if (mounted.current && currentDraft.current === draftKey) {
        setChat(previous => ({conversation: result.conversation, title: previous?.title || value, messages: [...(previous?.messages || []), {id: result.request, role: 'user', text: value}], pending: [result.request], interrupted: 0}));
        location.hash = href('chat', result.conversation, record);
      }
    } catch (e) {if (mounted.current) setError((e as Error).message);} finally {if (mounted.current) setSending(false); submitting.current = false;}
  }
  // An answer on the lesson card is already recorded as the learner's; this message only hands the turn to the tutor.
  async function notify(attempt: string, said: string) {
    if (!id || pending || !models.selected) return;
    try {
      await call('workspace_chat_send', {text: 'On the lesson card I answered: ' + said, model: currentModel, conversation: id, answered: attempt, key: crypto.randomUUID(), ...(models.selectedEffort ? {effort: models.selectedEffort} : {})}, record, true);
      runs.retry(); setChat(previous => previous && {...previous});
    } catch (e) {setError((e as Error).message);}
  }
  async function speak(messageId: string, value: string) {
    if (speaking) return;
    setSpeaking(messageId); setError('');
    try {const result = await service<{audio: string}>('speech', {text: value.slice(0, 12000), record}); setAudioUrl(result.audio);}
    catch (e) {setError((e as Error).message);} finally {setSpeaking('');}
  }
  useEffect(() => {if (audioUrl) audio.current?.play().catch(() => {});}, [audioUrl]);
  async function dictate() {
    if (recording) {setTranscribing(true); recorder.current?.stop(); setRecording(false); return;}
    setError('');
    if (!navigator.mediaDevices?.getUserMedia || !globalThis.MediaRecorder) {setError('Microphone capture is unavailable in this browser. Open the portal in Chrome or Edge on localhost.'); return;}
    const owner = ++acquisition.current;
    const active = () => mounted.current && acquisition.current === owner;
    let ownedStream: MediaStream | null = null;
    setOpeningMicrophone(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({audio: true});
      ownedStream = stream;
      if (!active() || currentDraft.current !== draftKey) {stream.getTracks().forEach(track => track.stop()); return;}
      const chunks: Blob[] = [], capture = new MediaRecorder(stream); recorder.current = capture;
      capture.ondataavailable = event => {if (event.data.size) chunks.push(event.data);};
      capture.onstop = async () => {
        stream.getTracks().forEach(track => track.stop()); if (!active()) return;
        setTranscribing(true);
        try {
          const blob = new Blob(chunks, {type: capture.mimeType});
          if (blob.size > 12 * 1024 * 1024) throw new Error('Please keep the recording under 12 MB.');
          const buffer = new Uint8Array(await blob.arrayBuffer()); let binary = '';
          for (let i = 0; i < buffer.length; i += 8192) binary += String.fromCharCode(...buffer.subarray(i, i + 8192));
          if (!active()) return;
          const result = await service<{text: string}>('transcribe', {audio: btoa(binary), record});
          if (!active()) return;
          if (currentDraft.current === draftKey) setText(previous => {const next = previous + (previous ? ' ' : '') + result.text; savePreference(draftKey, next); return next;});
          else {const previous = preference(draftKey, ''); savePreference(draftKey, previous + (previous ? ' ' : '') + result.text);}
        } catch (e) {if (active()) setError((e as Error).message);} finally {if (active()) setTranscribing(false);}
      };
      capture.start(); setRecording(true);
    } catch {ownedStream?.getTracks().forEach(track => track.stop()); if (active()) setError('Microphone permission was not granted. Allow it in your browser and try again.');} finally {if (active()) setOpeningMicrophone(false);}
  }
  return <div className={'conversation-workspace ' + (id ? 'has-conversation' : 'graph-home')} data-testid={!id ? 'graph-home' : undefined}>
    {!id && <Graph record={record} focus="" embedded />}
    {id && <div className="conversation-heading"><div><div className="eyebrow">An ongoing conversation</div><h1>{chat?.title || 'Let’s work through it'}</h1></div><a className="button" href={href('overview', '', record)}>New conversation</a></div>}
    {chat && <div className="messages" aria-label="Conversation messages">{chat.messages.map(message => <article className={'message ' + message.role} key={message.id}><div className="message-meta">{message.role === 'user' ? 'You' : message.role === 'error' ? 'Could not complete' : message.model?.split(':')[0] || 'Research OS'}</div><RichText text={message.text} prefix={message.id} record={record} />{message.role==='assistant'&&message.scope?.some(ref=>ref.kind==='media')&&<button onClick={async()=>{const ref=message.scope!.find(ref=>ref.kind==='media')!;try{await call('transcription_draft',{source:ref.sourceId,path:ref.relativePath,revision:ref.revision,text:message.text,by:message.model||'tutor'},record,true);setError('Transcription draft saved. Review it beside the original in Sources.');}catch(e){setError((e as Error).message);}}}>Save Transcription Draft</button>}{message.role === 'assistant' && capabilities.data?.voice.kokoro && <button className="read-message" disabled={!!speaking} onClick={() => speak(message.id, message.text)}>{speaking === message.id ? 'Preparing Kokoro audio…' : 'Listen · Kokoro'}</button>}</article>)}
      {pending && activeRun && activeRun.steps.length > 0 && <RunSteps steps={activeRun.steps} />}{pending && activeRun?.output && <div className="stream-output" aria-label="Partial response"><RichText text={activeRun.output} record={record}/></div>}{pending && <div className="thinking" role="status"><span className="pulse-dot" /> {activeRun?.state === 'queued' ? 'Queued for the foreground worker…' : 'Working on your question…'} <small>Your message is saved.</small></div>}{chat.interrupted > 0 && <p className="notice">A previous response was interrupted. You can send a follow-up to continue.</p>}<div ref={end} /></div>}
    {id && chat?.lesson && <Player key={chat.lesson.lesson} id={chat.lesson.lesson} record={chat.lesson.record || record} embedded refresh={chat.messages.length} onAnswered={notify} />}
    <div className="session-dock">{!id && <div className="mode-picker" role="group" aria-label="Session type">{SESSION_MODES.map(m => <button type="button" key={m.id} aria-pressed={mode === m.id} title={m.hint} onClick={() => setMode(m.id)}>{m.label}</button>)}<small className="muted">{SESSION_MODES.find(m => m.id === mode)?.hint}</small></div>}{id && chat && chat.mode && chat.mode !== 'chat' && <p className="mode-badge muted">{SESSION_MODES.find(m => m.id === chat.mode)?.label ?? chat.mode} session</p>}{!id && <nav className="home-actions" aria-label="Quick starts">{preference('last', '') && <a href={preference('last', '')}>Continue where you were</a>}<a href={href('library', '', record)}>Add material</a><a href={href('learn', '', record)}>Learn something</a><a href={href('research', '', record)}>Investigate a question</a></nav>}{newOutput &&<button type="button" onClick={()=>{follow.current=true;setNewOutput(false);end.current?.scrollIntoView({block:"nearest"});}}>New Output ↓</button>}{attachments.length > 0 && <ul className="attachment-chips" aria-label="Attached to this message">{attachments.map((attachment, index) => <li className="attachment-chip" key={attachment.sourceId + attachment.relativePath + attachment.revision}><span className="chip-name" title={attachment.relativePath}>{chipName(attachment)}</span><small>{chipKind(attachment)} · {attachment.localOnly ? 'Stays on this computer' : 'May be sent to the chosen model'}</small>
      {attachment.kind === 'media' && !currentModel.startsWith('ollama:') && (attachment.localOnly ? <small className="chip-warning">This file stays on this computer. Choose a local model to let it read this file.</small> : <><small>Sending to {modelLabel(currentModel, capabilities.data?.models)}. Your permission covers this version of the file for one message within 10 minutes.</small><button type="button" onClick={() => permitAttachment(index)}>{attachment.visionPermission && attachment.permissionModel === currentModel ? 'Renew permission' : 'Allow this file to be sent'}</button></>)}
      <button type="button" className="chip-remove" aria-label={`Remove ${chipName(attachment)}`} onClick={() => setAttachments(attachments.filter((_, i) => i !== index))}>×</button></li>)}</ul>}<form className="goal-composer chat-composer" onSubmit={send}><label className="sr-only" htmlFor="chat-input">Your message</label><textarea id="chat-input" rows={2} value={text} onChange={e => {setText(e.target.value); savePreference(draftKey, e.target.value);}} placeholder={id ? 'Follow your thinking…' : 'What would you like to understand or investigate?'} required maxLength={12000} onKeyDown={e => {if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {e.preventDefault(); e.currentTarget.form?.requestSubmit();}}} />
      <div className="composer-footer"><div className="composer-tools"><AttachMenu record={record} count={attachments.length} onAttach={addAttachment} onNote={setNote}/>
        <Menu kind="model" label="Language model" buttonLabel={'Language model: ' + modelLabel(currentModel, capabilities.data?.models)} buttonClassName="model-picker" up button={<>{modelLabel(currentModel, capabilities.data?.models)} <span aria-hidden="true">⌄</span></>}>{close => <div className="model-options" role="group" aria-label="Language model">{capabilities.data?.models.map(m => <button key={m.id} type="button" aria-pressed={currentModel === m.id} onClick={() => {models.update(m.id); close();}}><span>{m.label}</span><small>{m.provider}</small></button>)}<a className="manage-models" href={href('settings', '', record)} onClick={close}>Manage models →</a>{!capabilities.data?.models.length && <p>Install and sign in to Codex or Claude, or start a local Ollama model.</p>}</div>}</Menu>
        <EffortSlider model={models.selected} effort={models.selectedEffort} onChange={effort => models.update(currentModel, effort)} />
        <button className={'microphone ' + (recording ? 'recording' : '')} type="button" aria-label={recording ? 'Stop recording' : 'Dictate your question'} aria-pressed={recording} disabled={openingMicrophone || transcribing || !capabilities.data?.voice.whisper} onClick={dictate}>{recording ? '■ Stop' : transcribing ? 'Transcribing…' : '◉ Voice'}</button>
        <button type="button" className="voice-toggle" aria-pressed={voiceAuto} disabled={!capabilities.data?.voice.kokoro} onClick={() => {setVoiceAuto(!voiceAuto); savePreference('read-replies', voiceAuto ? 'off' : 'on');}}>♫ {voiceAuto ? 'Read replies on' : capabilities.data?.voice.kokoro ? 'Kokoro ready' : 'Voice unavailable'}</button></div>{pending && <button type="button" onClick={stop} disabled={!activeRun}>Stop</button>}<button className="primary send-message" disabled={pending || !models.selected || openingMicrophone || recording || transcribing} aria-label="Send message">{pending ? 'Working…' : 'Send ↑'}</button></div>
    </form>
    {note && <p className="notice" role="status">{note} <button type="button" onClick={() => setNote('')}>Dismiss</button></p>}
    <p className={'composer-caption' + (!recording && !transcribing && !(capabilities.data && (!capabilities.data.models.length || !models.selected)) ? ' idle' : '')} role="status">{recording ? 'Listening locally. Stop when you’re ready; review the transcript before sending.' : transcribing ? 'Transcribing locally. Review the transcript before sending.' : capabilities.data && !capabilities.data.models.length ? 'No model available. Open Settings to connect a provider.' : capabilities.data && !models.selected ? 'The selected model is unavailable. Choose a model in Settings.' : 'Enter to send · Shift Enter for a new line'}</p>
    {audioUrl && <audio className="reply-audio" ref={audio} src={audioUrl} controls aria-label="Kokoro response playback" />}
    {(error || capabilities.error) && <p className="notice error" role="alert">{error || capabilities.error}</p>}
    </div>
    {id && <p className="quiet-note"><a href={href('research', '', record)}>See preparation, evidence & next actions →</a></p>}
  </div>;
}

