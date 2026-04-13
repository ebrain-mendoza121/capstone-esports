export const LOL_ROLE_OPTIONS = [
  { value: "TOP", label: "Top" },
  { value: "JUNGLE", label: "Jungle" },
  { value: "MID", label: "Mid" },
  { value: "BOT", label: "Bot" },
  { value: "SUPPORT", label: "Support" },
] as const;

export const PLATFORM_OPTIONS = [
  { value: "NA",   label: "NA — North America" },
  { value: "EUW",  label: "EUW — Europe West" },
  { value: "EUNE", label: "EUNE — Europe Nordic & East" },
  { value: "KR",   label: "KR — Korea" },
  { value: "BR",   label: "BR — Brazil" },
  { value: "LAN",  label: "LAN — Latin America North" },
  { value: "LAS",  label: "LAS — Latin America South" },
  { value: "JP",   label: "JP — Japan" },
  { value: "OCE",  label: "OCE — Oceania" },
  { value: "TR",   label: "TR — Turkey" },
  { value: "RU",   label: "RU — Russia" },
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
