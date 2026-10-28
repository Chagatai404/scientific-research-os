import {useState} from 'react';
import {effortLabel, supportedEfforts, type ModelChoice} from './modelPreferences';

/** A short list of exclusive choices shown all at once (replaces a native drop-down). */
export function Choice<T extends string>({label, value, options, onChange}: {label: string; value: T; options: readonly (readonly [T, string])[]; onChange: (value: T) => void}) {
  return <div className="choice" role="radiogroup" aria-label={label}>{options.map(([key, text]) => <button key={key} type="button" role="radio" aria-checked={value === key} className={value === key ? 'on' : ''} onClick={() => onChange(key)}>{text}</button>)}</div>;
}

/** Reasoning effort as a slider over the efforts the chosen model supports; nothing when there is nothing to choose. */
export function EffortSlider({model, effort, onChange}: {model?: ModelChoice; effort?: string; onChange: (effort: string) => void}) {
  const steps = supportedEfforts(model), current = effort && steps.includes(effort) ? effort : steps.includes('medium') ? 'medium' : steps[0];
  if (steps.length < 2) return null;
  return <label className="effort-slider" title="How much the model thinks before answering"><span>Effort: <strong>{effortLabel(current)}</strong></span>
    <input type="range" aria-label="Reasoning effort" min={0} max={steps.length - 1} step={1} value={steps.indexOf(current)} aria-valuetext={effortLabel(current)} onChange={e => onChange(steps[Number(e.target.value)])} /></label>;
}

/** Pick one piece of material by typing a few words, instead of scrolling a list of everything. Nothing chosen means "my own words". */
export function MaterialPick({label, items, picked, onPick, none}: {label: string; items: {id: string; title: string}[]; picked: string; onPick: (id: string) => void; none: string}) {
  const [query, setQuery] = useState('');
  const chosen = items.find(m => m.id === picked), needle = query.trim().toLowerCase();
  const matches = needle ? items.filter(m => m.title.toLowerCase().includes(needle)).slice(0, 6) : [];
  return <div className="material-pick"><span className="pick-label">{label}</span>
    {chosen ? <span className="pick-chosen"><strong>{chosen.title}</strong><button type="button" aria-label={`Stop using ${chosen.title}`} onClick={() => onPick('')}>×</button></span>
      : <><input type="search" aria-label={label} value={query} onChange={e => setQuery(e.target.value)} placeholder={`${none} — or type to find material`} autoComplete="off"/>
        {matches.length > 0 && <ul className="pick-matches">{matches.map(m => <li key={m.id}><button type="button" onClick={() => {onPick(m.id); setQuery('');}}>{m.title}</button></li>)}</ul>}
        {needle && !matches.length && <small className="muted">Nothing in your Library matches.</small>}</>}</div>;
}
