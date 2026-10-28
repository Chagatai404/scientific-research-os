import {human} from './api';
import type {SourceConnection} from './desktop';

export type PickKind = 'file' | 'folder' | 'vault';
export interface Added {count: number; ids: string[]; label: string}

/** Connect what the person chose, then put it in the library at once. Reading it happens afterwards, in the background. */
async function addConnections(connections: SourceConnection[], record: string, folder: string): Promise<Added> {
  const ids: string[] = [];
  for (const connection of connections) {
    const out = await human<{ids: string[]}>('library_add', {source: connection.id, ...(folder ? {folder} : {})}, record);
    ids.push(...out.ids);
  }
  window.dispatchEvent(new Event('ros:library-changed')); window.dispatchEvent(new Event('ros:organization-changed')); window.dispatchEvent(new Event('ros:records-changed'));
  return {count: ids.length, ids, label: connections.length === 1 ? connections[0].label : `${connections.length} files`};
}

/** The desktop app opens the system picker. Nothing is read until the person picks. Returns null when they cancel. */
export async function pickAndAdd(kind: PickKind, record: string, folder = ''): Promise<Added | null> {
  const desktop = window.researchDesktop;
  if (!desktop) throw new Error('Choose a path below. Opening the system file picker needs the desktop app.');
  const picked = await desktop.pickSource(kind, record, true);
  if (!picked) return null;
  return addConnections(Array.isArray(picked) ? picked : [picked], record, folder);
}

/** Browser fallback for a development session without the desktop shell. */
export async function pathAndAdd(root: string, kind: PickKind, record: string, folder = ''): Promise<Added> {
  const connection = await human<SourceConnection>('source_register', {root: root.trim(), kind, local_only: true}, record);
  return addConnections([connection], record, folder);
}

export const describe = (added: Added) => added.count === 1 ? 'Added 1 item. It is being read now.' : `Added ${added.count} items from ${added.label}. They are being read now.`;
