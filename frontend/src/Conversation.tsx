import {useEffect, useRef, useState, type FormEvent} from 'react';
import {call, href, preference, savePreference, service} from './api';
import {RichText} from './Document';
import {Graph} from './Graph';
import {useResource} from './hooks';
import {Notice} from './ui';

interface Capabilities {models: {id: string; label: string; provider: string}[]; voice: {kokoro: boolean; whisper: boolean; label: string}; notice: string}
interface Chat {conversation: string; title: string; messages: {id: string; role: string; text: string; model?: string}[]; pending: string[]; interrupted: number}

export function Conversation({id, record}: {id: string; record: string}) {
  const capabilities = useResource('conversation-capabilities', () => service<Capabilities>('catalog'));
  const [model, setModel] = useState(() => preference('model', ''));
  const [customModel, setCustomModel] = useState('');
  const [text, setText] = useState(() => preference('composer:' + record, ''));
  const [chat, setChat] = useState<Chat | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [speaking, setSpeaking] = useState('');
  const [audioUrl, setAudioUrl] = useState('');
  const [voiceAuto, setVoiceAuto] = useState(() => preference('read-replies', 'off') === 'on');
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const audio = useRef<HTMLAudioElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const seen = useRef('');
  const currentModel = model || capabilities.data?.models[0]?.id || '';
  const pending = sending || !!chat?.pending.length;
  useEffect(() => {if (!id) setChat(null);}, [id]);
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
  useEffect(() => () => {recorder.current?.stream.getTracks().forEach(track => track.stop());}, []);
  useEffect(() => {
    const last = chat?.messages.at(-1);
    if (last?.role === 'assistant' && voiceAuto && capabilities.data?.voice.kokoro && last.id !== seen.current) {seen.current = last.id; speak(last.id, last.text);}
  }, [chat?.messages, voiceAuto, capabilities.data]);
  async function send(event: FormEvent) {
    event.preventDefault(); if (!text.trim() || pending || !currentModel) return;
    setSending(true); setError('');
    const value = text.trim();
    try {
      const result = await call<{conversation: string; request: string}>('workspace_chat_send', {text: value, model: currentModel, ...(id ? {conversation: id} : {})}, record, true);
      setText(''); savePreference('composer:' + record, '');
      window.dispatchEvent(new Event('ros:records-changed'));
      setChat(previous => ({conversation: result.conversation, title: previous?.title || value, messages: [...(previous?.messages || []), {id: result.request, role: 'user', text: value}], pending: [result.request], interrupted: 0}));
      location.hash = href('chat', result.conversation, record);
    } catch (e) {setError((e as Error).message);} finally {setSending(false);}
  }
  async function speak(messageId: string, value: string) {
    if (speaking) return;
    setSpeaking(messageId); setError('');
    try {const result = await service<{audio: string}>('speech', {text: value.slice(0, 12000), record}); setAudioUrl(result.audio);}
    catch (e) {setError((e as Error).message);} finally {setSpeaking('');}
  }
  useEffect(() => {if (audioUrl) audio.current?.play().catch(() => {});}, [audioUrl]);
  async function dictate() {
    if (recording) {recorder.current?.stop(); setRecording(false); return;}
    setError('');
    if (!navigator.mediaDevices?.getUserMedia || !globalThis.MediaRecorder) {setError('Microphone capture is unavailable in this browser. Open the portal in Chrome or Edge on localhost.'); return;}
    try {
      const stream = await navigator.mediaDevices.getUserMedia({audio: true});
      chunks.current = []; const capture = new MediaRecorder(stream); recorder.current = capture;
      capture.ondataavailable = event => {if (event.data.size) chunks.current.push(event.data);};
      capture.onstop = async () => {
        stream.getTracks().forEach(track => track.stop()); setTranscribing(true);
        try {
          const blob = new Blob(chunks.current, {type: capture.mimeType});
          if (blob.size > 12 * 1024 * 1024) throw new Error('Please keep the recording under 12 MB.');
          const buffer = new Uint8Array(await blob.arrayBuffer()); let binary = '';
          for (let i = 0; i < buffer.length; i += 8192) binary += String.fromCharCode(...buffer.subarray(i, i + 8192));
          const result = await service<{text: string}>('transcribe', {audio: btoa(binary), record});
          setText(previous => {const next = previous + (previous ? ' ' : '') + result.text; savePreference('composer:' + record, next); return next;});
        } catch (e) {setError((e as Error).message);} finally {setTranscribing(false);}
      };
      capture.start(); setRecording(true);
    } catch {setError('Microphone permission was not granted. Allow it in your browser and try again.');}
  }
  return <div className={'conversation-workspace ' + (id ? 'has-conversation' : '')}>
    {!id && <><div className="eyebrow">Your knowledge, connected</div><h1 className="hero-title">Where will curiosity<br />take you today?</h1><p className="lead muted">Ask a question. Explore an idea. Start building understanding.</p></>}
    {id && <div className="conversation-heading"><div><div className="eyebrow">An ongoing conversation</div><h1>{chat?.title || 'Let’s work through it'}</h1></div><a className="button" href={href('overview', '', record)}>New conversation</a></div>}
    {chat && <div className="messages" aria-label="Conversation messages">{chat.messages.map(message => <article className={'message ' + message.role} key={message.id}><div className="message-meta">{message.role === 'user' ? 'You' : message.role === 'error' ? 'Could not complete' : message.model?.split(':')[0] || 'Research OS'}</div><RichText text={message.text} prefix={message.id} record={record} />{message.role === 'assistant' && capabilities.data?.voice.kokoro && <button className="read-message" disabled={!!speaking} onClick={() => speak(message.id, message.text)}>{speaking === message.id ? 'Preparing Kokoro audio…' : 'Listen · Kokoro'}</button>}</article>)}
      {pending && <div className="thinking" role="status"><span className="pulse-dot" /> Thinking through your question… <small>Your message is saved.</small></div>}{chat.interrupted > 0 && <p className="notice">A previous response was interrupted. You can send a follow-up to continue.</p>}<div ref={end} /></div>}
    <form className="goal-composer chat-composer" onSubmit={send}><label className="sr-only" htmlFor="chat-input">Your message</label><textarea id="chat-input" value={text} onChange={e => {setText(e.target.value); savePreference('composer:' + record, e.target.value);}} placeholder={id ? 'Follow your thinking…' : 'What would you like to understand or investigate?'} required maxLength={12000} onKeyDown={e => {if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {e.preventDefault(); e.currentTarget.form?.requestSubmit();}}} />
      <div className="composer-footer"><div className="composer-tools"><details className="model-picker"><summary>{capabilities.data?.models.find(m => m.id === currentModel)?.label || currentModel || 'Choose a model'} <span aria-hidden="true">⌄</span></summary><div className="model-options" role="group" aria-label="Language model">{capabilities.data?.models.map(m => <button key={m.id} type="button" aria-pressed={currentModel === m.id} onClick={e => {setModel(m.id); savePreference('model', m.id); e.currentTarget.closest('details')?.removeAttribute('open');}}><span>{m.label}</span><small>{m.provider}</small></button>)}<label htmlFor="custom-model">Another model</label><input id="custom-model" value={customModel} onChange={e => setCustomModel(e.target.value)} placeholder="provider:model" /><button type="button" disabled={!/^(codex|claude|ollama):[A-Za-z0-9_.:/-]{1,100}$/.test(customModel)} onClick={e => {setModel(customModel); savePreference('model', customModel); e.currentTarget.closest('details')?.removeAttribute('open');}}>Use model</button>{!capabilities.data?.models.length && <p>Install and sign in to Codex or Claude, or start a local Ollama model.</p>}</div></details>
        <button className={'microphone ' + (recording ? 'recording' : '')} type="button" aria-label={recording ? 'Stop recording' : 'Dictate your question'} aria-pressed={recording} disabled={transcribing || !capabilities.data?.voice.whisper} onClick={dictate}>{recording ? '■ Stop' : transcribing ? 'Transcribing…' : '◉ Voice'}</button>
        <button type="button" className="voice-toggle" aria-pressed={voiceAuto} disabled={!capabilities.data?.voice.kokoro} onClick={() => {setVoiceAuto(!voiceAuto); savePreference('read-replies', voiceAuto ? 'off' : 'on');}}>♫ {voiceAuto ? 'Read replies on' : 'Kokoro ready'}</button></div><button className="primary send-message" disabled={pending || !currentModel || transcribing} aria-label="Send message">{pending ? 'Working…' : 'Send ↑'}</button></div>
    </form>
    <p className="composer-caption">{recording ? 'Listening locally. Stop when you’re ready; review the transcript before sending.' : capabilities.data?.voice.kokoro ? 'Kokoro voice ready · Local Whisper dictation · Enter to send' : 'Enter to send · Shift Enter for a new line'}</p>
    {audioUrl && <audio className="reply-audio" ref={audio} src={audioUrl} controls aria-label="Kokoro response playback" />}
    {(error || capabilities.error) && <p className="notice error" role="alert">{error || capabilities.error}</p>}
    {!id && <section className="landing-graph"><Graph record={record} focus="" embedded /></section>}
    {id && <p className="quiet-note"><a href={href('research', '', record)}>See preparation, evidence & next actions →</a></p>}
  </div>;
}
