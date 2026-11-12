import {useCallback, useEffect, useRef, useState} from 'react';

/* In-page find for the current view (Ctrl/Cmd+F).
   Keyboard policy: Ctrl/Cmd+F opens the bar and focuses its field. When focus is in a text field the person has
   already typed into (composer, title, search box), the browser default is left alone so editing is never hijacked;
   in an empty or read-only field, or anywhere else, the bar opens. Esc closes it and returns focus to where it was.
   Matches are found within single text nodes (a phrase split across bold or math markup is not matched). */

export interface TypingTarget {tagName?: string; isContentEditable?: boolean; readOnly?: boolean; disabled?: boolean; type?: string; value?: string}
const nonText = new Set(['button', 'checkbox', 'radio', 'submit', 'reset', 'range', 'color', 'file', 'image']);

/** True when the element is a text field the person can type into. */
export function isTypingTarget(el: TypingTarget | null | undefined): boolean {
  if (!el) return false;
  if (el.isContentEditable) return true;
  const tag = (el.tagName || '').toLowerCase();
  if (tag === 'textarea') return !el.readOnly && !el.disabled;
  if (tag === 'select') return true;
  return tag === 'input' && !nonText.has((el.type || 'text').toLowerCase()) && !el.readOnly && !el.disabled;
}

/** Whether Ctrl/Cmd+F should open the bar for this focused element. */
export function findShouldOpen(el: TypingTarget | null | undefined, ownField = false): boolean {
  return ownField || !isTypingTarget(el) || !(el?.isContentEditable || (el?.value ?? '') !== '');
}

export interface Match {node: number; start: number; end: number}

/** Case-insensitive, non-overlapping matches of `query` in each text. */
export function findMatches(texts: string[], query: string): Match[] {
  const needle = query.toLowerCase();
  if (!needle.trim()) return [];
  const found: Match[] = [];
  texts.forEach((text, node) => {
    const hay = text.toLowerCase();
    for (let at = hay.indexOf(needle); at >= 0; at = hay.indexOf(needle, at + needle.length)) found.push({node, start: at, end: at + needle.length});
  });
  return found;
}

export const stepIndex = (current: number, total: number, delta: 1 | -1): number => total ? (current + delta + total) % total : 0;
export const findLabel = (current: number, total: number, query: string): string =>
  !query.trim() ? '' : total ? `${current + 1} of ${total}` : 'No matches';

const skipped = 'script,style,textarea,.katex-mathml,.math-source,.find-bar,[hidden]';
type Highlights = {set(name: string, value: unknown): void; delete(name: string): void};
const highlights = (): Highlights | undefined => (typeof CSS !== 'undefined' ? (CSS as unknown as {highlights?: Highlights}).highlights : undefined);

function textNodes(root: HTMLElement): Text[] {
  const nodes: Text[] = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    if (n.nodeValue?.trim() && !n.parentElement?.closest(skipped)) nodes.push(n as Text);
  }
  return nodes;
}

const style = `.find-bar{position:fixed;top:.75rem;right:1rem;z-index:50;display:flex;align-items:center;gap:.4rem;padding:.4rem .5rem;background:Canvas;color:CanvasText;border:1px solid GrayText;border-radius:.5rem;box-shadow:0 2px 8px rgba(0,0,0,.25)}
.find-bar[hidden]{display:none}.find-bar input{min-width:12rem}.find-bar .find-count{min-width:5rem;font-variant-numeric:tabular-nums}
::highlight(ros-find){background:rgba(255,213,0,.45);color:inherit}::highlight(ros-find-current){background:rgba(255,140,0,.75);color:inherit}`;

export function FindBar({root, initiallyOpen = false}: {root: {current: HTMLElement | null}; initiallyOpen?: boolean}) {
  const [open, setOpen] = useState(initiallyOpen);
  const [query, setQuery] = useState('');
  const [total, setTotal] = useState(0);
  const [current, setCurrent] = useState(0);
  const field = useRef<HTMLInputElement>(null);
  const ranges = useRef<Range[]>([]);
  const opener = useRef<HTMLElement | null>(null);

  const clear = useCallback(() => {highlights()?.delete('ros-find'); highlights()?.delete('ros-find-current'); ranges.current = [];}, []);
  const close = useCallback(() => {
    setOpen(false); clear();
    const back = opener.current; opener.current = null;
    if (back?.isConnected) back.focus({preventScroll: true});
  }, [clear]);

  useEffect(() => {
    const keys = (event: KeyboardEvent) => {
      if (event.isComposing || !(event.ctrlKey || event.metaKey) || event.altKey || event.shiftKey || event.key.toLowerCase() !== 'f') return;
      const target = document.activeElement as HTMLElement | null;
      const own = target === field.current;
      if (!findShouldOpen(target as TypingTarget | null, own)) return;
      event.preventDefault();
      if (!open && target && target !== document.body) opener.current = target;
      setOpen(true);
      requestAnimationFrame(() => {field.current?.focus(); field.current?.select();});
    };
    window.addEventListener('keydown', keys);
    return () => window.removeEventListener('keydown', keys);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const base = root.current;
    clear();
    if (!base) {setTotal(0); return;}
    const nodes = textNodes(base);
    const found = findMatches(nodes.map(n => n.nodeValue || ''), query);
    ranges.current = found.map(m => {const r = document.createRange(); r.setStart(nodes[m.node], m.start); r.setEnd(nodes[m.node], m.end); return r;});
    setTotal(found.length); setCurrent(0);
  }, [open, query, root, clear]);

  useEffect(() => {
    const set = highlights();
    const list = ranges.current.filter(r => r.startContainer.isConnected);
    const here = list[Math.min(current, list.length - 1)];
    if (set && typeof Highlight !== 'undefined') {
      set.set('ros-find', new Highlight(...list));
      if (here) set.set('ros-find-current', new Highlight(here)); else set.delete('ros-find-current');
    }
    here?.startContainer.parentElement?.scrollIntoView?.({block: 'center', inline: 'nearest'});
  }, [current, total, query, open]);
  useEffect(() => () => clear(), [clear]);

  const go = (delta: 1 | -1) => setCurrent(c => stepIndex(c, total, delta));
  return <div className="find-bar" role="search" aria-label="Find in this page" hidden={!open}>
    <style>{style}</style>
    <input ref={field} type="search" aria-label="Find in this page" value={query} autoComplete="off" onChange={e => setQuery(e.target.value)}
      onKeyDown={e => {
        if (e.key === 'Escape') {e.preventDefault(); e.stopPropagation(); close();}
        else if (e.key === 'Enter' && !e.nativeEvent.isComposing) {e.preventDefault(); go(e.shiftKey ? -1 : 1);}
      }} />
    <span className="find-count" role="status" aria-live="polite">{open ? findLabel(current, total, query) : ''}</span>
    <button type="button" onClick={() => go(-1)} disabled={!total} aria-label="Previous match">↑</button>
    <button type="button" onClick={() => go(1)} disabled={!total} aria-label="Next match">↓</button>
    <button type="button" onClick={close} aria-label="Close find">×</button>
  </div>;
}
