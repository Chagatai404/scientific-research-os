import {createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode} from 'react';
import {createPortal} from 'react-dom';

/* One app-level owner for every transient surface: menus, pickers, the command palette and dialogs.
   Opening one replaces the previous one. Escape, an outside press, a selection or a route change closes it,
   and keyboard focus goes back to the control that opened it. */
export type OverlayKind = 'workspace' | 'attach' | 'model' | 'effort' | 'mode' | 'item' | 'graph' | 'palette' | 'modal';
export interface Active {kind: OverlayKind; id: string; data?: unknown}
interface Controller {
  active: Active | null;
  show(kind: OverlayKind, id?: string, data?: unknown): void;
  hide(restoreFocus?: boolean): void;
}
const Overlay = createContext<Controller>({active: null, show() {}, hide() {}});
export const ownerOf = (kind: string, id = '') => `${kind}:${id}`;

export function OverlayProvider({children}: {children: ReactNode}) {
  const [active, setActive] = useState<Active | null>(null);
  const opener = useRef<HTMLElement | null>(null);
  const current = useRef<Active | null>(null);
  current.current = active;
  const show = useCallback((kind: OverlayKind, id = '', data?: unknown) => {
    // Remember where focus was before the first overlay opened; a replacement keeps the original opener.
    if (!current.current && document.activeElement instanceof HTMLElement) opener.current = document.activeElement;
    setActive({kind, id, data});
  }, []);
  const hide = useCallback((restoreFocus = true) => {
    const target = opener.current;
    setActive(null);
    if (restoreFocus && target) requestAnimationFrame(() => {if (target.isConnected) target.focus({preventScroll: true});});
    opener.current = null;
  }, []);
  useEffect(() => {
    const key = (event: KeyboardEvent) => {if (event.key === 'Escape' && current.current && !event.defaultPrevented) {event.preventDefault(); hide(true);}};
    const press = (event: Event) => {
      const open = current.current;
      if (!open) return;
      const target = event.target instanceof Element ? event.target : null;
      if (!target?.closest(`[data-overlay-owner="${ownerOf(open.kind, open.id)}"]`)) hide(false);
    };
    const leave = () => {if (current.current) hide(false);};
    document.addEventListener('keydown', key);
    document.addEventListener('pointerdown', press, true);
    window.addEventListener('hashchange', leave);
    window.addEventListener('ros:overlay-close', leave);
    return () => {document.removeEventListener('keydown', key); document.removeEventListener('pointerdown', press, true); window.removeEventListener('hashchange', leave); window.removeEventListener('ros:overlay-close', leave);};
  }, [hide]);
  const value = useMemo(() => ({active, show, hide}), [active, show, hide]);
  return <Overlay.Provider value={value}>{children}</Overlay.Provider>;
}

export const useOverlayController = () => useContext(Overlay);

export function useOverlay(kind: OverlayKind, id = '') {
  const {active, show, hide} = useContext(Overlay);
  const open = active?.kind === kind && active.id === id;
  return {open, data: open ? active?.data : undefined, show: (data?: unknown) => show(kind, id, data), close: (restoreFocus = true) => hide(restoreFocus), toggle: () => (open ? hide(true) : show(kind, id))};
}

/** A button that owns one anchored panel. `children` receives close(), called after a selection. */
export function Menu({kind, id = '', label, button, buttonLabel, buttonClassName = '', className = '', align = 'left', up = false, disabled = false, children}: {
  kind: OverlayKind; id?: string; label: string; button: ReactNode; buttonLabel?: string; buttonClassName?: string; className?: string;
  align?: 'left' | 'right'; up?: boolean; disabled?: boolean; children: (close: () => void) => ReactNode;
}) {
  const overlay = useOverlay(kind, id);
  const first = useRef<HTMLDivElement>(null);
  useEffect(() => {if (overlay.open) first.current?.querySelector<HTMLElement>('input,[role=menuitem],button,a[href]')?.focus({preventScroll: true});}, [overlay.open]);
  // Keep the panel inside the window whatever the width: slide it sideways instead of letting it be clipped.
  useLayoutEffect(() => {
    const panel = first.current;
    if (!overlay.open || !panel) return;
    panel.style.transform = '';
    const box = panel.getBoundingClientRect();
    let shift = box.right > innerWidth - 8 ? innerWidth - 8 - box.right : 0;
    if (box.left + shift < 8) shift = 8 - box.left;
    if (shift) panel.style.transform = `translateX(${shift}px)`;
  }, [overlay.open]);
  return <span className={'menu ' + className} data-overlay-owner={ownerOf(kind, id)}>
    <button type="button" className={buttonClassName} aria-haspopup="dialog" aria-expanded={overlay.open} aria-label={buttonLabel} disabled={disabled} onClick={overlay.toggle}>{button}</button>
    {overlay.open && <div ref={first} className={`menu-panel ${align} ${up ? 'up' : ''}`} role="dialog" aria-label={label}>{children(() => overlay.close(true))}</div>}
  </span>;
}

/** A centred dialog. While one is open the rest of the app is inert (see App), so nothing hides behind it. */
export function Modal({id, title, children}: {id: string; title: string; children: (close: () => void, data: unknown) => ReactNode}) {
  const overlay = useOverlay('modal', id);
  const body = useRef<HTMLDivElement>(null);
  useEffect(() => {if (overlay.open) body.current?.querySelector<HTMLElement>('input,select,textarea,button')?.focus({preventScroll: true});}, [overlay.open]);
  if (!overlay.open) return null;
  // Portalled to <body> so a collapsed sidebar can never hide a dialog it opened.
  return createPortal(<div className="scrim"><div ref={body} className="modal" role="dialog" aria-modal="true" aria-label={title} data-overlay-owner={ownerOf('modal', id)}>
    <h2>{title}</h2>{children(() => overlay.close(true), overlay.data)}</div></div>, document.body);
}
