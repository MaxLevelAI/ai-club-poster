"""The AI agent's "make a post" brain.

  python generate.py                      make a brand-new draft (needs OPENAI_API_KEY)
  python generate.py --revise <draft_id>  redo a draft using the FEEDBACK env variable
  python generate.py --demo               no API calls, just tests the slide design

Text comes from an OpenAI text model, the artwork from an OpenAI image model, and the
slides are drawn here with Pillow so the words are always sharp and spelled right.
"""
import base64
import datetime
import io
import json
import os
import pathlib
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

import config

W, H = 1080, 1350  # Instagram portrait (4:5)
M = 88             # side margin
ROOT = pathlib.Path(__file__).parent
DRAFTS = ROOT / "drafts"
FONTS = ROOT / "fonts"


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


A1, A2 = hex_rgb(config.ACCENT), hex_rgb(config.ACCENT_2)
WHITE, SOFT, DIM = (255, 255, 255), (214, 219, 245), (160, 166, 200)


# ================================================================ topics
def pick_topic():
    if os.getenv("TOPIC", "").strip():
        return os.getenv("TOPIC").strip()
    lines = (ROOT / "topics.txt").read_text(encoding="utf-8").splitlines()
    topics = [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]
    used = len([p for p in DRAFTS.glob("*") if p.is_dir()]) if DRAFTS.exists() else 0
    return topics[used % len(topics)]


# ================================================================ OpenAI
PLAN_SHAPE = """{
  "title": "cover title, max 7 words",
  "subtitle": "cover subtitle, max 12 words",
  "slides": [
    {"heading": "max 6 words", "body": "max 28 words"},
    {"heading": "...", "body": "..."},
    {"heading": "...", "body": "..."}
  ],
  "caption": "Instagram caption: 2-4 short sentences, 1-3 emojis allowed, mention that an AI agent made this post, end with a question or an invite to the next meeting",
  "hashtags": ["6 to 10 relevant hashtags, e.g. #AgenticAI"],
  "image_prompt": "a vivid description of a background illustration that fits the topic"
}"""

NEW_PROMPT = """You write Instagram carousel posts for a student club.
Club name: {name}
About the club: {about}

Write a carousel about this topic: "{topic}"

Rules:
- Audience: students, many are beginners. Friendly, clear, exciting, never cringe.
- Be factually accurate. Never invent dates, meeting times, events, statistics, names or quotes.
- Slide text must be SHORT. No hashtags or emojis on slides.
- The 3 middle slides should teach one clear idea each and build on each other.

Return JSON only, in exactly this shape:
{shape}"""

REVISE_PROMPT = """You are revising an Instagram carousel for a student club ({name}).
Here is the current post as JSON:
{plan}

The club officer asked for these changes:
"{feedback}"

Apply the changes. Keep everything else the same unless the request implies otherwise.
Keep the same rules: accurate, no invented facts, short slide text.
Set "regenerate_image" to true ONLY if the request is about the picture/artwork/background/image.

Return JSON only, in this shape (all fields required):
{shape}"""

IMAGE_STYLE = (
    "Vertical background artwork for a premium Instagram post. Cinematic, modern digital art, "
    "dark navy and deep violet palette with glowing cyan light accents, soft volumetric light, "
    "subtle depth of field, elegant and minimal, lots of calm empty space in the lower half. "
    "Absolutely NO text, letters, numbers, words, symbols, logos, UI, or watermarks anywhere. "
    "No real people's faces. Subject: "
)


def _ask_json(client, prompt):
    resp = client.chat.completions.create(
        model=config.TEXT_MODEL,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )
    plan = json.loads(resp.choices[0].message.content)
    plan["slides"] = plan.get("slides", [])[:3]
    if not plan.get("title") or len(plan["slides"]) < 3 or not plan.get("caption"):
        raise SystemExit("The text model returned an incomplete post. Try again.")
    return plan


def make_plan(client, topic):
    return _ask_json(client, NEW_PROMPT.format(
        name=config.CLUB_NAME, about=config.CLUB_DESCRIPTION, topic=topic, shape=PLAN_SHAPE))


def revise_plan(client, plan, feedback):
    shape = PLAN_SHAPE[:PLAN_SHAPE.rfind("}")].rstrip() + ',\n  "regenerate_image": false\n}'
    keep = {k: plan[k] for k in ("title", "subtitle", "slides", "caption", "hashtags", "image_prompt") if k in plan}
    return _ask_json(client, REVISE_PROMPT.format(
        name=config.CLUB_NAME, plan=json.dumps(keep, indent=2), feedback=feedback, shape=shape))


def make_background(client, image_prompt):
    resp = client.images.generate(
        model=config.IMAGE_MODEL, prompt=IMAGE_STYLE + image_prompt,
        size="1024x1536", quality=config.IMAGE_QUALITY, n=1)
    data = resp.data[0]
    if getattr(data, "b64_json", None):
        raw = base64.b64decode(data.b64_json)
    else:
        import requests
        raw = requests.get(data.url, timeout=60).content
    return Image.open(io.BytesIO(raw)).convert("RGB")


# ================================================================ drawing helpers
def F(kind, size):
    files = {"head": "SpaceGrotesk_700Bold.ttf", "label": "SpaceGrotesk_500Medium.ttf",
             "body": "Inter_400Regular.ttf", "bodybold": "Inter_600SemiBold.ttf"}
    path = FONTS / files[kind]
    if path.exists():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size=size)


def wrap(draw, text, fnt, max_w):
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=fnt) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def fit(draw, text, kind, max_w, max_h, start, smallest, leading):
    size = start
    while True:
        fnt = F(kind, size)
        lines = wrap(draw, text, fnt, max_w)
        lh = int(size * leading)
        if len(lines) * lh <= max_h or size <= smallest:
            return fnt, lines, lh
        size -= 3


def text_block(draw, lines, fnt, lh, x, y, fill):
    for i, line in enumerate(lines):
        draw.text((x, y + i * lh), line, font=fnt, fill=fill)
    return y + len(lines) * lh


def tracked(draw, xy, text, fnt, fill, spacing=3):
    """Text with extra letter spacing (for small uppercase labels)."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill)
        x += draw.textlength(ch, font=fnt) + spacing
    return x


def tracked_width(draw, text, fnt, spacing=3):
    return sum(draw.textlength(c, font=fnt) + spacing for c in text) - spacing


def h_gradient(size, c1, c2):
    w, h = size
    g = Image.new("RGB", (w, 1))
    for x in range(w):
        t = x / max(1, w - 1)
        g.putpixel((x, 0), tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)))
    return g.resize((w, h))


def gradient_text(img, xy, text, fnt):
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).text(xy, text, font=fnt, fill=255)
    box = mask.getbbox()
    if not box:
        return
    grad = Image.new("RGB", img.size)
    grad.paste(h_gradient((box[2] - box[0], box[3] - box[1]), A1, A2), box[:2])
    img.paste(grad, (0, 0), mask)


def accent_bar(img, x, y, w=140, h=8):
    bar = h_gradient((w, h), A1, A2)
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=255)
    img.paste(bar, (x, y), m)


def vertical_fade(alpha_top, alpha_bottom, start=0.0):
    g = Image.new("L", (1, H))
    for y in range(H):
        t = y / H
        t = 0 if t < start else (t - start) / (1 - start)
        t = t * t * (3 - 2 * t)  # smooth
        g.putpixel((0, y), int(alpha_top + (alpha_bottom - alpha_top) * t))
    layer = Image.new("RGBA", (W, H), config.BG_DARK + (0,))
    layer.putalpha(g.resize((W, H)))
    return layer


def glow(img, cx, cy, r, color, strength=110):
    layer = Image.new("RGBA", (W, H), color + (0,))
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).ellipse((cx - r, cy - r, cx + r, cy + r), fill=strength)
    layer.putalpha(m.filter(ImageFilter.GaussianBlur(r // 2)))
    img.alpha_composite(layer)


def top_bar(d):
    """Series pill on the left, 'made by an AI agent' badge on the right."""
    f = F("label", 26)
    label = config.SERIES_LABEL.upper()
    w = tracked_width(d, label, f) + 78
    d.rounded_rectangle((M, M, M + w, M + 58), radius=29, fill=(255, 255, 255, 28),
                        outline=(255, 255, 255, 70), width=2)
    d.ellipse((M + 24, M + 22, M + 38, M + 36), fill=A2)
    tracked(d, (M + 52, M + 13), label, f, WHITE)

    badge = "MADE BY AN AI AGENT"
    bw = tracked_width(d, badge, f) + 56
    x = W - M - bw
    d.rounded_rectangle((x, M, x + bw, M + 58), radius=29, fill=(10, 12, 30, 150),
                        outline=A1 + (220,), width=2)
    tracked(d, (x + 28, M + 13), badge, f, WHITE)


def bottom_bar(d, page, total):
    f = F("label", 27)
    label = config.INSTAGRAM_HANDLE or config.CLUB_NAME
    d.text((M, H - M - 18), label, font=f, fill=DIM)
    x = W - M  # progress dots, active one stretched
    for i in range(total, 0, -1):
        w = 44 if i == page else 12
        x -= w
        d.rounded_rectangle((x, H - M - 6, x + w, H - M + 6), radius=6,
                            fill=A2 if i == page else (255, 255, 255, 80))
        x -= 10


# ================================================================ slides
def cover(bg, plan, total):
    img = bg.convert("RGBA")
    img.alpha_composite(vertical_fade(70, 250, start=0.30))
    img = img.convert("RGB")
    d = ImageDraw.Draw(img, "RGBA")
    top_bar(d)
    max_w = W - 2 * M
    sub_f, sub_l, sub_h = fit(d, plan.get("subtitle", ""), "body", max_w, 150, 42, 32, 1.3)
    t_f, t_l, t_h = fit(d, plan["title"], "head", max_w, 480, 124, 70, 1.0)
    block = len(t_l) * t_h + 74 + len(sub_l) * sub_h + 90
    y = H - M - 70 - block
    y = text_block(d, t_l, t_f, t_h, M, y, WHITE)
    accent_bar(img, M, y + 34)
    y = text_block(d, sub_l, sub_f, sub_h, M, y + 74, SOFT)
    tracked(d, (M, y + 34), "SWIPE  →", F("label", 28), A2, spacing=4)
    bottom_bar(d, 1, total)
    return img


def lesson(soft, heading, body, page, total):
    img = soft.copy()
    glow(img, W - 120, 330, 330, A1, 90)
    glow(img, 140, H - 260, 300, A2, 55)
    img = img.convert("RGB")
    d = ImageDraw.Draw(img, "RGBA")
    top_bar(d)
    max_w = W - 2 * M
    gradient_text(img, (M - 8, 220), f"{page - 1:02d}", F("head", 230))
    h_f, h_l, h_h = fit(d, heading, "head", max_w, 300, 84, 54, 1.05)
    y = text_block(d, h_l, h_f, h_h, M, 520, WHITE)
    accent_bar(img, M, y + 26)
    b_f, b_l, b_h = fit(d, body, "body", max_w, H - y - 300, 50, 34, 1.42)
    text_block(d, b_l, b_f, b_h, M, y + 76, SOFT)
    bottom_bar(d, page, total)
    return img


def agent_story(soft, page, total):
    img = soft.copy()
    glow(img, W // 2, 420, 420, A1, 80)
    img = img.convert("RGB")
    d = ImageDraw.Draw(img, "RGBA")
    top_bar(d)
    max_w = W - 2 * M
    tracked(d, (M, 200), "HOW WAS THIS MADE?", F("label", 30), A2, spacing=4)
    h_f, h_l, h_h = fit(d, "This post was made by an AI agent.", "head", max_w, 200, 80, 56, 1.03)
    y = text_block(d, h_l, h_f, h_h, M, 252, WHITE)

    steps = ["Picked today's topic", "Wrote every slide", "Generated the artwork",
             "Designed the slides", "Published to Instagram"]
    y += 44
    step_f, num_f = F("bodybold", 36), F("label", 26)
    for i, s in enumerate(steps):
        cy = y + i * 72
        if i < len(steps) - 1:
            d.line((M + 23, cy + 46, M + 23, cy + 72), fill=(255, 255, 255, 70), width=3)
        d.ellipse((M, cy, M + 46, cy + 46), fill=A1 if i < len(steps) - 1 else A2)
        n = str(i + 1)
        d.text((M + 23 - d.textlength(n, font=num_f) / 2, cy + 7), n, font=num_f, fill=WHITE)
        d.text((M + 70, cy + 2), s, font=step_f, fill=WHITE)
    y = y + len(steps) * 72 + 6
    s_f, s_l, s_h = fit(d, config.AGENT_STORY.split(". ")[-1], "body", max_w, 90, 32, 26, 1.35)
    y = text_block(d, s_l, s_f, s_h, M, y, DIM)

    # call-to-action card with a gradient border
    top, bottom = max(y + 36, H - M - 290), H - M - 50
    border = h_gradient((W - 2 * M, bottom - top), A1, A2)
    m = Image.new("L", border.size, 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, border.size[0] - 1, border.size[1] - 1), radius=34, fill=255)
    img.paste(border, (M, top), m)
    d.rounded_rectangle((M + 3, top + 3, W - M - 3, bottom - 3), radius=32, fill=(12, 14, 34, 255))
    d.text((M + 44, top + 34), "That's agentic AI.", font=F("head", 50), fill=WHITE)
    j_f, j_l, j_h = fit(d, config.JOIN_INFO, "body", W - 2 * M - 88, bottom - top - 130, 36, 26, 1.38)
    text_block(d, j_l, j_f, j_h, M + 44, top + 104, SOFT)
    bottom_bar(d, page, total)
    return img


def render(plan, bg):
    bg = ImageOps.fit(bg, (W, H), method=Image.LANCZOS)
    soft = bg.filter(ImageFilter.GaussianBlur(36)).convert("RGBA")
    soft.alpha_composite(Image.new("RGBA", (W, H), config.BG_DARK + (200,)))
    total = 2 + len(plan["slides"])
    out = [cover(bg, plan, total)]
    for i, s in enumerate(plan["slides"]):
        out.append(lesson(soft, s["heading"], s["body"], i + 2, total))
    out.append(agent_story(soft, total, total))
    return out


# ================================================================ demo content
def demo_background():
    img = Image.new("RGB", (W, H))
    img = img.convert("RGB")
    d = ImageDraw.Draw(img, "RGBA")
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=(int(18 + 30 * t), int(14 + 6 * t), int(70 - 40 * t)))
    pts = [((i * 211) % W, 120 + (i * 97) % 700) for i in range(22)]
    for a, b in zip(pts, pts[1:]):
        d.line((a, b), fill=(120, 92, 255), width=2)
    for x, y in pts:
        d.ellipse((x - 5, y - 5, x + 5, y + 5), fill=(34, 211, 238))
    return img.filter(ImageFilter.GaussianBlur(1.5))


DEMO_PLAN = {
    "title": "What is agentic AI?",
    "subtitle": "AI that doesn't just answer questions. It gets things done.",
    "slides": [
        {"heading": "Chatbots answer. Agents act.",
         "body": "A chatbot replies to one message. An AI agent is given a goal, then plans the steps and carries them out on its own."},
        {"heading": "Plan, act, check, repeat",
         "body": "Agents work in a loop: decide the next step, use a tool like a website or an app, look at the result, and adjust the plan."},
        {"heading": "Tools are the superpower",
         "body": "Give an agent access to search, code, or an image generator and it can finish real tasks, like making this whole post."},
    ],
    "caption": "This post was planned, written, designed and published by an AI agent 🤖 Want to see how it works? Come to our next meeting!",
    "hashtags": ["#AgenticAI", "#AI", "#AIAgents", "#AIClub", "#LearnAI", "#STEM"],
    "image_prompt": "demo",
}


# ================================================================ saving
def save(draft_dir, plan, bg, meta):
    draft_dir.mkdir(parents=True, exist_ok=True)
    ImageOps.fit(bg, (W, H), method=Image.LANCZOS).save(draft_dir / "background.jpg", "JPEG", quality=90)
    names = []
    for i, slide in enumerate(render(plan, bg), start=1):
        name = f"slide{i}.jpg"
        slide.save(draft_dir / name, "JPEG", quality=93, optimize=True)
        names.append(name)
    caption = plan["caption"].strip() + "\n\n" + " ".join(plan.get("hashtags", [])[:10])
    meta.update({"title": plan["title"], "caption": caption, "slides": names, "plan": plan,
                 "updated": now_iso()})
    (draft_dir / "draft.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (DRAFTS / "LATEST").write_text(meta["id"], encoding="utf-8")
    return meta


def new_draft(demo=False):
    topic = pick_topic()
    print(f"Topic: {topic}")
    if demo:
        plan, bg = DEMO_PLAN, demo_background()
    else:
        from openai import OpenAI
        client = OpenAI()
        plan = make_plan(client, topic)
        print(f"Title: {plan['title']}")
        bg = make_background(client, plan["image_prompt"])
    draft_id = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d-%H%M")
    meta = {"id": draft_id, "topic": topic, "status": "waiting", "version": 1,
            "created": now_iso(), "changes": []}
    save(DRAFTS / draft_id, plan, bg, meta)
    print(f"Draft saved: {draft_id}")


def revise(draft_id, feedback):
    from openai import OpenAI
    client = OpenAI()
    folder = DRAFTS / draft_id
    meta = json.loads((folder / "draft.json").read_text(encoding="utf-8"))
    plan = revise_plan(client, meta["plan"], feedback)
    if plan.pop("regenerate_image", False):
        print("Making new artwork")
        bg = make_background(client, plan.get("image_prompt") or meta["plan"]["image_prompt"])
    else:
        bg = Image.open(folder / "background.jpg").convert("RGB")
    meta["version"] = meta.get("version", 1) + 1
    meta.setdefault("changes", []).append({"version": meta["version"], "request": feedback, "at": now_iso()})
    save(folder, plan, bg, meta)
    print(f"Revised {draft_id} to version {meta['version']}")


if __name__ == "__main__":
    if "--revise" in sys.argv:
        revise(sys.argv[sys.argv.index("--revise") + 1], os.environ["FEEDBACK"])
    else:
        new_draft(demo="--demo" in sys.argv)
