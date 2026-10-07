"""Small helpers for saving to the repo and talking to GitHub issues (used inside Actions)."""
import json
import os
import pathlib
import subprocess
import time

ROOT = pathlib.Path(__file__).parent
REPO = os.environ.get("GITHUB_REPOSITORY", "")
OWNER = os.environ.get("GITHUB_REPOSITORY_OWNER", REPO.split("/")[0] if REPO else "")


def sh(*args, check=True):
    return subprocess.run(args, check=check, text=True, capture_output=True)


def commit_and_push(message):
    """Commit everything under drafts/ and push, retrying if another run pushed first."""
    sh("git", "config", "user.name", "github-actions[bot]")
    sh("git", "config", "user.email", "41898283+github-actions[bot]@users.noreply.github.com")
    sh("git", "add", "drafts")
    if sh("git", "diff", "--cached", "--quiet", check=False).returncode == 0:
        return head_sha()
    sh("git", "commit", "-m", message)
    for attempt in range(5):
        if sh("git", "push", check=False).returncode == 0:
            return head_sha()
        sh("git", "pull", "--rebase", "-X", "theirs", check=False)
        time.sleep(3 + attempt * 3)
    raise SystemExit("Could not push to the repo after several tries.")


def head_sha():
    return sh("git", "rev-parse", "HEAD").stdout.strip()


def load_draft(draft_id):
    return json.loads((ROOT / "drafts" / draft_id / "draft.json").read_text(encoding="utf-8"))


def write_draft(meta):
    (ROOT / "drafts" / meta["id"] / "draft.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def raw_base(draft_id, sha):
    return f"https://raw.githubusercontent.com/{REPO}/{sha}/drafts/{draft_id}"


def image_row(draft_id, sha, names, width=230):
    base = raw_base(draft_id, sha)
    return "\n".join(f'<img src="{base}/{n}" width="{width}">' for n in names)


def issue_body(draft_id, sha):
    d = load_draft(draft_id)
    changes = ""
    if d.get("changes"):
        changes = "\n**Changes so far:**\n" + "\n".join(
            f"- v{c['version']}: {c['request']}" for c in d["changes"]) + "\n"
    return f"""@{OWNER} the agent made a new post. Should it go on Instagram?

**Topic:** {d['topic']}  ·  **Version {d.get('version', 1)}**

{image_row(draft_id, sha, d['slides'])}

**Caption:**
```
{d['caption']}
```
{changes}
---
### Reply to this
- **yes** (or **approve**) to post it now
- **no** (or **skip**) to throw it away
- **Anything else** is treated as a change request, for example:
  *"make the title shorter"*, *"slide 2 is too technical"*, *"new background with robots"*.
  The agent redoes the post and sends you the new version here.

<!-- draft:{draft_id} sha:{sha} -->
"""


def gh(*args):
    return sh("gh", *args, "--repo", REPO)
