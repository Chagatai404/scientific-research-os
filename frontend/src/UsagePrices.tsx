import {useState, type FormEvent} from 'react';
import {call, human} from './api';
import {useResource} from './hooks';

export interface PriceVersion {input: number; output: number; cached: number | null; currency: string; effective: string; version: number}
export type PriceTable = Record<string, PriceVersion[]>;

export function PriceList({prices}: {prices: PriceTable}) {
  const models = Object.keys(prices ?? {}).filter(m => Array.isArray(prices[m]) && prices[m].length);
  if (!models.length) return <p className="muted">No prices set yet. Costs stay unknown until you add one.</p>;
  return <table><caption className="muted">Per million tokens, every version.</caption>
    <thead><tr><th scope="col">Model</th><th scope="col">Version</th><th scope="col">Input</th><th scope="col">Output</th><th scope="col">Cached</th><th scope="col">Currency</th><th scope="col">Effective</th></tr></thead>
    <tbody>{models.flatMap(m => prices[m].map(p => <tr key={`${m}:${p.version}`}><th scope="row">{m}</th><td>{p.version}</td><td>{p.input}</td><td>{p.output}</td><td>{p.cached ?? 'not set'}</td><td>{p.currency}</td><td>{p.effective}</td></tr>))}</tbody></table>;
}

export function UsagePrices({record}: {record: string}) {
  const [shown, setShown] = useState(false);
  return <section aria-labelledby="settings-prices"><h2 id="settings-prices">Model prices</h2>
    <p className="muted">Prices are yours to set, per million tokens. Subscription models show as included, and usage a provider did not report is never estimated.</p>
    {shown ? <PriceEditor record={record}/> : <button type="button" onClick={() => setShown(true)}>Show model prices</button>}
  </section>;
}

function PriceEditor({record}: {record: string}) {
  const prices = useResource<PriceTable>('usage-prices:' + record, signal => call<PriceTable>('usage_prices', {}, record, false, signal), record);
  const [model, setModel] = useState(''); const [input, setInput] = useState(''); const [output, setOutput] = useState(''); const [cached, setCached] = useState('');
  const [currency, setCurrency] = useState('USD'); const [effective, setEffective] = useState(new Date().toISOString().slice(0, 10));
  const [open, setOpen] = useState(false);
  const [error, setError] = useState(''); const [saved, setSaved] = useState('');
  async function add(event: FormEvent) {
    event.preventDefault(); setError(''); setSaved('');
    try {
      await human('usage_prices_configure', {model: model.trim(), input: Number(input), output: Number(output), effective, currency, ...(cached !== '' ? {cached: Number(cached)} : {})}, record);
      setSaved('Price version added.'); prices.retry();
    } catch (e) {setError((e as Error).message);}
  }
  return <>
    {prices.data ? <PriceList prices={prices.data}/> : prices.error ? <p className="notice error" role="alert">{prices.error}</p> : <p role="status">Loading prices…</p>}
    {!open ? <button type="button" onClick={() => setOpen(true)}>Add a price version</button> : <form onSubmit={add}>
      <label htmlFor="price-model">Model</label><input id="price-model" value={model} onChange={e => setModel(e.target.value)} required/>
      <label htmlFor="price-input">Input per million</label><input id="price-input" type="number" min="0" step="any" value={input} onChange={e => setInput(e.target.value)} required/>
      <label htmlFor="price-output">Output per million</label><input id="price-output" type="number" min="0" step="any" value={output} onChange={e => setOutput(e.target.value)} required/>
      <label htmlFor="price-cached">Cached per million (optional)</label><input id="price-cached" type="number" min="0" step="any" value={cached} onChange={e => setCached(e.target.value)}/>
      <label htmlFor="price-currency">Currency</label><input id="price-currency" value={currency} maxLength={3} onChange={e => setCurrency(e.target.value.toUpperCase())} required/>
      <label htmlFor="price-effective">Effective date</label><input id="price-effective" type="date" value={effective} onChange={e => setEffective(e.target.value)} required/>
      <button type="submit">Add price version</button>
    </form>}
    {saved && <p role="status">{saved}</p>}{error && <p className="notice error" role="alert">{error}</p>}
  </>;
}
