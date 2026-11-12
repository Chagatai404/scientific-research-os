import {useEffect} from 'react';
import {Modal, useOverlayController} from './overlay';
import {isTypingTarget, type TypingTarget} from './FindBar';

export const SHORTCUTS_ID = 'shortcuts';

export interface Shortcut {keys: string; action: string}
export interface ShortcutGroup {title: string; items: Shortcut[]}

/** The single list of the app's keyboard shortcuts. Keep it in step with the key handlers it describes. */
export function shortcutGroups(mac: boolean): ShortcutGroup[] {
  const mod = mac ? '⌘' : 'Ctrl+', shift = mac ? '⇧' : 'Shift+';
  return [
    {title: 'Anywhere', items: [
      {keys: `${mod}K`, action: 'Go to a page (command menu)'},
      {keys: `${mod}P`, action: 'Go to the Library'},
      {keys: `${mod}B`, action: 'Show or hide navigation'},
      {keys: `${mod}${shift}B`, action: 'Show or hide the sessions column'},
      {keys: `${mod}F`, action: 'Find in this page'},
      {keys: '?', action: 'Show these shortcuts (when not typing in a field)'},
      {keys: 'Esc', action: 'Close the open menu, dialog or find bar'},
    ]},
    {title: 'Find bar', items: [
      {keys: 'Enter', action: 'Next match'},
      {keys: `${shift}Enter`, action: 'Previous match'},
    ]},
    {title: 'Conversation', items: [
      {keys: 'Enter', action: 'Send the message'},
      {keys: `${shift}Enter`, action: 'New line in the message'},
    ]},
    {title: 'Graph', items: [
      {keys: 'Arrow keys', action: 'Pan the view'},
      {keys: '+  /  -', action: 'Zoom in / out'},
      {keys: '0', action: 'Fit everything'},
      {keys: 'Esc', action: 'Close node details'},
    ]},
  ];
}

const mac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform);

export function ShortcutList({mac: onMac = mac}: {mac?: boolean}) {
  return <>{shortcutGroups(onMac).map(group => <section key={group.title} aria-label={group.title}>
    <h3>{group.title}</h3>
    <dl className="shortcut-list">{group.items.map(item => <div key={item.keys + item.action} style={{display: 'flex', gap: '1rem', justifyContent: 'space-between'}}>
      <dt>{item.action}</dt><dd><kbd>{item.keys}</kbd></dd></div>)}</dl>
  </section>)}</>;
}

/** The "Keyboard shortcuts" dialog; "?" opens it when no text field has focus. */
export function ShortcutHelp() {
  const overlay = useOverlayController();
  const {active, show} = overlay;
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if (event.key !== '?' || event.isComposing || event.ctrlKey || event.metaKey || event.altKey) return;
      if (isTypingTarget(document.activeElement as TypingTarget | null) || active?.kind === 'modal') return;
      event.preventDefault(); show('modal', SHORTCUTS_ID);
    };
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  }, [active, show]);
  return <Modal id={SHORTCUTS_ID} title="Keyboard shortcuts">{close => <>
    <ShortcutList />
    <div className="modal-actions"><button onClick={close} aria-label="Close keyboard shortcuts">Close</button></div></>}</Modal>;
}
