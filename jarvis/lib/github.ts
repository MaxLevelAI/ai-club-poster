// Server-only GitHub helpers. Uses conditional requests (ETag) so polling every few seconds
// barely touches the rate limit: a 304 "not modified" reply doesn't count against it.
import "server-only";

const API = "https://api.github.com";
export const REPO = process.env.GITHUB_REPO || "MaxLevelAI/ai-club-poster";

type Entry = { etag?: string; data: any; at: number };
const g = globalThis as any;
const cache: Map<string, Entry> = g.__jarvisGh || (g.__jarvisGh = new Map());

export class GhError extends Error {
  status: number;
  constructor(status: number, msg: string) {
    super(msg);
    this.status = status;
  }
}

function headers(extra: Record<string, string> = {}) {
  const h: Record<string, string> = {
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "jarvis-dashboard",
    ...extra,
  };
  if (process.env.GITHUB_TOKEN) h.Authorization = `Bearer ${process.env.GITHUB_TOKEN}`;
  return h;
}

/** GET with an ETag cache. `fresh` = how many ms a cached copy is used without asking again. */
export async function ghGet(path: string, fresh = 3000, allow404 = false): Promise<any> {
  const url = path.startsWith("http") ? path : `${API}${path}`;
  const hit = cache.get(url);
  if (hit && Date.now() - hit.at < fresh) return hit.data;
  const res = await fetch(url, {
    headers: headers(hit?.etag ? { "If-None-Match": hit.etag } : {}),
    cache: "no-store",
  });
  if (res.status === 304 && hit) {
    hit.at = Date.now();
    return hit.data;
  }
  if (res.status === 404 && allow404) {
    cache.set(url, { data: null, at: Date.now() });
    return null;
  }
  if (!res.ok) {
    if (hit) return hit.data; // keep showing the last good copy
    throw new GhError(res.status, `GitHub ${res.status}: ${(await res.text()).slice(0, 160)}`);
  }
  const data = await res.json();
  cache.set(url, { etag: res.headers.get("etag") || undefined, data, at: Date.now() });
  return data;
}

/** Raw file from the public repo (no API rate limit). Cached for `fresh` ms. */
export async function rawGet(path: string, ref = "main", fresh = 15000): Promise<any> {
  const url = `https://raw.githubusercontent.com/${REPO}/${ref}/${path}`;
  const hit = cache.get(url);
  if (hit && Date.now() - hit.at < fresh) return hit.data;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    if (hit) return hit.data;
    return null;
  }
  const text = await res.text();
  let data: any = text;
  if (path.endsWith(".json")) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  cache.set(url, { data, at: Date.now() });
  return data;
}

/** Write call (POST/PUT/PATCH/DELETE). Throws GhError with a readable message. */
export async function ghSend(method: string, path: string, body?: any) {
  if (!process.env.GITHUB_TOKEN) throw new GhError(500, "GITHUB_TOKEN is not set on the server.");
  const res = await fetch(`${API}${path}`, {
    method,
    headers: headers(body ? { "Content-Type": "application/json" } : {}),
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  if (!res.ok) {
    const t = await res.text();
    let msg = t;
    try {
      msg = JSON.parse(t).message || t;
    } catch {}
    throw new GhError(res.status, `GitHub ${res.status}: ${msg.slice(0, 200)}`);
  }
  // Writes change what reads should return, so drop the cache.
  cache.clear();
  return res.status === 204 ? null : res.json().catch(() => null);
}
