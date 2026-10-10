# AI Club Instagram Agent

An AI agent that runs the club's Instagram. Twice a day it picks a topic, writes a
5-slide carousel, generates artwork with OpenAI, designs the slides, and sends them to
your phone. You reply:

- **yes**: it posts to Instagram
- **no**: it throws the draft away
- **anything else** (like "make slide 2 simpler"): it redoes the post and sends the new version

JARVIS, a live mission-control dashboard on Vercel, shows the agent working in real time and can
control it (approve, pause, kill switch, voice). See `jarvis/README.md`.

## One-time setup

1. **Put this code in a GitHub repo** named `ai-club-poster`, set to **Public**.
   (Instagram downloads the images from a public link. Your keys stay private.)
2. **Add secrets** in the repo: Settings, Secrets and variables, Actions, New repository secret.
   - `OPENAI_API_KEY`: your OpenAI key
   - `IG_PAGE_TOKEN`: the Page token that never expires
   - `IG_USER_ID`: `17841426927209902`
3. **Phone alerts:** install the GitHub app, sign in, allow notifications.
4. **Dashboard:** on vercel.com, Add New, Project, import `ai-club-poster`, set Root Directory
   to `jarvis`, add the environment variables from `jarvis/README.md`, Deploy.
5. **First post:** Actions tab, Make a draft post, Run workflow.

After that it runs by itself. You never upload anything again.

## Change things

- **Next meeting, guest, register link, club name, colors:** `config.py` (meeting slides hide themselves after the meeting date)
- **Topics:** `topics.txt` (one per line, used in order)
- **Times:** the `cron` lines in `.github/workflows/draft.yml` (UTC)
- **One-off topic:** Actions, Make a draft post, Run workflow, type a topic

## If something goes wrong

- **Image step fails mentioning "verification":** OpenAI requires organization
  verification for its image model. Do it at platform.openai.com, Settings,
  Organization, then run again.
- **"model not found":** OpenAI renamed a model. Add a repo Variable `TEXT_MODEL` or
  `IMAGE_MODEL` with the new name (Settings, Secrets and variables, Actions, Variables).
- **Posting fails:** the agent comments the reason on the issue. Reply **yes** to retry.
- **"permission denied" when saving:** Settings, Actions, General, Workflow permissions,
  choose Read and write, Save.

Cost: about $0.15 to $0.25 per post at high image quality, so roughly $10 to $15 a month
at 2 posts a day. Set `IMAGE_QUALITY` to `medium` in `config.py` to cut that by about 75%.

Fonts: Inter, Space Grotesk and JetBrains Mono, used under the SIL Open Font License (see `fonts/`).
