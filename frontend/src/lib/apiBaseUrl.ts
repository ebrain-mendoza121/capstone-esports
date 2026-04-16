function stripTrailingSlash(value: string): string {
  return value.replace(/\/+$/, "");
}

export function normalizeApiBaseUrl(raw: string | undefined): string {
  const value = stripTrailingSlash((raw ?? "").trim());
  if (!value) return "";

  if (value.startsWith("http://")) {
    const host = value.slice("http://".length);

    // Never upgrade localhost — local dev must stay http
    const isLocal =
      host.startsWith("localhost") ||
      host.startsWith("127.0.0.1") ||
      host.startsWith("0.0.0.0");

    if (!isLocal) {
      // Non-localhost http is always wrong in production — force https.
      // This runs safely at module load time (no window dependency).
      return `https://${host}`;
    }
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
