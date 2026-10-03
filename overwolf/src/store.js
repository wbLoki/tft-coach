/** Game data every module reads: set numbers (set_data.json), names and traits (static.json), meta comps (meta.json). */
export const data = { set: null, static: null, meta: null };

let unitsByApi = new Map();
let unitsByName = new Map();
let itemsByApi = new Map();
let traitNames = new Set();

export function setData(parts) {
  Object.assign(data, parts);
  if (!parts.static) return;
  // Units of the current set that have traits: leaves out minions, summons and "(…)" variants.
  const playable = Object.entries(parts.static.units).filter(([, u]) => u.traits.length && !u.name.includes("("));
  unitsByApi = new Map(playable.map(([api, u]) => [api.toLowerCase(), u]));
  unitsByName = new Map(playable.map(([, u]) => [u.name, u]));
  itemsByApi = new Map(Object.entries(parts.static.items).map(([api, name]) => [api.toLowerCase(), name]));
  traitNames = new Set(Object.values(parts.static.traits));
}

/** The unit (name, cost, traits) behind a game id like 'DA_18_Varus', if it is a playable one. */
export function unit(api) {
  return (api && unitsByApi.get(String(api).toLowerCase())) || null;
}

export function unitNamed(name) {
  return unitsByName.get(name) ?? null;
}

/** The trait an emblem item grants, or null for any other item. */
export function emblemTrait(api) {
  const name = itemsByApi.get(String(api).toLowerCase()) ?? "";
  const trait = name.endsWith(" Emblem") ? name.slice(0, -" Emblem".length) : null;
  return traitNames.has(trait) ? trait : null;
}
