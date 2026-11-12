import {call} from './api';
import {useResource} from './hooks';

/** One provider/model row of `usage_summary`. Cost is null when no price is configured or the provider reported no usage. */
export interface UsageModel {provider: string; model: string; runs: number; reported: number; unknown: number; input: number; output: number; cached: number; requests: number; cost: number | null; currency: string | null; unpriced: number; subscription: boolean; cost_status: 'subscription' | 'unknown' | 'unpriced' | 'partial' | 'priced'}
export interface UsageTotal {runs: number; reported: number; unknown: number; input: number; output: number; cached: number; requests: number; cost: number | null; currency: string | null; cost_complete: boolean}
export interface ContextGauge {known: boolean; used?: number; limit: number | null; unit: string; fraction?: number; run: string | null}
export interface UsageSummary {scope: string; id: string | null; total: UsageTotal; models: UsageModel[]; context?: ContextGauge}

export const formatCount = (n: number) => n >= 1e6 ? `${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)}M` : n >= 1e4 ? `${Math.round(n / 1e3)}k` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}k` : String(n);

/** What to show for cost, never a made-up number: a figure only when a configured price produced it. */
export function costLabel(total: Pick<UsageTotal, 'cost' | 'currency' | 'cost_complete' | 'reported' | 'runs'>, models: UsageModel[]): string {
  if (models.length && models.every(m => m.subscription)) return 'Included in subscription';
  if (total.cost == null) return total.reported ? 'Cost unknown (no price set)' : 'Cost unknown';
  const money = `${total.currency ?? ''} ${total.cost.toFixed(total.cost < 1 ? 4 : 2)}`.trim();
  return total.cost_complete ? money : `${money} (partial)`;
}

export const modelCostLabel = (m: UsageModel) => m.cost_status === 'subscription' ? 'Included in subscription' : m.cost == null ? (m.reported ? 'Cost unknown (no price set)' : 'Cost unknown') : `${m.currency ?? ''} ${m.cost.toFixed(m.cost < 1 ? 4 : 2)}${m.cost_status === 'partial' ? ' (partial)' : ''}`.trim();

export function contextLabel(gauge?: ContextGauge): string {
  if (!gauge || !gauge.known || gauge.used == null || !gauge.limit) return gauge?.limit ? `Context size unknown (limit ${formatCount(gauge.limit)} ${gauge.unit})` : 'Context size unknown';
  return `Context ${Math.round((gauge.fraction ?? gauge.used / gauge.limit) * 100)}% of ${formatCount(gauge.limit)} ${gauge.unit}`;
}

function Gauge({gauge}: {gauge?: ContextGauge}) {
  const label = contextLabel(gauge);
  if (!gauge || !gauge.known || gauge.used == null || !gauge.limit) return <span className="usage-gauge muted">{label}</span>;
  const pct = Math.round((gauge.fraction ?? gauge.used / gauge.limit) * 100);
  return <span className="usage-gauge"><meter min={0} max={100} value={pct} low={70} high={90} optimum={0} aria-label={label}>{pct}%</meter> <span>{label}</span></span>;
}

/** The compact footer: tokens, requests, cost (or unknown / subscription) and, in a conversation, the context gauge. */
export function UsageFooter({summary}: {summary: UsageSummary}) {
  const {total, models} = summary;
  const unknown = total.unknown ? ` · ${total.unknown} ${total.unknown === 1 ? 'run' : 'runs'} reported no usage` : '';
  return <p className="usage-meter muted" role="status" aria-label="Usage">
    <span>{total.reported ? `${formatCount(total.input + total.cached)} in · ${formatCount(total.output)} out · ${total.requests} ${total.requests === 1 ? 'request' : 'requests'}` : 'Usage unknown'}{unknown}</span>
    {' · '}<span>{costLabel(total, models)}</span>
    {summary.context && <>{' · '}<Gauge gauge={summary.context}/></>}
  </p>;
}

/** The workspace total: one row per provider and model, with the same honesty about unknown usage and unset prices. */
export function WorkspaceUsagePanel({summary}: {summary: UsageSummary}) {
  const {total, models} = summary;
  return <section className="usage-panel" aria-labelledby="usage-panel-title">
    <h2 id="usage-panel-title">Usage in this workspace</h2>
    {!total.runs ? <p className="muted">No runs yet.</p> : <>
      <table>
        <caption className="muted">Provider-reported usage. Nothing is estimated; a run whose provider reported none is counted as unknown.</caption>
        <thead><tr><th scope="col">Provider</th><th scope="col">Model</th><th scope="col">Input</th><th scope="col">Cached</th><th scope="col">Output</th><th scope="col">Requests</th><th scope="col">Unknown runs</th><th scope="col">Cost</th></tr></thead>
        <tbody>{models.map(m => <tr key={`${m.provider}:${m.model}`}><th scope="row">{m.provider}</th><td>{m.model}</td><td>{m.input.toLocaleString()}</td><td>{m.cached.toLocaleString()}</td><td>{m.output.toLocaleString()}</td><td>{m.requests}</td><td>{m.unknown}</td><td>{modelCostLabel(m)}</td></tr>)}</tbody>
        <tfoot><tr><th scope="row" colSpan={2}>Total</th><td>{total.input.toLocaleString()}</td><td>{total.cached.toLocaleString()}</td><td>{total.output.toLocaleString()}</td><td>{total.requests}</td><td>{total.unknown}</td><td>{costLabel(total, models)}</td></tr></tfoot>
      </table>
      <p className="muted">Prices are the ones you set in Settings; without one a cost stays unknown.</p>
    </>}
  </section>;
}

/** Loads the summary for a conversation (footer) or the workspace (panel) and keeps it current with the record. */
export function UsageMeter({record, conversation, panel = false}: {record?: string; conversation?: string; panel?: boolean}) {
  const scope = conversation && !panel ? 'conversation' : 'workspace';
  const usage = useResource<UsageSummary>(`usage:${record ?? ''}:${scope}:${conversation ?? ''}`, signal => call<UsageSummary>('usage_summary', scope === 'conversation' ? {scope, id: conversation} : {scope}, record, false, signal), record);
  if (!usage.data) return usage.error ? <p className="notice error" role="alert">{usage.error}</p> : null;
  return panel || scope === 'workspace' ? <WorkspaceUsagePanel summary={usage.data}/> : <UsageFooter summary={usage.data}/>;
}
