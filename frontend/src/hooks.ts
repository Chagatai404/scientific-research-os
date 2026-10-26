import {useEffect, useState} from 'react';

export function useResource<T>(key: string, load: (signal: AbortSignal) => Promise<T>) {
  const [version, setVersion] = useState(0);
  const [state, setState] = useState<{key: string; data?: T; error?: string}>({key});
  useEffect(() => {
    const abort = new AbortController();
    setState({key});
    load(abort.signal).then(data => {if (!abort.signal.aborted) setState({key, data});})
      .catch(error => {if (!abort.signal.aborted) setState({key, error: String(error.message || error)});});
    return () => abort.abort();
    // key explicitly includes every request argument. Re-rendering a form never replaces its data.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, version]);
  return {...(state.key === key ? state : {key}), retry: () => setVersion(x => x + 1)};
}
