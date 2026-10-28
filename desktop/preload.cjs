'use strict';
const {contextBridge, ipcRenderer} = require('electron');
contextBridge.exposeInMainWorld('researchDesktop', Object.freeze({
  pickSource: (kind, record, localOnly) => ipcRenderer.invoke('source:pick', {kind, record, localOnly}),
  openSource: (source, relativePath, record, reveal, obsidian = false) => ipcRenderer.invoke('source:open', {source, relativePath, record, reveal, obsidian}),
  backend: () => ipcRenderer.invoke('backend:state'),
  updates: () => ipcRenderer.invoke('updates:status'),
  checkUpdates: () => ipcRenderer.invoke('updates:check'),
  installUpdate: () => ipcRenderer.invoke('updates:install'),
  openExternal: url => ipcRenderer.invoke('external:open', url),
}));
