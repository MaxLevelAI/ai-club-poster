"""After a new draft is saved, open a GitHub issue with the slides so your phone gets a
notification and you can answer yes / no / change requests."""
import pathlib

from github_helpers import ROOT, commit_and_push, gh, issue_body, load_draft, write_draft

draft_id = (ROOT / "drafts" / "LATEST").read_text().strip()
sha = commit_and_push(f"Draft {draft_id}")
d = load_draft(draft_id)

body_file = pathlib.Path(ROOT / "issue_body.md")
body_file.write_text(issue_body(draft_id, sha), encoding="utf-8")
url = gh("issue", "create", "--title", f"Draft post: {d['title']}", "--body-file", str(body_file)).stdout.strip()
print(f"Sent for approval: {url}")

d["issue"] = int(url.rstrip("/").split("/")[-1])
write_draft(d)
commit_and_push(f"Link draft {draft_id} to issue #{d['issue']}")
