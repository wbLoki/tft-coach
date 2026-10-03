/** Bridge between the main process and the window: game updates in, a "ready" signal out. */
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("game", {
  onInfo: (handler) => ipcRenderer.on("info", (_event, info) => handler(info)),
  onEvent: (handler) => ipcRenderer.on("event", (_event, name) => handler(name)),
  onProblem: (handler) => ipcRenderer.on("problem", (_event, text) => handler(text)),
  ready: () => ipcRenderer.send("ready"),
});
