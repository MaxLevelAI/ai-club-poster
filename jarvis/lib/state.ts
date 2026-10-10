// Builds the one JSON snapshot the HUD renders. Every number here comes from the agent's real
// storage: GitHub (drafts, issues, workflow runs) and Instagram. Nothing is invented.
import "server-only";
import { ghGet, rawGet, REPO } from "./github";
import { igSnapshot } from "./instagram";

const TOPIC_FORMATS = ["explainer", "terminal log", "myth vs fact", "versus", "quiz", "framework", "big ideas"];
const COVERS = ["art", "terminal", "center"];
const SCHEDULE_UTC = [
  [13, 7],
  [22, 7],
];
// Fallback cost for drafts made before usage tracking was added (one high-quality image + text).
const EST_COST_PER_VERSION = 0.004;
const EST_IMAGE_COST = 0.25;
const EST_TOKENS_PER_VERSION = 5500;

export type LogLine = { t: string; level: "info" | "ok" | "warn" | "error" | "step"; text: string };

function nextRun(now: Date) {
  for (let d = 0; d < 2; d++) {
    for (const [h, m] of SCHEDULE_UTC) {
      const t = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + d, h, m));
      if (t > now) return t;
    }
  }
  return null;
}

const MARK = /<!-- draft:(\S+) sha:([0-9a-f]+) -->/;
const NOISE = /^(Set up job|Complete job|Post |Run actions\/|Run pip|Run git)/;

export async function buildState() {
  const now = new Date();
  const errors: { source: string; msg: string }[] = [];
  const safe = async <T,>(source: string, p: Promise<T>, fallback: T): Promise<T> => {
    try {
      return await p;
    } catch (e: any) {
      errors.push({ source, msg: e.message || String(e) });
      return fallback;
    }
  };

  const [issues, runsRes, wfRes, dirList, approvalVar, topicsTxt, ig] = await Promise.all([
    safe("github", ghGet(`/repos/${REPO}/issues?state=all&per_page=40&sort=created&direction=desc`, 4000), [] as any[]),
    safe("github", ghGet(`/repos/${REPO}/actions/runs?per_page=20`, 2500), { workflow_runs: [] } as any),
    safe("github", ghGet(`/repos/${REPO}/actions/workflows`, 6000), { workflows: [] } as any),
    safe("github", ghGet(`/repos/${REPO}/contents/drafts?ref=main`, 15000), [] as any[]),
    ghGet(`/repos/${REPO}/actions/variables/REQUIRE_APPROVAL`, 10000, true).catch(() => null),
    rawGet("topics.txt", "main", 60000).catch(() => null),
    igSnapshot().catch((e) => ({ ok: false, error: e.message, followers: null, mediaCount: null, posts: [], countries: null, reach: null })),
  ]);
  if (!ig.ok && ig.error) errors.push({ source: "instagram", msg: ig.error });

  // ---- Workflows (on/off switches) ----
  const wfs: any[] = wfRes.workflows || [];
  const draftWf = wfs.find((w) => w.path?.endsWith("/draft.yml"));
  const replyWf = wfs.find((w) => w.path?.endsWith("/reply.yml"));
  const draftOn = draftWf ? draftWf.state === "active" : null;
  const replyOn = replyWf ? replyWf.state === "active" : null;
  const requireApproval = !(approvalVar && String(approvalVar.value).toLowerCase() === "false");

  // ---- Drafts ----
  const dirs: string[] = (Array.isArray(dirList) ? dirList : []).filter((d: any) => d.type === "dir").map((d: any) => d.name).sort();
  const drafts = (
    await Promise.all(
      dirs.map((id) =>
        ghGet(`/repos/${REPO}/contents/drafts/${id}/draft.json?ref=main`, 15000)
          .then((f: any) => (f?.content ? JSON.parse(Buffer.from(f.content, "base64").toString("utf8")) : null))
          .catch(() => null),
      ),
    )
  ).filter(Boolean) as any[];
  const byId = new Map(drafts.map((d) => [d.id, d]));

  // ---- Topic / format the agent will use next ----
  const topics = String(topicsTxt || "")
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith("#"));
  const n = dirs.length;
  const nextTopic = topics.length ? topics[n % topics.length] : null;
  const nextFormat = TOPIC_FORMATS[n % TOPIC_FORMATS.length];
  const nextCover = COVERS[n % COVERS.length];

  // ---- Queue: open draft issues ----
  const draftIssues = (Array.isArray(issues) ? issues : []).filter((i: any) => !i.pull_request && /^Draft post:/.test(i.title));
  const queue = (
    await Promise.all(
      draftIssues
        .filter((i: any) => i.state === "open")
        .map(async (i: any) => {
          const m = (i.body || "").match(MARK);
          if (!m) return null;
          const [, id, sha] = m;
          const d = (await rawGet(`drafts/${id}/draft.json`, sha, 3600_000).catch(() => null)) || byId.get(id) || {};
          const base = `https://raw.githubusercontent.com/${REPO}/${sha}/drafts/${id}`;
          return {
            issue: i.number,
            url: i.html_url,
            id,
            title: d.title || i.title.replace(/^Draft post:\s*/, ""),
            topic: d.topic || "",
            caption: d.caption || "",
            format: d.format || "",
            version: d.version || 1,
            created: d.created || i.created_at,
            slides: (d.slides || []).map((s: string) => `${base}/${s}`),
            thumb: d.slides?.length ? `${base}/${d.slides[0]}` : null,
          };
        }),
    )
  ).filter(Boolean) as any[];

  // ---- Runs: what's happening right now ----
  const runs: any[] = runsRes.workflow_runs || [];
  const active = runs.filter((r) => r.status === "in_progress" || r.status === "queued" || r.status === "waiting");
  const detailRuns = runs.slice(0, 6);
  const jobsByRun = new Map<number, any[]>();
  await Promise.all(
    detailRuns.map(async (r) => {
      const done = r.status === "completed";
      const j = await ghGet(`/repos/${REPO}/actions/runs/${r.id}/jobs`, done ? 3600_000 : 2000).catch(() => null);
      if (j) jobsByRun.set(r.id, j.jobs || []);
    }),
  );
  const steps = (r: any) =>
    (jobsByRun.get(r.id) || []).flatMap((j: any) => j.steps || []).filter((s: any) => !NOISE.test(s.name));

  let task: any;
  const cur = active[0];
  if (cur) {
    const st = steps(cur);
    const live = st.find((s: any) => s.status === "in_progress") || st.find((s: any) => s.status !== "completed");
    const isDraft = cur.path?.endsWith("draft.yml");
    const issueNum = (cur.display_title || "").match(/#(\d+)/)?.[1];
    task = {
      kind: isDraft ? "draft" : "reply",
      title: live ? live.name : cur.status === "queued" ? "Starting up" : "Booting the run",
      headline: isDraft ? "MAKING A NEW POST" : "ACTING ON YOUR REPLY",
      reasoning: isDraft
        ? [
            `Topic: ${cur.event === "workflow_dispatch" ? "manual request" : nextTopic || "next in topics.txt"}`,
            `Format: ${nextFormat} · cover style: ${nextCover}`,
            "Plan: write slides → generate art → design 1080×1350 → send for approval",
            requireApproval ? "Approval is required: nothing posts until you say yes." : "Approval is OFF: it will post by itself.",
          ]
        : [
            `Draft: ${cur.display_title || ""}${issueNum ? ` (#${issueNum})` : ""}`,
            "Reading your comment: yes = post, no = skip, anything else = revise.",
          ],
      steps: st.map((s: any) => ({ name: s.name, status: s.conclusion || s.status })),
      started: cur.run_started_at || cur.created_at,
      url: cur.html_url,
    };
  } else if (queue.length) {
    const q = queue[0];
    task = {
      kind: "waiting",
      headline: "AWAITING YOUR APPROVAL",
      title: `#${q.issue} ${q.title}`,
      reasoning: [
        `${queue.length} draft${queue.length > 1 ? "s" : ""} ready for review.`,
        `Format: ${q.format || "?"} · version ${q.version} · ${q.slides.length} slides`,
        "Approve, reject, or ask for changes from the queue panel or GitHub.",
      ],
      steps: [],
    };
  } else {
    task = {
      kind: "idle",
      headline: draftOn === false && replyOn === false ? "AGENT HALTED" : draftOn === false ? "SCHEDULE PAUSED" : "STANDING BY",
      title: nextTopic ? `Next topic: ${nextTopic}` : "Waiting for the next scheduled run",
      reasoning: [
        `Format queued: ${nextFormat} · cover: ${nextCover}`,
        "Schedule: about 9:07 AM and 6:07 PM Eastern, every day.",
        requireApproval ? "Every post waits for a human yes." : "Approval is OFF.",
      ],
      steps: [],
    };
  }

  // ---- Activity log (built from persisted history: runs, steps, drafts, issues) ----
  const log: LogLine[] = [];
  for (const r of runs) {
    const isDraft = r.path?.endsWith("draft.yml");
    const who = r.event === "schedule" ? "scheduled" : r.event === "workflow_dispatch" ? "manual" : "reply";
    const start = r.run_started_at || r.created_at;
    log.push({
      t: start,
      level: "info",
      text: isDraft ? `AGENT WOKE UP (${who}) · new post run` : `REPLY RECEIVED · ${r.display_title || ""}`,
    });
    for (const s of steps(r)) {
      if (!s.started_at) continue;
      const lvl = s.conclusion === "failure" ? "error" : s.conclusion === "skipped" ? "info" : "step";
      if (s.conclusion === "skipped") continue;
      log.push({ t: s.started_at, level: lvl, text: `${s.name.toUpperCase()}${s.status === "in_progress" ? " …" : ""}` });
    }
    if (r.status === "completed") {
      const t = r.updated_at;
      if (r.conclusion === "success") log.push({ t, level: "ok", text: isDraft ? "RUN COMPLETE" : "REPLY HANDLED" });
      else if (r.conclusion === "failure") log.push({ t, level: "error", text: `RUN FAILED · ${r.name}` });
      else if (r.conclusion === "cancelled") log.push({ t, level: "warn", text: `RUN CANCELLED · ${r.name}` });
    }
  }
  for (const d of drafts) {
    log.push({ t: d.created, level: "ok", text: `DRAFTED “${d.title}” · ${d.format || "post"} · ${d.slides?.length || 0} slides` });
    for (const c of d.changes || []) {
      if (/^(yes|y|ok|approve)/i.test(c.request || "")) continue;
      log.push({ t: c.at, level: "info", text: `REVISION v${c.version}: “${String(c.request).slice(0, 70)}”` });
    }
    if (d.status === "posted" && d.decided) log.push({ t: d.decided, level: "ok", text: `POSTED TO INSTAGRAM · ${d.title}` });
    if (d.status === "skipped" && d.decided) log.push({ t: d.decided, level: "warn", text: `SKIPPED · ${d.title}` });
  }
  for (const i of draftIssues) log.push({ t: i.created_at, level: "info", text: `SENT FOR APPROVAL · #${i.number}` });
  for (const l of log) l.t = new Date(l.t).toISOString();
  log.sort((a, b) => (a.t < b.t ? 1 : -1));

  // ---- Telemetry ----
  let cost = 0,
    tokens = 0,
    estimated = false;
  for (const d of drafts) {
    if (d.usage) {
      cost += d.usage.cost_usd || 0;
      tokens += d.usage.tokens || 0;
    } else {
      estimated = true;
      const v = d.version || 1;
      cost += EST_IMAGE_COST + EST_COST_PER_VERSION * v;
      tokens += EST_TOKENS_PER_VERSION * v;
    }
  }
  const shipped = drafts.filter((d) => d.status === "posted").length;
  const failedRuns = runs.filter((r) => r.conclusion === "failure").length;

  // ---- Published (Instagram, matched to drafts where possible) ----
  const draftByLink = new Map(drafts.filter((d) => d.permalink).map((d) => [d.permalink.replace(/\/$/, ""), d]));
  const published = ig.posts.map((p) => {
    const d = draftByLink.get((p.permalink || "").replace(/\/$/, ""));
    return { ...p, title: d?.title || p.caption.split("\n")[0].slice(0, 60), cost: d?.usage?.cost_usd ?? null };
  });
  const engagementRate =
    ig.followers && published.length
      ? (published.reduce((s, p) => s + p.likes + p.comments, 0) / published.length / ig.followers) * 100
      : null;

  // ---- Status ----
  const githubDown = errors.some((e) => e.source === "github") && !runs.length && !wfs.length;
  let status: "ONLINE" | "WORKING" | "PAUSED" | "KILLED" | "OFFLINE" = "ONLINE";
  if (githubDown) status = "OFFLINE";
  else if (draftOn === false && replyOn === false) status = "KILLED";
  else if (cur) status = "WORKING";
  else if (draftOn === false) status = "PAUSED";
  const onlineSince = draftOn && draftWf?.updated_at ? draftWf.updated_at : drafts[0]?.created || null;

  return {
    now: now.toISOString(),
    repo: REPO,
    status,
    onlineSince,
    errors,
    task,
    queue,
    published,
    log: log.slice(0, 80),
    settings: {
      requireApproval,
      schedule: draftOn,
      replies: replyOn,
      igLinked: ig.ok,
      voice: Boolean(process.env.ELEVENLABS_API_KEY),
      brain: Boolean(process.env.OPENAI_API_KEY),
    },
    nextPost: draftOn === false ? null : nextRun(now)?.toISOString() || null,
    nextTopic,
    nextFormat,
    stats: {
      shipped,
      drafts: drafts.length,
      cost,
      costPerPost: shipped ? cost / shipped : null,
      costEstimated: estimated,
      tokens,
      queueDepth: queue.length,
      errors: failedRuns + errors.length,
    },
    audience: {
      followers: ig.followers,
      mediaCount: ig.mediaCount,
      reach: ig.reach,
      countries: ig.countries,
      engagementRate,
    },
    runs: runs.slice(0, 20).map((r) => ({
      name: r.name,
      status: r.status,
      conclusion: r.conclusion,
      at: r.run_started_at || r.created_at,
      url: r.html_url,
    })),
    lastRun: runs[0] ? { name: runs[0].name, conclusion: runs[0].conclusion, status: runs[0].status, at: runs[0].updated_at, url: runs[0].html_url } : null,
  };
}

export type HudState = Awaited<ReturnType<typeof buildState>>;
