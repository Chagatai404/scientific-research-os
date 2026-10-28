import {useEffect, useRef, useState} from 'react';
import type {UpdateStatus} from './desktop';
import {Modal, useOverlay} from './overlay';

const key = 'ros.update-prompt.later';
const later = () => {try {return sessionStorage.getItem(key) || '';} catch {return '';}};

/** Offers a newer version as soon as the app has found one. "Later" lasts until the next launch. */
export function UpdatePrompt() {
  const host = window.researchDesktop;
  const prompt = useOverlay('modal', 'update');
  const [status, setStatus] = useState<UpdateStatus | null>(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const offered = useRef('');
  const {show} = prompt;
  useEffect(() => {
    if (!host) return;
    let active = true;
    const poll = async () => {
      try {
        const next = await host.updates();
        if (!active) return;
        setStatus(next);
        if (next.available && (next.state === 'downloading' || next.state === 'ready') && later() !== next.available && offered.current !== next.available) {offered.current = next.available; show();}
      } catch { /* the Settings page reports connectivity */ }
    };
    void poll();
    const timer = setInterval(poll, 2000);
    return () => {active = false; clearInterval(timer);};
  }, [host, show]);
  if (!host) return null;
  const dismiss = (close: () => void) => {try {sessionStorage.setItem(key, status?.available || '');} catch { /* private mode */ } close();};
  async function install() {
    setBusy(true); setError('');
    try {await host!.installUpdate();} catch (e) {setError((e as Error).message);} finally {setBusy(false);}
  }
  return <Modal id="update" title={status?.state === 'ready' ? 'An update is ready' : 'An update is on its way'}>{close => <>
    {status?.state === 'ready'
      ? <p>Research OS {status.available} is ready. Restart now to finish updating, or leave it and it installs the next time you quit. Your records and notes stay exactly where they are.</p>
      : <p>Research OS {status?.available} is downloading{status?.percent != null ? ` (${status.percent}%)` : ''}. Keep working; you can restart when it is ready.</p>}
    {error && <p className="notice error" role="alert">{error}</p>}
    <div className="modal-actions"><button onClick={() => dismiss(close)}>Later</button>{status?.state === 'ready' && <button className="primary" disabled={busy} onClick={install}>{busy ? 'Restarting…' : 'Restart & install'}</button>}</div></>}</Modal>;
}
