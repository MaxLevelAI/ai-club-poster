# JARVIS: mission control for the Instagram agent

A live 1920×1080 HUD for the AI Club Instagram agent. It reads the agent's real data and its
buttons really control the agent.

## Where the data comes from

| HUD slot | Real source |
|---|---|
| Status core (ONLINE / WORKING / PAUSED / KILLED) | GitHub Actions workflow states + live runs |
| Current task + steps | The running workflow's live step (Writing the slides → Generating the artwork → Designing the slides → Sending for approval) |
| Post queue (approve / reject / revise) | Open "Draft post:" issues + `drafts/<id>/draft.json` |
| Activity log | Workflow runs and steps, draft history (created, revisions, posted, skipped), issues |
| Stats (cost, tokens) | `usage` saved in each `draft.json` (older drafts are estimated, marked EST) |
| Published, followers, engagement | Instagram Graph API |
| Globe | Instagram follower countries (needs 100+ followers), otherwise ambient |
| Countdown | The schedule in `draft.yml` (13:07 and 22:07 UTC) |

## Controls (password protected)

- **Approve / Reject / Request changes**: comments `yes` / `no` / your text on the draft's issue (same as replying on your phone).
- **Generate post now**: starts the "Make a draft post" workflow.
- **Pause / Resume**: turns the scheduled workflow off / on.
- **Kill switch** (hold): turns off both workflows and cancels running ones. Nothing can post until you hold **Restore**.
- **Require approval** (default ON): repo variable `REQUIRE_APPROVAL`. Turning it off makes new drafts post by themselves.

## Voice

Press the mic (or Space) and talk; works in Chrome or Edge. OpenAI answers using the live HUD data
and ElevenLabs speaks the answer. If JARVIS proposes an action, nothing happens until you press
CONFIRM (or say "confirm"). Without ElevenLabs it uses the browser's voice. You can also type.

## Environment variables

| Name | Value |
|---|---|
| `GITHUB_TOKEN` | Fine-grained token for `ai-club-poster`: Actions RW, Contents R, Issues RW, Variables RW |
| `GITHUB_REPO` | `MaxLevelAI/ai-club-poster` |
| `IG_PAGE_TOKEN` | Same Page token as the GitHub secret |
| `IG_USER_ID` | `17841426927209902` |
| `CONTROL_PASSWORD` | Any password you choose |
| `OPENAI_API_KEY` | Your OpenAI key |
| `ELEVENLABS_API_KEY` | Your ElevenLabs key |
| `ELEVENLABS_VOICE_ID` | Optional. Any voice ID from your ElevenLabs Voices page |

## Run locally

```
cd jarvis
npm install
cp .env.example .env.local   # fill it in
npm run dev                  # open http://localhost:3000
```

## Deploy

Vercel → Add New → Project → import `ai-club-poster` → set **Root Directory** to `jarvis` →
add the environment variables → Deploy.
