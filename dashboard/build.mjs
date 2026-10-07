// Vercel runs this on every push: it gathers every draft into site/data.json
// and copies the slide images next to the dashboard page.
import fs from "node:fs";
import path from "node:path";

const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const out = path.join(root, "site");
fs.rmSync(out, { recursive: true, force: true });
fs.mkdirSync(out, { recursive: true });
fs.copyFileSync(path.join(root, "dashboard", "index.html"), path.join(out, "index.html"));

// Club name for the page title, read from config.py
const cfg = fs.readFileSync(path.join(root, "config.py"), "utf8");
const club = (cfg.match(/^CLUB_NAME\s*=\s*"([^"]*)"/m) || [, "AI Club"])[1];
const handle = (cfg.match(/^INSTAGRAM_HANDLE\s*=\s*"([^"]*)"/m) || [, ""])[1];

const draftsDir = path.join(root, "drafts");
const drafts = [];
if (fs.existsSync(draftsDir)) {
  for (const id of fs.readdirSync(draftsDir)) {
    const file = path.join(draftsDir, id, "draft.json");
    if (!fs.existsSync(file)) continue;
    const d = JSON.parse(fs.readFileSync(file, "utf8"));
    fs.mkdirSync(path.join(out, "drafts", id), { recursive: true });
    for (const s of d.slides || []) {
      fs.copyFileSync(path.join(draftsDir, id, s), path.join(out, "drafts", id, s));
    }
    drafts.push({
      id, topic: d.topic, title: d.title, caption: d.caption, status: d.status,
      version: d.version || 1, created: d.created, decided: d.decided || null,
      permalink: d.permalink || null, changes: d.changes || [],
      slides: (d.slides || []).map((s) => `drafts/${id}/${s}`),
    });
  }
}
drafts.sort((a, b) => (a.created < b.created ? 1 : -1));
fs.writeFileSync(path.join(out, "data.json"),
  JSON.stringify({ club, handle, built: new Date().toISOString(), drafts }, null, 1));
console.log(`Dashboard built with ${drafts.length} drafts`);
