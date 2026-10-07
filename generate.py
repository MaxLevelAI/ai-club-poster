"""The AI agent's "make a post" brain.

  python generate.py                      make a brand-new draft (needs OPENAI_API_KEY)
  python generate.py --revise <draft_id>  redo a draft using the FEEDBACK env variable
  python generate.py --demo [format]      no API calls, just tests the slide design

LOCKED RULES (approved by the club, the same in every post):
  - 1080x1350 JPEG slides, max 10, Matrix green-on-black theme, about AI agents
  - "MADE BY AN AI AGENT" badge top-right on every slide
  - meeting ticker at the bottom of every slide (while a meeting is upcoming)
  - guest/meeting slide: "AI at Disney", the guest line, date, time, place, full address
  - reveal slide (second to last): "This post was made by an AI agent.", the steps,
    the approval line, and "Want to learn how? Sign up with the link in our bio."
  - QR finale (always last): "SCAN TO JOIN", a 640px centered QR code,
    "Or screenshot this and press & hold the QR code", "Link in our bio", short address
  - caption: hook line, made-by-an-agent line, meeting block, register line, max 5 hashtags
Everything else (format, slide types, layouts, art) changes from post to post.
"""
import base64
import datetime
import io
import json
import os
import pathlib
import random
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

import config

W, H = 1080, 1350  # Instagram portrait (4:5), the tallest ratio the API accepts
M = 88             # side margin (also clears the profile-grid crop)
MAX_SLIDES = 10    # Instagram API carousel limit
ROOT = pathlib.Path(__file__).parent
DRAFTS = ROOT / "drafts"
FONTS = ROOT / "fonts"
ASSETS = ROOT / "assets"


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


A1, A2 = hex_rgb(config.ACCENT), hex_rgb(config.ACCENT_2)
WHITE, SOFT, DIM = (240, 255, 244), (190, 240, 205), (105, 160, 122)
PANEL = (0, 14, 6)


def meeting_upcoming():
    if not getattr(config, "MEETING_DATE", ""):
        return False
    meeting = datetime.date.fromisoformat(config.MEETING_DATE)
    today = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=5)).date()
    return today <= meeting


def meeting_block():
    if not meeting_upcoming():
        return "🔗 Learn more and sign up: link in our bio, or scan the QR code on the last slide"
    lines = [f"📅 {config.MEETING_DAY} · {config.MEETING_TIME}",
             f"📍 {config.MEETING_PLACE}, The Grove · {config.MEETING_ADDRESS}"]
    if config.GUEST_LINE:
        lines.append(f"🎤 Special guest: {config.GUEST_LINE[0].lower() + config.GUEST_LINE[1:]}")
    lines.append("🔗 Register: link in our bio, or scan the QR code on the last slide")
    return "\n".join(lines)


def build_caption(plan):
    tags = [t if t.startswith("#") else "#" + t for t in plan.get("hashtags", []) if t.strip()]
    tags = list(dict.fromkeys(tags))[:5]  # Instagram allows 5 hashtags max
    hook = plan.get("caption_hook", "").strip()
    body = plan.get("caption_body", "").strip()
    if "agent" not in body.lower():
        body = (body + " This whole post was made by an AI agent 🤖").strip()
    return f"{hook}\n\n{body}\n\n{meeting_block()}\n\n{' '.join(tags)}".strip()


# ================================================================ topics & formats
def draft_count():
    return len([p for p in DRAFTS.glob("*") if p.is_dir()]) if DRAFTS.exists() else 0


def pick_topic():
    if os.getenv("TOPIC", "").strip():
        return os.getenv("TOPIC").strip()
    lines = (ROOT / "topics.txt").read_text(encoding="utf-8").splitlines()
    topics = [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]
    return topics[draft_count() % len(topics)]


FORMATS = [
    ("explainer", "3-4 'statement' slides that each teach one idea, building on each other. Mix in one 'big_word' slide."),
    ("terminal log", "Tell it like the agent's own log: 2-3 'terminal' slides showing goal -> plan -> actions -> result, plus 1 'statement' slide that explains what it means."),
    ("myth vs fact", "3 'myth_fact' slides busting common misconceptions, then 1 'statement' takeaway."),
    ("versus", "1 'versus' comparison slide, then 2 'statement' or 'steps' slides that go deeper."),
    ("quiz", "A 'quiz' slide with a question and 3 options, then a 'statement' slide revealing and explaining the answer, then 1-2 more slides of any type."),
    ("framework", "1 'steps' slide with a simple 3-4 step framework, 1 'big_word' slide, 1-2 'statement' slides."),
    ("big ideas", "3 'big_word' slides, each one punchy phrase with a one-line explanation, then 1 'statement'."),
]
COVER_STYLES = ["art", "terminal", "center"]

SLIDE_TYPES = """Slide types you can use (fields in brackets):
- statement {heading: max 7 words, body: max 22 words}
- big_word {word: 1-4 words, caption: max 14 words}
- terminal {title: short file-like name, lines: 3-6 lines, each max 32 chars; start command lines with "> "}
- versus {heading: max 6 words, left_title, left_points: 3 items max 5 words each, right_title, right_points: 3 items}
- myth_fact {myth: max 14 words, fact: max 20 words}
- steps {heading: max 6 words, steps: 3-4 items, max 7 words each}
- quiz {question: max 14 words, options: 3 short options}"""

PLAN_SHAPE = """{
  "cover": {"title": "max 7 words, a bold hook or question", "kicker": "max 4 words"},
  "slides": [ {"type": "statement", "heading": "...", "body": "..."}, ... 2 to 5 slides ... ],
  "caption_hook": "first caption line, max 110 characters, makes people want to swipe",
  "caption_body": "1-2 sentences, mention that an AI agent made this post. No dates, places, links or hashtags.",
  "hashtags": ["exactly 5 relevant hashtags, e.g. #AgenticAI"],
  "image_prompt": "a vivid description of cover artwork that fits the topic"
}"""

NEW_PROMPT = """You design Instagram carousel posts for a student club.
Club name: {name}
About the club: {about}

Topic: "{topic}"
Format for this post ("{fmt_name}"): {fmt_rule}

{types}

Rules:
- Audience: students, many are beginners. Clear, exciting, a little playful, never cringe.
- Be factually accurate. Never invent statistics, dates, events, names, quotes, or company facts.
- One idea per slide. Max 25 words on any slide. No hashtags or emojis on slides.
- The FIRST slide in "slides" must work on its own as a second hook (Instagram re-shows carousels
  starting at slide 2), e.g. a surprising statement or a question.
- Do NOT write slides about the meeting, the guest, sign-ups, or "made by an AI agent";
  those slides are added automatically.

Return JSON only, in exactly this shape:
{shape}"""

REVISE_PROMPT = """You are revising an Instagram carousel for a student club ({name}).
Current post (JSON):
{plan}

{types}

The club officer asked for these changes:
"{feedback}"

Apply the changes. Keep everything else the same unless the request implies otherwise.
Same rules: accurate, no invented facts, max 25 words per slide, 2-5 slides, the first slide is a second hook.
The meeting, guest, "made by an AI agent" and QR slides are fixed and added automatically, so do not add them.
If the request is about those fixed slides, keep the content as is.
Set "regenerate_image" to true ONLY if the request is about the cover picture/artwork/image.
Set "cover_style" to one of: art, terminal, center (keep the current one unless asked).

Return JSON only, in this shape (all fields required):
{shape}"""

IMAGE_STYLE = (
    "Vertical cover artwork for a premium Instagram post in a 'hacker / Matrix' aesthetic. "
    "Pitch black background, glowing neon green (#00FF41) light, cascading streams of abstract green "
    "light like digital rain, circuit traces, holographic wireframes, subtle CRT scanline glow, "
    "cinematic depth, a clear focal subject in the upper half and calm dark space in the lower half. "
    "Absolutely NO readable text, letters, numbers, words, logos, or watermarks anywhere. "
    "No real people's faces. Subject: "
)


def _clean_plan(plan):
    """Make the model's output safe to render: known types only, 2-5 slides, short text."""
    def cut(s, n):
        s = str(s or "").strip()
        words = s.split()
        return " ".join(words[:n]) if len(words) > n else s

    out = []
    for s in plan.get("slides", []):
        t = s.get("type", "statement")
        if t == "big_word" and s.get("word"):
            out.append({"type": t, "word": cut(s["word"], 4), "caption": cut(s.get("caption"), 16)})
        elif t == "terminal" and s.get("lines"):
            out.append({"type": t, "title": cut(s.get("title", "agent.log"), 3),
                        "lines": [str(l)[:40] for l in s["lines"][:6]]})
        elif t == "versus" and s.get("left_points") and s.get("right_points"):
            out.append({"type": t, "heading": cut(s.get("heading"), 7),
                        "left_title": cut(s.get("left_title"), 3), "right_title": cut(s.get("right_title"), 3),
                        "left_points": [cut(p, 6) for p in s["left_points"][:3]],
                        "right_points": [cut(p, 6) for p in s["right_points"][:3]]})
        elif t == "myth_fact" and s.get("myth") and s.get("fact"):
            out.append({"type": t, "myth": cut(s["myth"], 16), "fact": cut(s["fact"], 22)})
        elif t == "steps" and s.get("steps"):
            out.append({"type": t, "heading": cut(s.get("heading"), 7),
                        "steps": [cut(x, 8) for x in s["steps"][:4]]})
        elif t == "quiz" and s.get("question") and s.get("options"):
            out.append({"type": t, "question": cut(s["question"], 16),
                        "options": [cut(o, 6) for o in s["options"][:3]]})
        elif s.get("heading") or s.get("body"):
            out.append({"type": "statement", "heading": cut(s.get("heading"), 8), "body": cut(s.get("body"), 24)})
    plan["slides"] = out[:5]
    cover = plan.get("cover") or {}
    plan["cover"] = {"title": cut(cover.get("title") or plan.get("title"), 8), "kicker": cut(cover.get("kicker"), 4)}
    if not plan["cover"]["title"] or len(plan["slides"]) < 2:
        raise SystemExit("The text model returned an incomplete post. Try again.")
    plan["title"] = plan["cover"]["title"]
    return plan


def _ask_json(client, prompt):
    resp = client.chat.completions.create(
        model=config.TEXT_MODEL,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )
    return json.loads(resp.choices[0].message.content)


def make_plan(client, topic, fmt):
    plan = _ask_json(client, NEW_PROMPT.format(
        name=config.CLUB_NAME, about=config.CLUB_DESCRIPTION, topic=topic,
        fmt_name=fmt[0], fmt_rule=fmt[1], types=SLIDE_TYPES, shape=PLAN_SHAPE))
    return _clean_plan(plan)


def revise_plan(client, plan, feedback):
    shape = PLAN_SHAPE[:PLAN_SHAPE.rfind("}")].rstrip() + \
        ',\n  "cover_style": "art",\n  "regenerate_image": false\n}'
    keep = {k: plan[k] for k in ("cover", "slides", "caption_hook", "caption_body", "hashtags",
                                 "image_prompt", "cover_style") if k in plan}
    new = _ask_json(client, REVISE_PROMPT.format(
        name=config.CLUB_NAME, plan=json.dumps(keep, indent=2), types=SLIDE_TYPES,
        feedback=feedback, shape=shape))
    regen = bool(new.pop("regenerate_image", False))
    new = _clean_plan(new)
    if new.get("cover_style") not in COVER_STYLES:
        new["cover_style"] = plan.get("cover_style", "art")
    new["format"] = plan.get("format", "")
    return new, regen


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


def guest_background(client):
    """The guest-slide artwork is made once and reused."""
    path = ASSETS / "guest.jpg"
    if path.exists():
        return Image.open(path).convert("RGB")
    if client is None:
        return None
    img = make_background(client, config.GUEST_IMAGE_PROMPT)
    ASSETS.mkdir(exist_ok=True)
    ImageOps.fit(img, (W, H), method=Image.LANCZOS).save(path, "JPEG", quality=90)
    return img


# ================================================================ drawing helpers
def F(kind, size):
    files = {"head": "SpaceGrotesk_700Bold.ttf", "label": "JetBrainsMono_500Medium.ttf",
             "mono": "JetBrainsMono_800ExtraBold.ttf", "body": "Inter_400Regular.ttf",
             "bodybold": "Inter_600SemiBold.ttf"}
    path = FONTS / files[kind]
    if path.exists():
        return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size=size)


def wrap(draw, text, fnt, max_w):
    lines, cur = [], ""
    for word in str(text).split():
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
        widest = max((draw.textlength(l, font=fnt) for l in lines), default=0)
        if (len(lines) * lh <= max_h and widest <= max_w) or size <= smallest:
            return fnt, lines, lh
        size -= 2


def text_block(draw, lines, fnt, lh, x, y, fill, center=False):
    for i, line in enumerate(lines):
        lx = (W - draw.textlength(line, font=fnt)) / 2 if center else x
        draw.text((lx, y + i * lh), line, font=fnt, fill=fill)
    return y + len(lines) * lh


def tracked(draw, xy, text, fnt, fill, spacing=3):
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


def gradient_text(img, xy, text, fnt, glow_amount=0.55):
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).text(xy, text, font=fnt, fill=255)
    box = mask.getbbox()
    if not box:
        return
    if glow_amount:
        img.paste(Image.new("RGB", img.size, A1), (0, 0),
                  mask.filter(ImageFilter.GaussianBlur(18)).point(lambda v: v * glow_amount))
    grad = Image.new("RGB", img.size)
    grad.paste(h_gradient((box[2] - box[0], box[3] - box[1]), A1, A2), box[:2])
    img.paste(grad, (0, 0), mask)


def gradient_lines(img, draw, lines, fnt, lh, x, y, center=False):
    for i, line in enumerate(lines):
        lx = (W - draw.textlength(line, font=fnt)) / 2 if center else x
        gradient_text(img, (lx, y + i * lh), line, fnt)
    return y + len(lines) * lh


def accent_bar(img, x, y, w=140, h=8):
    bar = h_gradient((w, h), A1, A2)
    m = Image.new("L", (w, h), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=255)
    img.paste(bar, (int(x), int(y)), m)


def vertical_fade(alpha_top, alpha_bottom, start=0.0):
    g = Image.new("L", (1, H))
    for y in range(H):
        t = y / H
        t = 0 if t < start else (t - start) / (1 - start)
        t = t * t * (3 - 2 * t)
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


RAIN_CHARS = "0123456789ABCDEF<>{}[]#$%&*+=/|:;"


def code_rain(seed, strength=1.0):
    rnd = random.Random(str(seed))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    f = F("label", 24)
    col_w, row_h = 34, 30
    for c in range(W // col_w + 1):
        if rnd.random() < 0.45:
            continue
        x = c * col_w + 6
        length = rnd.randint(6, 26)
        head = rnd.randint(0, H // row_h + length)
        for k in range(length):
            row = head - k
            if row < 0 or row * row_h > H:
                continue
            fade = 1 - k / length
            alpha = int((40 + 150 * fade) * strength) if k else int(230 * strength)
            color = (210, 255, 220) if k == 0 else A1
            d.text((x, row * row_h), rnd.choice(RAIN_CHARS), font=f, fill=color + (alpha,))
    return layer


def scanlines(img, alpha=26):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for y in range(0, H, 4):
        d.line((0, y, W, y), fill=(0, 0, 0, alpha))
    img.alpha_composite(layer)


def panel(d, box, radius=18, outline_alpha=200, fill=PANEL + (235,)):
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=A1 + (outline_alpha,), width=2)


# ---- locked chrome: badge on top, ticker on the bottom of EVERY slide
def top_bar(d, label=None):
    f = F("label", 24)
    label = "> " + (label or config.SERIES_LABEL).upper()
    w = tracked_width(d, label, f) + 70
    d.rounded_rectangle((M, M, M + w, M + 56), radius=8, fill=(0, 20, 8, 200),
                        outline=A1 + (160,), width=2)
    d.rectangle((M + 22, M + 21, M + 34, M + 35), fill=A1)
    tracked(d, (M + 46, M + 13), label, f, A1)
    badge = "MADE BY AN AI AGENT"
    f2 = F("label", 26)
    bw = tracked_width(d, badge, f2) + 52
    x = W - M - bw
    d.rounded_rectangle((x, M, x + bw, M + 56), radius=8, fill=(0, 0, 0, 200),
                        outline=A1 + (230,), width=2)
    tracked(d, (x + 26, M + 12), badge, f2, WHITE)


def bottom_bar(d, page, total):
    f = F("label", 22)
    if meeting_upcoming():
        label = f"NEXT MEETING: {config.MEETING_TICKER}"
        color = A2
    else:
        label = config.INSTAGRAM_HANDLE or config.CLUB_NAME
        color = DIM
    y = H - M - 4
    d.text((M, y - 12), label, font=f, fill=color)
    x = W - M
    for i in range(total, 0, -1):
        w = 36 if i == page else 9
        x -= w
        d.rectangle((x, y, x + w, y + 9), fill=A1 if i == page else (255, 255, 255, 70))
        x -= 7
    if page < total:
        d.text((x - 34, y - 14), "→", font=F("label", 26), fill=A1)


def base(soft, seed, glow_xy=(W - 120, 330), glow_strength=50, rain=0.4):
    img = soft.copy()
    img.alpha_composite(code_rain(seed, rain))
    scanlines(img)
    if glow_xy:
        glow(img, glow_xy[0], glow_xy[1], 330, A1, glow_strength)
    img = img.convert("RGB")
    return img, ImageDraw.Draw(img, "RGBA")


# ================================================================ covers
def cover(bg, plan, total, style):
    title = plan["cover"]["title"]
    kicker = plan["cover"].get("kicker") or config.SERIES_LABEL
    img = bg.convert("RGBA")
    max_w = W - 2 * M
    if style == "center":
        img.alpha_composite(Image.new("RGBA", (W, H), config.BG_DARK + (150,)))
        halo = Image.new("L", (W, H), 0)
        ImageDraw.Draw(halo).rounded_rectangle((40, H // 2 - 330, W - 40, H // 2 + 290), radius=200, fill=200)
        dark = Image.new("RGBA", (W, H), config.BG_DARK + (0,))
        dark.putalpha(halo.filter(ImageFilter.GaussianBlur(90)))
        img.alpha_composite(dark)
        img.alpha_composite(code_rain(title, 0.25))
        scanlines(img)
        img = img.convert("RGB")
        d = ImageDraw.Draw(img, "RGBA")
        top_bar(d)
        t_f, t_l, t_h = fit(d, title, "head", max_w, 520, 140, 76, 1.0)
        y = (H - len(t_l) * t_h) // 2 - 20
        tracked(d, ((W - tracked_width(d, "> " + kicker.upper(), F("label", 30), 4)) / 2, y - 70),
                "> " + kicker.upper(), F("label", 30), A1, 4)
        y = gradient_lines(img, d, t_l, t_f, t_h, M, y, center=True)
        tracked(d, ((W - tracked_width(d, "SWIPE  →", F("label", 30), 4)) / 2, y + 50),
                "SWIPE  →", F("label", 30), A1, 4)
    elif style == "terminal":
        img.alpha_composite(vertical_fade(40, 200, start=0.2))
        img.alpha_composite(code_rain(title, 0.3))
        scanlines(img)
        img = img.convert("RGB")
        d = ImageDraw.Draw(img, "RGBA")
        top_bar(d)
        t_f, t_l, t_h = fit(d, title, "mono", max_w - 80, 420, 92, 56, 1.12)
        box_h = 120 + 70 + len(t_l) * t_h + 90
        top = H - M - 80 - box_h
        panel(d, (M, top, W - M, top + box_h), fill=(0, 6, 2, 225))
        d.rectangle((M + 2, top + 2, W - M - 2, top + 56), fill=(0, 40, 14, 255))
        for i in range(3):
            d.ellipse((M + 22 + i * 30, top + 18, M + 40 + i * 30, top + 36), fill=A1 if i == 2 else (60, 90, 70))
        d.text((M + 130, top + 14), "agent@ai-club: ~", font=F("label", 24), fill=SOFT)
        d.text((M + 40, top + 80), f"> run agent --topic \"{kicker.lower()}\"", font=F("label", 28), fill=DIM)
        y = gradient_lines(img, d, t_l, t_f, t_h, M + 40, top + 140)
        d.rectangle((M + 40, y + 20, M + 70, y + 60), fill=A1)  # blinking cursor
        d.text((M + 90, y + 18), "swipe →", font=F("label", 30), fill=A1)
    else:  # "art"
        img.alpha_composite(vertical_fade(60, 250, start=0.30))
        img.alpha_composite(code_rain(title, 0.35))
        scanlines(img)
        img = img.convert("RGB")
        d = ImageDraw.Draw(img, "RGBA")
        top_bar(d)
        t_f, t_l, t_h = fit(d, title, "head", max_w, 480, 128, 72, 1.0)
        y = H - M - 120 - len(t_l) * t_h - 70
        tracked(d, (M, y), "> " + kicker.upper(), F("label", 30), A1, 4)
        y += 60
        for i, line in enumerate(t_l):
            if i == len(t_l) - 1:
                gradient_text(img, (M, y + i * t_h), line, t_f)
            else:
                d.text((M, y + i * t_h), line, font=t_f, fill=WHITE)
        y += len(t_l) * t_h
        tracked(d, (M, y + 30), "SWIPE  →", F("label", 30), A1, 4)
    bottom_bar(d, 1, total)
    return img


# ================================================================ content slide types
def s_statement(soft, s, page, total, idx):
    img, d = base(soft, s["heading"])
    max_w = W - 2 * M
    if s.get("_num"):
        gradient_text(img, (M - 6, 210), f"{s['_num']:02d}", F("mono", 200))
    else:
        tracked(d, (M, 420), "> KEY IDEA", F("label", 32), A1, 4)
    h_f, h_l, h_h = fit(d, s["heading"], "head", max_w, 300, 86, 56, 1.05)
    y = text_block(d, h_l, h_f, h_h, M, 500, WHITE)
    accent_bar(img, M, y + 26)
    b_f, b_l, b_h = fit(d, s["body"], "body", max_w, H - y - 300, 52, 36, 1.42)
    text_block(d, b_l, b_f, b_h, M, y + 76, SOFT)
    return img, d


def s_big_word(soft, s, page, total, idx):
    img, d = base(soft, s["word"], glow_xy=(W // 2, H // 2 - 60), glow_strength=70)
    max_w = W - 2 * M
    w_f, w_l, w_h = fit(d, s["word"].upper(), "mono", max_w, 560, 220, 96, 1.02)
    block = len(w_l) * w_h
    y = (H - block) // 2 - 80
    y = gradient_lines(img, d, w_l, w_f, w_h, M, y, center=True)
    c_f, c_l, c_h = fit(d, s["caption"], "body", max_w - 60, 220, 48, 36, 1.38)
    accent_bar(img, (W - 140) / 2, y + 30)
    text_block(d, c_l, c_f, c_h, M, y + 80, SOFT, center=True)
    return img, d


def s_terminal(soft, s, page, total, idx):
    img, d = base(soft, s.get("title", ""), rain=0.3)
    lines = s["lines"]
    f = F("label", 38)
    while f.size > 30 and max(d.textlength(l, font=f) for l in lines) > W - 2 * M - 80:
        f = F("label", f.size - 2)
    lh = int(f.size * 1.7)
    box_h = 56 + 50 + len(lines) * lh + 40
    top = max(200, (H - box_h) // 2 - 30)
    panel(d, (M, top, W - M, top + box_h), fill=(0, 6, 2, 240))
    d.rectangle((M + 2, top + 2, W - M - 2, top + 56), fill=(0, 40, 14, 255))
    for i in range(3):
        d.ellipse((M + 22 + i * 30, top + 18, M + 40 + i * 30, top + 36), fill=A1 if i == 2 else (60, 90, 70))
    d.text((M + 130, top + 14), s.get("title") or "agent.log", font=F("label", 24), fill=SOFT)
    y = top + 90
    for line in lines:
        cmd = line.strip().startswith(">")
        d.text((M + 40, y), line, font=f, fill=A1 if cmd else WHITE)
        y += lh
    d.rectangle((M + 40, y + 4, M + 62, y + 40), fill=A1)
    return img, d


def s_versus(soft, s, page, total, idx):
    img, d = base(soft, s["heading"])
    max_w = W - 2 * M
    h_f, h_l, h_h = fit(d, s["heading"], "head", max_w, 220, 80, 54, 1.05)
    y = text_block(d, h_l, h_f, h_h, M, 210, WHITE) + 50
    col_w = (W - 2 * M - 30) // 2
    cols = [(s["left_title"], s["left_points"]), (s["right_title"], s["right_points"])]
    # measure first so both panels fit their content
    layout, tallest = [], 0
    for title, pts in cols:
        t_f, t_l, t_h = fit(d, title.upper(), "mono", col_w - 60, 120, 44, 30, 1.1)
        pl = [fit(d, p, "bodybold", col_w - 90, 160, 40, 36, 1.3) for p in pts]
        hgt = 60 + len(t_l) * t_h + sum(len(l) * h + 34 for _, l, h in pl) + 20
        layout.append((t_f, t_l, t_h, pl))
        tallest = max(tallest, hgt)
    y = max(y, (H - tallest) // 2 + 40)
    for c, (t_f, t_l, t_h, pl) in enumerate(layout):
        x = M + c * (col_w + 30)
        panel(d, (x, y, x + col_w, y + tallest), outline_alpha=230 if c else 90,
              fill=(0, 22, 9, 235) if c else (0, 8, 4, 235))
        if c:
            gradient_lines(img, d, t_l, t_f, t_h, x + 30, y + 34)
        else:
            text_block(d, t_l, t_f, t_h, x + 30, y + 34, DIM)
        py = y + 60 + len(t_l) * t_h
        for p_f, p_l, p_h in pl:
            d.rectangle((x + 32, py + 17, x + 44, py + 29), fill=A1 if c else DIM)
            py = text_block(d, p_l, p_f, p_h, x + 64, py, WHITE if c else SOFT) + 34
    return img, d


def s_myth_fact(soft, s, page, total, idx):
    img, d = base(soft, s["myth"])
    max_w = W - 2 * M - 80
    m_f, m_l, m_h = fit(d, s["myth"], "bodybold", max_w, 230, 46, 36, 1.3)
    f_f, f_l, f_h = fit(d, s["fact"], "bodybold", max_w, 300, 50, 36, 1.3)
    mh = 120 + len(m_l) * m_h
    fh_pre = 120 + len(f_l) * f_h
    top = max(210, (H - (mh + 40 + fh_pre)) // 2)
    panel(d, (M, top, W - M, top + mh), outline_alpha=70, fill=(0, 6, 3, 235))
    tracked(d, (M + 40, top + 34), "MYTH", F("mono", 40), DIM, 6)
    for i, line in enumerate(m_l):
        ly = top + 96 + i * m_h
        d.text((M + 40, ly), line, font=m_f, fill=DIM)
        mid = ly + m_f.size * 0.62
        d.line((M + 36, mid, M + 44 + d.textlength(line, font=m_f), mid), fill=(255, 90, 90, 170), width=4)
    top2 = top + mh + 40
    fh = 120 + len(f_l) * f_h
    panel(d, (M, top2, W - M, top2 + fh), fill=(0, 26, 10, 240))
    gradient_text(img, (M + 40, top2 + 30), "FACT", F("mono", 44))
    text_block(d, f_l, f_f, f_h, M + 40, top2 + 96, WHITE)
    return img, d


def s_steps(soft, s, page, total, idx):
    img, d = base(soft, s["heading"])
    max_w = W - 2 * M
    h_f, h_l, h_h = fit(d, s["heading"], "head", max_w, 220, 80, 54, 1.05)
    y = text_block(d, h_l, h_f, h_h, M, 220, WHITE)
    accent_bar(img, M, y + 24)
    y += 80
    n = len(s["steps"])
    row_h = min(190, (H - M - 90 - y) // max(1, n))
    for i, step in enumerate(s["steps"]):
        ry = y + i * row_h
        d.rectangle((M, ry, M + 84, ry + 84), fill=(0, 22, 9), outline=A1, width=3)
        num = str(i + 1)
        nf = F("mono", 50)
        d.text((M + 42 - d.textlength(num, font=nf) / 2, ry + 10), num, font=nf, fill=A1)
        if i < n - 1:
            d.line((M + 42, ry + 84, M + 42, ry + row_h), fill=A1 + (110,), width=3)
        s_f, s_l, s_h = fit(d, step, "bodybold", max_w - 130, row_h - 30, 44, 36, 1.28)
        text_block(d, s_l, s_f, s_h, M + 120, ry + 12, WHITE)
    return img, d


def s_quiz(soft, s, page, total, idx):
    img, d = base(soft, s["question"])
    max_w = W - 2 * M
    tracked(d, (M, 210), "> QUICK QUIZ", F("label", 32), A1, 4)
    q_f, q_l, q_h = fit(d, s["question"], "head", max_w, 330, 78, 52, 1.08)
    y = text_block(d, q_l, q_f, q_h, M, 266, WHITE) + 50
    for i, opt in enumerate(s["options"]):
        oy = y + i * 150
        panel(d, (M, oy, W - M, oy + 124), outline_alpha=150)
        d.text((M + 34, oy + 30), "ABC"[i], font=F("mono", 52), fill=A1)
        o_f, o_l, o_h = fit(d, opt, "bodybold", max_w - 160, 90, 42, 36, 1.2)
        text_block(d, o_l, o_f, o_h, M + 120, oy + 62 - len(o_l) * o_h / 2, WHITE)
    d.text((M, y + 3 * 150 + 10), "Swipe for the answer →", font=F("label", 30), fill=A2)
    return img, d


RENDERERS = {"statement": s_statement, "big_word": s_big_word, "terminal": s_terminal,
             "versus": s_versus, "myth_fact": s_myth_fact, "steps": s_steps, "quiz": s_quiz}


# ================================================================ LOCKED slides
def guest_slide(guest_bg, soft, page, total):
    """Meeting + special guest slide (locked content)."""
    if guest_bg is not None and config.GUEST_LINE:
        img = ImageOps.fit(guest_bg, (W, H), method=Image.LANCZOS).convert("RGBA")
        img.alpha_composite(vertical_fade(30, 250, start=0.18))
    else:
        img = soft.copy()
    img.alpha_composite(code_rain("guest", 0.25))
    scanlines(img)
    img = img.convert("RGB")
    d = ImageDraw.Draw(img, "RGBA")
    top_bar(d, "Next meeting")
    max_w = W - 2 * M
    heading = config.GUEST_HEADING if config.GUEST_LINE else "Next meeting"
    rows = [("WHEN", f"{config.MEETING_DAY} · {config.MEETING_TIME}"),
            ("WHERE", f"{config.MEETING_PLACE}, The Grove")]
    h_f, h_l, h_h = fit(d, heading, "head", max_w, 250, 128, 90, 1.0)
    b_f, b_l, b_h = fit(d, config.GUEST_BODY if config.GUEST_LINE else "", "bodybold", max_w, 130, 44, 36, 1.3)
    a_f, a_l, a_h = fit(d, config.MEETING_ADDRESS, "body", max_w - 60, 100, 36, 32, 1.25)
    rows_h = 2 * 62 + 16 + len(a_l) * a_h + 34
    block = 56 + len(h_l) * h_h + 50 + len(b_l) * b_h + 40 + rows_h
    y = H - M - 64 - block
    tracked(d, (M, y), "> SPECIAL GUEST" if config.GUEST_LINE else "> SAVE THE DATE", F("label", 32), A1, 4)
    y += 56
    y = gradient_lines(img, d, h_l, h_f, h_h, M, y)
    accent_bar(img, M, y + 20)
    y = text_block(d, b_l, b_f, b_h, M, y + 50, WHITE) + 30
    panel(d, (M, y, W - M, y + rows_h), fill=(0, 10, 4, 220))
    ry = y + 22
    for key, val in rows:
        d.text((M + 30, ry + 8), key, font=F("label", 26), fill=A1)
        v_f = F("bodybold", 38)
        while d.textlength(val, font=v_f) > max_w - 220 and v_f.size > 30:
            v_f = F("bodybold", v_f.size - 1)
        d.text((M + 170, ry), val, font=v_f, fill=WHITE)
        ry += 62
    d.line((M + 30, ry, W - M - 30, ry), fill=A1 + (60,), width=2)
    text_block(d, a_l, a_f, a_h, M + 30, ry + 14, SOFT)
    return img, d


def reveal_slide(soft, page, total):
    """'This post was made by an AI agent' (locked content, second to last)."""
    img, d = base(soft, "agent", glow_xy=(W // 2, 420), glow_strength=45)
    top_bar(d, "How was this made?")
    max_w = W - 2 * M
    h_f, h_l, h_h = fit(d, "This post was made by an AI agent.", "head", max_w, 210, 84, 70, 1.03)
    y = gradient_lines(img, d, h_l, h_f, h_h, M, 196)
    steps = ["Picked the topic", "Wrote every slide", "Generated the artwork",
             "Designed the layout", "Published to Instagram"]
    y += 40
    step_f, num_f = F("bodybold", 38), F("label", 26)
    for i, s in enumerate(steps):
        cy = y + i * 70
        if i < len(steps) - 1:
            d.line((M + 23, cy + 46, M + 23, cy + 70), fill=A1 + (90,), width=2)
        d.rectangle((M, cy, M + 46, cy + 46), fill=(0, 20, 8), outline=A1, width=2)
        n = str(i + 1)
        d.text((M + 23 - d.textlength(n, font=num_f) / 2, cy + 7), n, font=num_f, fill=A1)
        d.text((M + 70, cy + 1), s, font=step_f, fill=WHITE)
    y = y + len(steps) * 70 + 4
    d.text((M, y), config.AGENT_APPROVAL_LINE, font=F("body", 34), fill=DIM)
    top, bottom = H - M - 300, H - M - 54
    panel(d, (M, top, W - M, bottom), fill=(0, 18, 7, 240), outline_alpha=240)
    j_f, j_l, j_h = fit(d, config.JOIN_INFO, "head", W - 2 * M - 88, bottom - top - 70, 60, 48, 1.15)
    text_block(d, j_l, j_f, j_h, M + 44, top + (bottom - top - len(j_l) * j_h) / 2 - 4, WHITE)
    return img, d


def qr_image(url, size):
    import qrcode
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_Q, border=4, box_size=20)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color=(0, 0, 0), back_color=(255, 255, 255)).convert("RGB")
    return img.resize((size, size), Image.NEAREST)


def qr_slide(soft, page, total):
    """QR finale (locked content, always last)."""
    img, d = base(soft, "qr", glow_xy=(W // 2, 640), glow_strength=80, rain=0.35)
    top_bar(d, "Join the club")
    # 1) biggest text
    t_f = F("mono", 96)
    title = "SCAN TO JOIN"
    while d.textlength(title, font=t_f) > W - 2 * M and t_f.size > 70:
        t_f = F("mono", t_f.size - 2)
    gradient_text(img, ((W - d.textlength(title, font=t_f)) / 2, 166), title, t_f)
    # 2) the QR code: 640px, centered, white panel + green frame
    q = 640
    url_f = F("label", 24)
    px0, py0 = (W - q - 32) // 2, 280
    d.rounded_rectangle((px0 - 6, py0 - 6, px0 + q + 38, py0 + q + 60), radius=26, outline=A1, width=4)
    d.rounded_rectangle((px0, py0, px0 + q + 32, py0 + q + 54), radius=20, fill=(255, 255, 255))
    img.paste(qr_image(config.REGISTER_URL, q), (px0 + 16, py0 + 8))
    url = config.REGISTER_URL.replace("https://", "").rstrip("/")
    d.text(((W - d.textlength(url, font=url_f)) / 2, py0 + q + 14), url, font=url_f, fill=(0, 60, 20))
    # 3) how to open it
    y = py0 + q + 76
    i_f, i_l, i_h = fit(d, "Or screenshot this and press & hold the QR code", "bodybold",
                        W - 2 * M, 112, 44, 40, 1.22)
    y = text_block(d, i_l, i_f, i_h, M, y, WHITE, center=True) + 6
    l_f = F("head", 56)
    link = "Link in our bio ↗"
    gradient_text(img, ((W - d.textlength(link, font=l_f)) / 2, y), link, l_f, glow_amount=0.4)
    y += 72
    if meeting_upcoming():
        a_f = F("label", 26)
        addr = f"{config.MEETING_PLACE} · {config.MEETING_ADDRESS_SHORT}"
        while d.textlength(addr, font=a_f) > W - 2 * M and a_f.size > 20:
            a_f = F("label", a_f.size - 1)
        d.text(((W - d.textlength(addr, font=a_f)) / 2, y), addr, font=a_f, fill=SOFT)
    return img, d


# ================================================================ assemble
def render(plan, bg, guest_bg=None):
    bg = ImageOps.fit(bg, (W, H), method=Image.LANCZOS)
    soft = bg.filter(ImageFilter.GaussianBlur(36)).convert("RGBA")
    soft.alpha_composite(Image.new("RGBA", (W, H), config.BG_DARK + (215,)))
    locked = (["guest"] if meeting_upcoming() else []) + ["reveal", "qr"]
    content = [dict(x) for x in plan["slides"][:MAX_SLIDES - 1 - len(locked)]]
    statements = [x for x in content if x["type"] == "statement"]
    if len(statements) > 1:
        for k, x in enumerate(statements, 1):
            x["_num"] = k
    total = 1 + len(content) + len(locked)
    out = [cover(bg, plan, total, plan.get("cover_style", "art"))]
    for i, s in enumerate(content):
        img, d = RENDERERS.get(s["type"], s_statement)(soft, s, len(out) + 1, total, i + 1)
        top_bar(d)
        bottom_bar(d, len(out) + 1, total)
        out.append(img)
    for kind in locked:
        page = len(out) + 1
        if kind == "guest":
            img, d = guest_slide(guest_bg, soft, page, total)
        elif kind == "reveal":
            img, d = reveal_slide(soft, page, total)
        else:
            img, d = qr_slide(soft, page, total)
        bottom_bar(d, page, total)
        out.append(img)
    return out


# ================================================================ demo content
def demo_background(seed=1):
    img = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=(0, int(30 * (1 - t)), int(12 * (1 - t))))
    rnd = random.Random(seed)
    for _ in range(26):
        x = rnd.randint(0, W)
        d.line((x, 0, x, rnd.randint(200, 900)), fill=(0, rnd.randint(80, 200), 40), width=2)
    return img.filter(ImageFilter.GaussianBlur(2))


DEMO_PLAN = {
    "format": "mixed demo", "cover_style": "terminal",
    "cover": {"title": "Your next coworker is an AI agent", "kicker": "agentic ai"},
    "slides": [
        {"type": "big_word", "word": "Goal in. Results out.", "caption": "You give an agent a goal. It figures out the steps itself."},
        {"type": "terminal", "title": "agent.log", "lines": ["> goal: make an AI club post", "planning... 4 steps", "> write_slides()", "done: 7 slides", "> generate_art()", "done: cover.jpg"]},
        {"type": "myth_fact", "myth": "AI agents are just chatbots with a new name.", "fact": "Chatbots reply. Agents plan, use tools, check the result, and keep going until the job is done."},
        {"type": "versus", "heading": "Chatbot vs. agent", "left_title": "Chatbot", "left_points": ["Answers one message", "Waits for you", "Talks only"], "right_title": "Agent", "right_points": ["Works toward a goal", "Takes the next step", "Uses real tools"]},
        {"type": "steps", "heading": "The agent loop", "steps": ["Plan the next step", "Use a tool", "Check the result", "Repeat until done"]},
    ],
    "caption_hook": "Your next group project partner might not be human 👀",
    "caption_body": "Swipe to see what makes an AI agent different from a chatbot. This whole post was made by one.",
    "hashtags": ["#AgenticAI", "#AIAgents", "#AIClub", "#LearnAI", "#StudentTech"],
    "image_prompt": "demo",
}


# ================================================================ saving
def save(draft_dir, plan, bg, guest_bg, meta):
    draft_dir.mkdir(parents=True, exist_ok=True)
    ImageOps.fit(bg, (W, H), method=Image.LANCZOS).save(draft_dir / "background.jpg", "JPEG", quality=90)
    for old in draft_dir.glob("slide*.jpg"):
        old.unlink()
    names = []
    for i, slide in enumerate(render(plan, bg, guest_bg), start=1):
        name = f"slide{i}.jpg"
        slide.save(draft_dir / name, "JPEG", quality=93, optimize=True)
        names.append(name)
    meta.update({"title": plan["title"], "caption": build_caption(plan), "slides": names,
                 "format": plan.get("format", ""), "plan": plan, "updated": now_iso()})
    (draft_dir / "draft.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (DRAFTS / "LATEST").write_text(meta["id"], encoding="utf-8")
    return meta


def new_draft(demo=False):
    topic = pick_topic()
    n = draft_count()
    fmt = FORMATS[n % len(FORMATS)]
    style = COVER_STYLES[n % len(COVER_STYLES)]
    print(f"Topic: {topic} | format: {fmt[0]} | cover: {style}")
    if demo:
        plan, bg = json.loads(json.dumps(DEMO_PLAN)), demo_background()
        guest_bg = guest_background(None)
        plan = _clean_plan(plan)
        plan["cover_style"] = os.getenv("COVER", "terminal")
    else:
        from openai import OpenAI
        client = OpenAI()
        plan = make_plan(client, topic, fmt)
        plan["format"], plan["cover_style"] = fmt[0], style
        print(f"Title: {plan['title']}")
        bg = make_background(client, plan.get("image_prompt") or topic)
        guest_bg = guest_background(client) if meeting_upcoming() and config.GUEST_LINE else None
    draft_id = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d-%H%M")
    meta = {"id": draft_id, "topic": topic, "status": "waiting", "version": 1,
            "created": now_iso(), "changes": []}
    save(DRAFTS / draft_id, plan, bg, guest_bg, meta)
    print(f"Draft saved: {draft_id}")


def revise(draft_id, feedback):
    from openai import OpenAI
    client = OpenAI()
    folder = DRAFTS / draft_id
    meta = json.loads((folder / "draft.json").read_text(encoding="utf-8"))
    old = meta["plan"]
    if "cover" not in old:  # draft made by an older version of this script
        old = {"cover": {"title": old.get("title", ""), "kicker": ""},
               "slides": [dict(type="statement", **s) for s in old.get("slides", [])],
               "caption_hook": "", "caption_body": old.get("caption", ""),
               "hashtags": old.get("hashtags", []), "image_prompt": old.get("image_prompt", ""),
               "cover_style": "art"}
    plan, regen = revise_plan(client, old, feedback)
    if regen:
        print("Making new artwork")
        bg = make_background(client, plan.get("image_prompt") or old.get("image_prompt", ""))
    else:
        bg = Image.open(folder / "background.jpg").convert("RGB")
    guest_bg = guest_background(client) if meeting_upcoming() and config.GUEST_LINE else None
    meta["version"] = meta.get("version", 1) + 1
    meta.setdefault("changes", []).append({"version": meta["version"], "request": feedback, "at": now_iso()})
    save(folder, plan, bg, guest_bg, meta)
    print(f"Revised {draft_id} to version {meta['version']}")


if __name__ == "__main__":
    if "--revise" in sys.argv:
        revise(sys.argv[sys.argv.index("--revise") + 1], os.environ["FEEDBACK"])
    else:
        new_draft(demo="--demo" in sys.argv)
