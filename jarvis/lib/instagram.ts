// Server-only Instagram Graph API reads (followers, recent posts, audience by country).
import "server-only";

const GRAPH = "https://graph.facebook.com/v26.0";
const g = globalThis as any;
const cache: Map<string, { data: any; at: number }> = g.__jarvisIg || (g.__jarvisIg = new Map());

async function get(path: string, params: Record<string, string>, fresh = 60000) {
  const token = process.env.IG_PAGE_TOKEN;
  if (!token) throw new Error("IG_PAGE_TOKEN is not set");
  const q = new URLSearchParams({ ...params, access_token: token });
  const url = `${GRAPH}${path}?${q}`;
  const key = `${path}?${new URLSearchParams(params)}`;
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < fresh) return hit.data;
  const res = await fetch(url, { cache: "no-store" });
  const json = await res.json().catch(() => ({}));
  if (!res.ok || json.error) {
    if (hit) return hit.data;
    throw new Error(json.error?.message || `Instagram ${res.status}`);
  }
  cache.set(key, { data: json, at: Date.now() });
  return json;
}

export type IgPost = {
  id: string;
  caption: string;
  image: string;
  permalink: string;
  timestamp: string;
  likes: number;
  comments: number;
};

export async function igSnapshot() {
  const ig = process.env.IG_USER_ID || "17841426927209902";
  const out: {
    ok: boolean;
    error?: string;
    followers: number | null;
    mediaCount: number | null;
    posts: IgPost[];
    countries: { code: string; value: number }[] | null;
    reach: number | null;
  } = { ok: false, followers: null, mediaCount: null, posts: [], countries: null, reach: null };

  try {
    const [acct, media] = await Promise.all([
      get(`/${ig}`, { fields: "followers_count,media_count,username" }),
      get(`/${ig}/media`, {
        fields: "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp,like_count,comments_count",
        limit: "12",
      }),
    ]);
    out.ok = true;
    out.followers = acct.followers_count ?? null;
    out.mediaCount = acct.media_count ?? null;
    out.posts = (media.data || []).map((m: any) => ({
      id: m.id,
      caption: m.caption || "",
      image: m.thumbnail_url || m.media_url || "",
      permalink: m.permalink,
      timestamp: m.timestamp,
      likes: m.like_count || 0,
      comments: m.comments_count || 0,
    }));
  } catch (e: any) {
    out.error = e.message;
    return out;
  }

  // Extras that need the insights permission (and, for countries, 100+ followers).
  // If Instagram says no, the globe just runs in ambient mode.
  try {
    const demo = await get(
      `/${ig}/insights`,
      { metric: "follower_demographics", period: "lifetime", metric_type: "total_value", breakdown: "country" },
      15 * 60000,
    );
    const rows = demo.data?.[0]?.total_value?.breakdowns?.[0]?.results || [];
    if (rows.length) out.countries = rows.map((r: any) => ({ code: r.dimension_values?.[0], value: r.value }));
  } catch {}
  try {
    const r = await get(`/${ig}/insights`, { metric: "reach", period: "day", metric_type: "total_value" }, 10 * 60000);
    out.reach = r.data?.[0]?.total_value?.value ?? null;
  } catch {}
  return out;
}
