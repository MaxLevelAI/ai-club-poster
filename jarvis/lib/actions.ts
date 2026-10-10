// Every control in the HUD ends up here. Each one changes the real agent on GitHub.
import "server-only";
import { ghGet, ghSend, REPO } from "./github";

export type Action =
  | { type: "approve"; issue: number }
  | { type: "reject"; issue: number }
  | { type: "revise"; issue: number; text: string }
  | { type: "generate"; topic?: string }
  | { type: "pause" }
  | { type: "resume" }
  | { type: "kill" }
  | { type: "restore" }
  | { type: "require_approval"; value: boolean };

// Turning a workflow on/off. "Already off" (or on) counts as success.
const wf = (file: string, what: "enable" | "disable") =>
  ghSend("PUT", `/repos/${REPO}/actions/workflows/${file}/${what}`).catch((e) => {
    if (/not active|already/i.test(e.message)) return null;
    throw e;
  });

async function ensureDraftIssue(issue: number) {
  const i = await ghGet(`/repos/${REPO}/issues/${issue}`, 0);
  if (!i || !/^Draft post:/.test(i.title)) throw new Error(`#${issue} isn't a draft post.`);
  if (i.state !== "open") throw new Error(`#${issue} is already closed.`);
}

export async function runAction(a: Action): Promise<string> {
  switch (a.type) {
    case "approve":
      await ensureDraftIssue(a.issue);
      await ghSend("POST", `/repos/${REPO}/issues/${a.issue}/comments`, { body: "yes" });
      return `Approved #${a.issue}. Posting to Instagram now.`;
    case "reject":
      await ensureDraftIssue(a.issue);
      await ghSend("POST", `/repos/${REPO}/issues/${a.issue}/comments`, { body: "no" });
      return `Rejected #${a.issue}. It won't be posted.`;
    case "revise": {
      const text = (a.text || "").trim();
      if (text.split(/\s+/).length < 4) throw new Error("Describe the change in at least 4 words.");
      await ensureDraftIssue(a.issue);
      await ghSend("POST", `/repos/${REPO}/issues/${a.issue}/comments`, { body: text.slice(0, 1500) });
      return `Sent your changes for #${a.issue}. New version in about a minute.`;
    }
    case "generate":
      await ghSend("POST", `/repos/${REPO}/actions/workflows/draft.yml/dispatches`, {
        ref: "main",
        inputs: a.topic ? { topic: a.topic.slice(0, 200) } : {},
      });
      return "New post run started. It will show up for approval in a few minutes.";
    case "pause":
      await wf("draft.yml", "disable");
      return "Schedule paused. No new drafts until you resume.";
    case "resume":
      await wf("draft.yml", "enable");
      return "Schedule resumed.";
    case "kill": {
      await wf("draft.yml", "disable");
      await wf("reply.yml", "disable");
      const runs = await ghGet(`/repos/${REPO}/actions/runs?per_page=20`, 0);
      const live = (runs?.workflow_runs || []).filter((r: any) => r.status !== "completed");
      await Promise.all(live.map((r: any) => ghSend("POST", `/repos/${REPO}/actions/runs/${r.id}/cancel`).catch(() => null)));
      return `Kill switch engaged. Agent stopped${live.length ? `, ${live.length} run(s) cancelled` : ""}. Nothing can post.`;
    }
    case "restore":
      await wf("draft.yml", "enable");
      await wf("reply.yml", "enable");
      return "Agent restored. Schedule and replies are back on.";
    case "require_approval": {
      const value = a.value ? "true" : "false";
      try {
        await ghSend("PATCH", `/repos/${REPO}/actions/variables/REQUIRE_APPROVAL`, { name: "REQUIRE_APPROVAL", value });
      } catch (e: any) {
        if (e.status !== 404) throw e;
        await ghSend("POST", `/repos/${REPO}/actions/variables`, { name: "REQUIRE_APPROVAL", value });
      }
      return a.value ? "Approval required. Nothing posts without your yes." : "Approval OFF. New drafts will post by themselves.";
    }
  }
  throw new Error("Unknown action");
}
