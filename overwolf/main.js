/** Main process: opens the coach window and forwards Overwolf's TFT game events to it. */
import { app, BrowserWindow, ipcMain, screen } from "electron";
import path from "node:path";
import { fileURLToPath } from "node:url";

// Augment data is left out on purpose: Riot doesn't allow third-party apps to show it.
const FEATURES = ["me", "match_info", "store", "board", "bench"];
// kGepSupportedGameIds lists TFT on its own id; League of Legends, which TFT runs in, is accepted too.
const GAME_IDS = [21570, 5426];

const here = path.dirname(fileURLToPath(import.meta.url));
let window = null;
let listening = false; // the window has loaded its data and asked for the game state
let gep = null;
let activeGame = null;

function send(channel, payload) {
  if (listening && window) window.webContents.send(channel, payload);
}

function createWindow() {
  // Like the Python coach: open on the other monitor if there is one, so it sits next to the game.
  const primary = screen.getPrimaryDisplay();
  const other = screen.getAllDisplays().find((display) => display.id !== primary.id);
  const position = other ? { x: other.bounds.x + 20, y: other.bounds.y + 40 } : {};
  window = new BrowserWindow({
    ...position, width: 900, height: 760, minWidth: 640, minHeight: 480,
    backgroundColor: "#101a17", alwaysOnTop: true, autoHideMenuBar: true,
    icon: path.join(here, "icons", "icon.png"),
    webPreferences: { preload: path.join(here, "preload.cjs") },
  });
  window.removeMenu();
  window.loadFile(path.join(here, "coach.html"));
  window.on("closed", () => {
    window = null;
    listening = false;
  });
}

/** The state so far, for a window that finished loading after the game started. */
async function sendState() {
  if (!gep || activeGame === null) return;
  try {
    send("info", await gep.getInfo(activeGame));
  } catch (error) {
    console.error("getInfo failed:", error);
  }
}

function watchGames() {
  gep.removeAllListeners();
  for (const gameId of GAME_IDS) {
    gep.setRequiredFeatures(gameId, FEATURES).catch((error) => console.error(`features for ${gameId}:`, error));
  }
  gep.on("game-detected", (event, gameId) => {
    if (!GAME_IDS.includes(gameId)) return;
    event.enable();
    activeGame = gameId;
    sendState();
  });
  gep.on("game-exit", (event, gameId) => {
    if (gameId === activeGame) activeGame = null;
  });
  gep.on("new-info-update", (event, gameId, data) => send("info", { [data.category]: { [data.key]: data.value } }));
  gep.on("new-game-event", (event, gameId, data) => send("event", data.key));
  gep.on("elevated-privileges-required", () => {
    send("problem", "The game runs as administrator: run TFT Coach as administrator too.");
  });
  gep.on("error", (event, gameId, error) => console.error("game events error:", gameId, error));
}

ipcMain.on("ready", () => {
  listening = true;
  sendState();
});
app.overwolf.packages.on("ready", (event, name) => {
  if (name !== "gep") return;
  gep = app.overwolf.packages.gep;
  watchGames();
});
app.overwolf.packages.on("failed-to-initialize", (event, name) => {
  if (name === "gep") send("problem", "Overwolf's game events couldn't start, so the game can't be read.");
});

app.whenReady().then(createWindow);
app.on("window-all-closed", () => app.quit());
