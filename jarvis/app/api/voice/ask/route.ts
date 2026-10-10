// JARVIS's brain: your words + the live HUD state -> a short spoken answer (OpenAI).
// It can also PROPOSE an action (e.g. "approve #10"); the HUD asks you to confirm before it runs.
import { authorized, deny } from "@/lib/auth";
import { buildState } from "@/lib/state";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const PERSONA = `You are JARVIS, the mission-control voice of an AI club's Instagram agent.
The agent writes carousel posts about AI agents twice a day, makes art with OpenAI, designs slides,
and sends each draft to a club member for approval before it posts.
You speak out loud, so:
- Answer in 1-3 short sentences. No lists, no markdown, no emoji, no URLs.
- Be calm, precise and a little dry-witted. Use real numbers from the state. Never invent numbers.
- Say money like "about 25 cents". Say times in Eastern time.
- If you don't know, say so briefly.
You may propose ONE action when the user clearly asks for it. Allowed actions:
  {"type":"generate","topic":"optional topic"} | {"type":"pause"} | {"type":"resume"} |
  {"type":"approve","issue":N} | {"type":"reject","issue":N} | {"type":"revise","issue":N,"text":"the change"} |
  {"type":"require_approval","value":true|false} | {"type":"kill"} | {"type":"restore"}
Only use issue numbers that are in the queue. The user will confirm on screen before anything runs,
so phrase the reply as "Ready to ... confirm on screen." when you propose one.
Reply as JSON: {"say":"...","action":null or one action object}`;

function brief(s: any) {
  return JSON.stringify({
    now_utc: s.now,
    status: s.status,
    task: s.task,
    queue: (s.queue || []).map((q: any) => ({ issue: q.issue, title: q.title, version: q.version, format: q.format })),
    next_post_utc: s.nextPost,
    next_topic: s.nextTopic,
    settings: s.settings,
    stats: s.stats,
    audience: s.audience,
    recent_posts: (s.published || []).slice(0, 5).map((p: any) => ({ title: p.title, likes: p.likes, comments: p.comments, at: p.timestamp })),
    recent_log: (s.log || []).slice(0, 12),
    errors: s.errors,
  });
}

export async function POST(req: Request) {
  if (!authorized(req)) return deny();
  const key = process.env.OPENAI_API_KEY;
  if (!key) return Response.json({ ok: false, error: "OPENAI_API_KEY isn't set on the server." }, { status: 500 });
  const { text, history = [] } = await req.json();
  if (!text || typeof text !== "string") return Response.json({ ok: false, error: "Say something first." }, { status: 400 });

  const state = await buildState().catch(() => null);
  const messages = [
    { role: "system", content: PERSONA },
    { role: "system", content: `LIVE STATE: ${state ? brief(state) : "unavailable (offline)"}` },
    ...history.slice(-8).map((h: any) => ({ role: h.role === "assistant" ? "assistant" : "user", content: String(h.content).slice(0, 800) })),
    { role: "user", content: text.slice(0, 800) },
  ];
  const res = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      model: process.env.JARVIS_MODEL || "gpt-4.1-mini",
      messages,
      temperature: 0.5,
      max_tokens: 220,
      response_format: { type: "json_object" },
    }),
  });
  const j = await res.json().catch(() => ({}));
  if (!res.ok) return Response.json({ ok: false, error: j.error?.message || `OpenAI ${res.status}` }, { status: 502 });
  let out: any = {};
  try {
    out = JSON.parse(j.choices?.[0]?.message?.content || "{}");
  } catch {}
  const say = String(out.say || "I didn't catch that.").slice(0, 600);
  const allowed = ["generate", "pause", "resume", "approve", "reject", "revise", "require_approval", "kill", "restore"];
  const action = out.action && allowed.includes(out.action.type) ? out.action : null;
  return Response.json({ ok: true, say, action });
}
