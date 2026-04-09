export const LOL_ROLE_OPTIONS = [
  { value: "TOP", label: "Top" },
  { value: "JUNGLE", label: "Jungle" },
  { value: "MID", label: "Mid" },
  { value: "BOT", label: "Bot" },
  { value: "SUPPORT", label: "Support" },
] as const;

export const PLATFORM_OPTIONS = [
  { value: "NA1", label: "NA1" },
  { value: "EUW1", label: "EUW1" },
  { value: "KR", label: "KR" },
  { value: "LA1", label: "LA1" },
] as const;

// Fallback list used only if `/champions` is unavailable.
// Primary source for the full LoL roster is the backend champions endpoint.
export const FALLBACK_LOL_CHAMPIONS = [
  "Aatrox",
  "Ahri",
  "Azir",
  "Jinx",
  "Kai'Sa",
  "Lee Sin",
  "Lulu",
  "Nautilus",
  "Orianna",
  "Ornn",
  "Rakan",
  "Sejuani",
  "Thresh",
  "Vi",
  "Yone",
  "Zeri",
] as const;
