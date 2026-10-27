import {useEffect, useRef, useState, type FormEvent} from 'react';
import {call, href, preference, savePreference, service} from './api';
import {RichText} from './Document';
import {Graph} from './Graph';
import {useResource} from './hooks';
import {effortLabel, modelLabel, supportedEfforts, useModelPreferences, type ModelCatalog} from './modelPreferences';

interface Chat {conversation: string; title: string; messages: {id: string; role: string; text: string; model?: string}[]; pending: string[]; interrupted: number}

export function Conversation({id, record}: {id: string; record: string}) {
  const capabilities = useResource('conversation-capabilities', () => service<ModelCatalog>('catalog'));
  const models = useModelPreferences(capabilities.data?.models);
  const draftKey = 'composer:' + JSON.stringify([record, id || 'new']);
  const [text, setText] = useState(() => preference(draftKey, ''));
  const [chat, setChat] = useState<Chat | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
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
  const pending = sending || !!chat?.pending.length;
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
  }, [id, record, sending]);
  useEffect(() => {end.current?.scrollIntoView({block: 'nearest', behavior: 'auto'});}, [chat?.messages.length]);
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
      const result = await call<{conversation: string; request: string}>('workspace_chat_send', {text: value, model: currentModel, ...(models.selectedEffort ? {effort: models.selectedEffort} : {}), ...(id ? {conversation: id} : {})}, record, true);
      // A request can finish while the person is writing the next message or navigating.
      // Preserve that newer draft and never steal the new page's input/focus.
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
    {chat && <div className="messages" aria-label="Conversation messages">{chat.messages.map(message => <article className={'message ' + message.role} key={message.id}><div className="message-meta">{message.role === 'user' ? 'You' : message.role === 'error' ? 'Could not complete' : message.model?.split(':')[0] || 'Research OS'}</div><RichText text={message.text} prefix={message.id} record={record} />{message.role === 'assistant' && capabilities.data?.voice.kokoro && <button className="read-message" disabled={!!speaking} onClick={() => speak(message.id, message.text)}>{speaking === message.id ? 'Preparing Kokoro audio…' : 'Listen · Kokoro'}</button>}</article>)}
      {pending && <div className="thinking" role="status"><span className="pulse-dot" /> Thinking through your question… <small>Your message is saved.</small></div>}{chat.interrupted > 0 && <p className="notice">A previous response was interrupted. You can send a follow-up to continue.</p>}<div ref={end} /></div>}
    <div className="session-dock"><form className="goal-composer chat-composer" onSubmit={send}><label className="sr-only" htmlFor="chat-input">Your message</label><textarea id="chat-input" rows={2} value={text} onChange={e => {setText(e.target.value); savePreference(draftKey, e.target.value);}} placeholder={id ? 'Follow your thinking…' : 'What would you like to understand or investigate?'} required maxLength={12000} onKeyDown={e => {if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {e.preventDefault(); e.currentTarget.form?.requestSubmit();}}} />
      <div className="composer-footer"><div className="composer-tools"><details className="model-picker"><summary>{modelLabel(currentModel, capabilities.data?.models)} <span aria-hidden="true">⌄</span></summary><div className="model-options" role="group" aria-label="Language model">{capabilities.data?.models.map(m => <button key={m.id} type="button" aria-pressed={currentModel === m.id} onClick={e => {models.update(m.id); e.currentTarget.closest('details')?.removeAttribute('open');}}><span>{m.label}</span><small>{m.provider}</small></button>)}<a className="manage-models" href={href('settings', '', record)}>Manage Models →</a>{!capabilities.data?.models.length && <p>Install and sign in to Codex or Claude, or start a local Ollama model.</p>}</div></details>
        {supportedEfforts(models.selected).length > 0 && <details className="effort-picker"><summary aria-label={'Reasoning effort: ' + effortLabel(models.selectedEffort || 'medium')}>{effortLabel(models.selectedEffort || 'medium')} <span aria-hidden="true">⌄</span></summary><div className="model-options effort-options" role="group" aria-label="Reasoning effort">{supportedEfforts(models.selected).map(effort => <button key={effort} type="button" aria-pressed={models.selectedEffort === effort} onClick={event => {models.update(currentModel, effort); event.currentTarget.closest('details')?.removeAttribute('open');}}>{effortLabel(effort)}</button>)}</div></details>}
        <button className={'microphone ' + (recording ? 'recording' : '')} type="button" aria-label={recording ? 'Stop recording' : 'Dictate your question'} aria-pressed={recording} disabled={openingMicrophone || transcribing || !capabilities.data?.voice.whisper} onClick={dictate}>{recording ? '■ Stop' : transcribing ? 'Transcribing…' : '◉ Voice'}</button>
        <button type="button" className="voice-toggle" aria-pressed={voiceAuto} disabled={!capabilities.data?.voice.kokoro} onClick={() => {setVoiceAuto(!voiceAuto); savePreference('read-replies', voiceAuto ? 'off' : 'on');}}>♫ {voiceAuto ? 'Read replies on' : capabilities.data?.voice.kokoro ? 'Kokoro ready' : 'Voice unavailable'}</button></div><button className="primary send-message" disabled={pending || !models.selected || openingMicrophone || recording || transcribing} aria-label="Send message">{pending ? 'Working…' : 'Send ↑'}</button></div>
    </form>
    <p className="composer-caption" role="status">{recording ? 'Listening locally. Stop when you’re ready; review the transcript before sending.' : transcribing ? 'Transcribing locally. Review the transcript before sending.' : capabilities.data && !capabilities.data.models.length ? 'No model available. Open Settings to connect a provider.' : capabilities.data && !models.selected ? 'The selected model is unavailable. Choose a model in Settings.' : 'Enter to send · Shift Enter for a new line'}</p>
    {audioUrl && <audio className="reply-audio" ref={audio} src={audioUrl} controls aria-label="Kokoro response playback" />}
    {(error || capabilities.error) && <p className="notice error" role="alert">{error || capabilities.error}</p>}
    </div>
    {id && <p className="quiet-note"><a href={href('research', '', record)}>See preparation, evidence & next actions →</a></p>}
  </div>;
}
