"""Runs when you comment on a draft issue.
  yes / approve  -> post to Instagram
  no / skip      -> throw the draft away
  anything else  -> treat it as a change request, redo the post, send the new version
"""
import datetime
import os
import pathlib
import re

from github_helpers import (ROOT, commit_and_push, gh, image_row, issue_body, load_draft,
                            raw_base, write_draft)

issue = os.environ["ISSUE_NUMBER"]
comment = os.environ.get("COMMENT_BODY", "").strip()
first = re.sub(r"[^a-z]", "", comment.lower().split()[0]) if comment else ""
APPROVE = {"yes", "y", "approve", "approved", "post", "postit", "ship", "lgtm", "ok", "okay"}
SKIP = {"no", "n", "skip", "reject", "cancel", "delete", "nope"}

m = re.search(r"<!-- draft:(\S+) sha:([0-9a-f]+) -->", os.environ.get("ISSUE_BODY", ""))
if not m:
    raise SystemExit("Not a draft issue.")
draft_id, sha = m.groups()
draft = load_draft(draft_id)


def reply(text, close=False):
    gh("issue", "comment", issue, "--body", text)
    if close:
        gh("issue", "close", issue)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


short_answer = len(comment.split()) <= 3

if first in SKIP and short_answer:
    draft.update(status="skipped", decided=now())
    write_draft(draft)
    commit_and_push(f"Skip {draft_id}")
    reply("Okay, skipped. This one won't be posted.", close=True)

elif first in APPROVE and short_answer:
    from publish import InstagramError, publish
    urls = [f"{raw_base(draft_id, sha)}/{n}" for n in draft["slides"]]
    try:
        link = publish(urls, draft["caption"])
    except InstagramError as e:
        reply(f"Posting failed: {e}\n\nNothing was posted. Reply **yes** to try again.")
        raise SystemExit(1)
    draft.update(status="posted", decided=now(), permalink=link)
    write_draft(draft)
    commit_and_push(f"Posted {draft_id}")
    reply(f"Posted to Instagram! {link}".strip(), close=True)

else:
    # A change request: redo the post with the feedback, then send the new version.
    os.environ["FEEDBACK"] = comment
    import generate
    reply("Got it, working on those changes. The new version will show up here in about a minute.")
    generate.revise(draft_id, comment)
    new_sha = commit_and_push(f"Revise {draft_id}")
    body_file = pathlib.Path(ROOT / "issue_body.md")
    body_file.write_text(issue_body(draft_id, new_sha), encoding="utf-8")
    gh("issue", "edit", issue, "--body-file", str(body_file))
    d = load_draft(draft_id)
    reply(f"Here's version {d['version']}:\n\n{image_row(draft_id, new_sha, d['slides'], 200)}\n\n"
          f"**Caption:**\n```\n{d['caption']}\n```\n\nReply **yes** to post, **no** to skip, "
          "or tell me what else to change.")
