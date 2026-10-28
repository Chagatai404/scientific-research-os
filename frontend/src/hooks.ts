import {useEffect, useState} from 'react';

export function useRecordEvents(record: string) {
  useEffect(() => {
    if (typeof EventSource === 'undefined') return;
    const stream = new EventSource('/events' + (record ? '?record=' + encodeURIComponent(record) : ''));
    const changed = () => window.dispatchEvent(new CustomEvent('ros:record-changed', {detail: {record}}));
    stream.addEventListener('change', changed);
    const run = () => window.dispatchEvent(new CustomEvent('ros:run-changed', {detail: {record}}));
    stream.addEventListener('run', run);
    return () => {stream.removeEventListener('change', changed); stream.removeEventListener('run', run); stream.close();};
  }, [record]);
}

export function useRecordRevision(record?: string, runs = false) {
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (record === undefined) return;
    const changed = (event: Event) => {
      if ((event as CustomEvent<{record: string}>).detail?.record === record) setRevision(value => value + 1);
    };
    window.addEventListener('ros:record-changed', changed);
    if (runs) window.addEventListener('ros:run-changed', changed);
    return () => {window.removeEventListener('ros:record-changed', changed); window.removeEventListener('ros:run-changed', changed);};
  }, [record, runs]);
  return revision;
}

export function useResource<T>(key: string, load: (signal: AbortSignal) => Promise<T>, liveRecord?: string) {
  const [version, setVersion] = useState(0);
  const revision = useRecordRevision(liveRecord, key.includes('runs:'));
  const [state, setState] = useState<{key: string; data?: T; error?: string}>({key});
  useEffect(() => {
    const abort = new AbortController();
    // A live update must not unmount reading/answer forms or discard their drafts.
    setState(previous => previous.key === key ? {...previous, error: undefined} : {key});
    load(abort.signal).then(data => {if (!abort.signal.aborted) setState({key, data});})
      .catch(error => {if (!abort.signal.aborted) setState(previous => ({...(previous.key === key ? previous : {}), key, error: String(error.message || error)}));});
    return () => abort.abort();
    // key explicitly includes every request argument. Re-rendering a form never replaces its data.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, version, revision]);
  return {...(state.key === key ? state : {key}), retry: () => setVersion(x => x + 1)};
}
