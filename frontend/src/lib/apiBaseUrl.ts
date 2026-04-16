function stripTrailingSlash(value: string): string {
  return value.replace(/\/+$/, "");
}

export function normalizeApiBaseUrl(raw: string | undefined): string {
  const value = stripTrailingSlash((raw ?? "").trim());
  if (!value) return "";

  // If the frontend is served over HTTPS, force HTTPS for API calls as well.
  if (typeof window !== "undefined" && window.location.protocol === "https:" && value.startsWith("http://")) {
    return `https://${value.slice("http://".length)}`;
  }

  return value;
}

export function getApiBaseUrl(): string {
  return normalizeApiBaseUrl(process.env.NEXT_PUBLIC_API_URL);
}

export function buildApiUrl(path: string): string {
  const base = getApiBaseUrl();
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${base}${normalizedPath}`;
}
