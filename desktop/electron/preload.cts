import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('myocontrol', {
  request: (method: string, params: Record<string, unknown> = {}) =>
    ipcRenderer.invoke('runtime:request', method, params),
  subscribe: (callback: (event: unknown) => void) => {
    const listener = (_event: Electron.IpcRendererEvent, value: unknown) => callback(value)
    ipcRenderer.on('runtime:event', listener)
    return () => ipcRenderer.removeListener('runtime:event', listener)
  },
  importRecording: (participantKey: string) => ipcRenderer.invoke('desktop:import', participantKey),
  importDemo: () => ipcRenderer.invoke('desktop:demo'),
  importModel: () => ipcRenderer.invoke('desktop:model'),
  exportRecording: (identifier: string) => ipcRenderer.invoke('desktop:export', identifier),
  restart: () => ipcRenderer.invoke('desktop:restart'),
  identity: () => ipcRenderer.invoke('cloud:identity'),
  login: (body: { base: string; email: string; password: string }) =>
    ipcRenderer.invoke('cloud:login', body),
  logout: () => ipcRenderer.invoke('cloud:logout'),
})
