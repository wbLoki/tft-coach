/** Downloads the game data the coach needs, keeping the last good copy for when you are offline. */

// meta.json and static.json are published by .github/workflows/meta.yml; set_data.json lives in the repo.
const SOURCES = {
  meta: "https://raw.githubusercontent.com/wbLoki/tft-coach/meta/meta.json",
  static: "https://raw.githubusercontent.com/wbLoki/tft-coach/meta/static.json",
  set: "https://raw.githubusercontent.com/wbLoki/tft-coach/main/data/set_data.json",
};

/** {set, static, meta}, each null if it can neither be downloaded nor found in the saved copies. */
export async function loadData() {
  const parts = await Promise.all(Object.entries(SOURCES).map(async ([name, url]) => {
    const key = `tft-coach:${name}`;
    try {
      const response = await fetch(url, { cache: "no-cache" });
      if (!response.ok) throw new Error(`${response.status} for ${url}`);
      const text = await response.text();
      const value = JSON.parse(text);
      localStorage.setItem(key, text);
      return [name, value];
    } catch {
      const saved = localStorage.getItem(key);
      return [name, saved ? JSON.parse(saved) : null];
    }
  }));
  return Object.fromEntries(parts);
}
