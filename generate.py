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
import random
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

import config

W, H = 1080, 1350  # Instagram portrait (4:5)
M = 88             # side margin
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
PANEL = (2, 14, 7)


def meeting_upcoming():
    """True until the day after the meeting (Eastern time is close enough to UTC-4/5)."""
    if not getattr(config, "MEETING_DATE", ""):
        return False
    meeting = datetime.date.fromisoformat(config.MEETING_DATE)
    today = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=5)).date()
    return today <= meeting


def meeting_caption():
    if not meeting_upcoming():
        return "🔗 Learn more and register: link in our bio"
    lines = [f"📅 Next meeting: {config.MEETING_DAY} · {config.MEETING_TIME}",
             f"📍 {config.MEETING_PLACE}, {config.MEETING_PLACE_DETAIL}"]
    if config.GUEST_LINE:
        lines.append(f"🎤 Special guest: {config.GUEST_LINE}")
    lines.append("🔗 Register with the link in our bio (or scan the QR code in the slides)")
    return "\n".join(lines)


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
  "caption": "Instagram caption: 2-3 short sentences, 1-3 emojis allowed, mention that an AI agent made this post. Do NOT include dates, times, places, links or hashtags (those are added automatically).",
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
    "Vertical background artwork for a premium Instagram post in a 'hacker / Matrix' aesthetic. "
    "Pitch black background, glowing neon green (#00FF41) light, cascading streams of abstract green "
    "light like digital rain, circuit traces, holographic wireframes, subtle CRT scanline glow, "
    "cinematic depth, lots of calm dark empty space in the lower half. "
    "Absolutely NO readable text, letters, numbers, words, logos, or watermarks anywhere. "
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


def guest_background(client):
    """The guest-slide artwork is made once and reused, so every post doesn't pay for it."""
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
    """Glowing green text: a blurred glow underneath, gradient fill on top."""
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).text(xy, text, font=fnt, fill=255)
    box = mask.getbbox()
    if not box:
        return
    glow_layer = Image.new("RGB", img.size, A1)
    img.paste(glow_layer, (0, 0), mask.filter(ImageFilter.GaussianBlur(18)).point(lambda v: v * 0.55))
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


GLYPHS = "01アイウエオカキクケコ<>{}[]#$%&*+=/\\|"
RAIN_CHARS = "0123456789ABCDEF<>{}[]#$%&*+=/|:;"


def code_rain(seed, strength=1.0):
    """A 'digital rain' layer of falling characters, faded so text stays readable."""
    rnd = random.Random(seed)
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


def top_bar(d):
    f = F("label", 24)
    label = "> " + config.SERIES_LABEL.upper()
    w = tracked_width(d, label, f) + 70
    d.rounded_rectangle((M, M, M + w, M + 56), radius=8, fill=(0, 20, 8, 200),
                        outline=A1 + (160,), width=2)
    d.rectangle((M + 22, M + 21, M + 34, M + 35), fill=A1)
    tracked(d, (M + 46, M + 13), label, f, A1)

    badge = "MADE BY AN AI AGENT"
    bw = tracked_width(d, badge, f) + 52
    x = W - M - bw
    d.rounded_rectangle((x, M, x + bw, M + 56), radius=8, fill=(0, 0, 0, 190),
                        outline=A1 + (220,), width=2)
    tracked(d, (x + 26, M + 13), badge, f, WHITE)


def bottom_bar(d, page, total):
    f = F("label", 23)
    if meeting_upcoming():
        label = f"NEXT MEETING: {config.MEETING_DAY.upper()} · {config.MEETING_TIME} · {config.MEETING_PLACE.upper()}"
    else:
        label = config.INSTAGRAM_HANDLE or config.CLUB_NAME
    x = W - M
    dots_w = sum((40 if i == page else 10) + 8 for i in range(1, total + 1))
    max_w = W - 2 * M - dots_w - 30
    while d.textlength(label, font=f) > max_w and f.size > 16:
        f = F("label", f.size - 1)
    d.text((M, H - M - 16), label, font=f, fill=DIM if not meeting_upcoming() else A2)
    for i in range(total, 0, -1):
        w = 40 if i == page else 10
        x -= w
        d.rectangle((x, H - M - 4, x + w, H - M + 6), fill=A1 if i == page else (255, 255, 255, 70))
        x -= 8


# ================================================================ slides
def cover(bg, plan, total):
    img = bg.convert("RGBA")
    img.alpha_composite(vertical_fade(60, 250, start=0.30))
    img.alpha_composite(code_rain(plan["title"], 0.35))
    scanlines(img)
    img = img.convert("RGB")
    d = ImageDraw.Draw(img, "RGBA")
    top_bar(d)
    max_w = W - 2 * M
    sub_f, sub_l, sub_h = fit(d, plan.get("subtitle", ""), "body", max_w, 150, 42, 32, 1.3)
    t_f, t_l, t_h = fit(d, plan["title"], "head", max_w, 480, 124, 70, 1.0)
    block = len(t_l) * t_h + 74 + len(sub_l) * sub_h + 90
    y = H - M - 70 - block
    for i, line in enumerate(t_l):
        gradient_text(img, (M, y + i * t_h), line, t_f) if i == len(t_l) - 1 else \
            d.text((M, y + i * t_h), line, font=t_f, fill=WHITE)
    y += len(t_l) * t_h
    accent_bar(img, M, y + 34)
    y = text_block(d, sub_l, sub_f, sub_h, M, y + 74, SOFT)
    tracked(d, (M, y + 34), "> SWIPE_", F("label", 28), A1, spacing=3)
    bottom_bar(d, 1, total)
    return img


def soft_base(bg, seed):
    img = bg.copy()
    img.alpha_composite(code_rain(seed, 0.4))
    scanlines(img)
    return img


def lesson(soft, heading, body, page, total):
    img = soft_base(soft, heading)
    glow(img, W - 120, 330, 330, A1, 50)
    img = img.convert("RGB")
    d = ImageDraw.Draw(img, "RGBA")
    top_bar(d)
    max_w = W - 2 * M
    gradient_text(img, (M - 6, 220), f"{page - 1:02d}", F("mono", 210))
    h_f, h_l, h_h = fit(d, heading, "head", max_w, 300, 84, 54, 1.05)
    y = text_block(d, h_l, h_f, h_h, M, 520, WHITE)
    accent_bar(img, M, y + 26)
    b_f, b_l, b_h = fit(d, body, "body", max_w, H - y - 300, 50, 34, 1.42)
    text_block(d, b_l, b_f, b_h, M, y + 76, SOFT)
    bottom_bar(d, page, total)
    return img


def guest_slide(guest_bg, soft, page, total):
    if guest_bg is not None:
        img = ImageOps.fit(guest_bg, (W, H), method=Image.LANCZOS).convert("RGBA")
        img.alpha_composite(vertical_fade(40, 245, start=0.25))
    else:
        img = soft.copy()
    img.alpha_composite(code_rain("guest", 0.3))
    scanlines(img)
    img = img.convert("RGB")
    d = ImageDraw.Draw(img, "RGBA")
    top_bar(d)
    max_w = W - 2 * M
    b_f, b_l, b_h = fit(d, config.GUEST_BODY, "body", max_w, 220, 42, 30, 1.38)
    h_f, h_l, h_h = fit(d, config.GUEST_HEADING, "head", max_w, 260, 128, 80, 1.0)
    block = 60 + len(h_l) * h_h + 70 + len(b_l) * b_h
    y = H - M - 80 - block
    tracked(d, (M, y), "> SPECIAL GUEST", F("label", 32), A1, spacing=4)
    y += 60
    for i, line in enumerate(h_l):
        gradient_text(img, (M, y + i * h_h), line, h_f)
    y += len(h_l) * h_h
    accent_bar(img, M, y + 28)
    text_block(d, b_l, b_f, b_h, M, y + 70, WHITE)
    bottom_bar(d, page, total)
    return img


def qr_image(url, size):
    import qrcode
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=2, box_size=10)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color=(225, 255, 232)).convert("RGB")
    return img.resize((size, size), Image.NEAREST)


def meeting_slide(soft, page, total):
    img = soft_base(soft, "meeting")
    glow(img, W // 2, 380, 380, A1, 45)
    img = img.convert("RGB")
    d = ImageDraw.Draw(img, "RGBA")
    top_bar(d)
    max_w = W - 2 * M
    tracked(d, (M, 200), "> NEXT MEETING", F("label", 32), A1, spacing=4)
    day_f, day_l, day_h = fit(d, config.MEETING_DAY, "head", max_w, 220, 104, 70, 1.0)
    y = 250
    for i, line in enumerate(day_l):
        gradient_text(img, (M, y + i * day_h), line, day_f)
    y += len(day_l) * day_h + 30

    rows = [("TIME", config.MEETING_TIME),
            ("WHERE", f"{config.MEETING_PLACE} · {config.MEETING_PLACE_DETAIL}")]
    if config.GUEST_LINE:
        rows.append(("GUEST", config.GUEST_LINE))
    key_f, val_f = F("label", 26), F("bodybold", 36)
    for key, val in rows:
        d.line((M, y, W - M, y), fill=A1 + (70,), width=2)
        d.text((M, y + 22), key, font=key_f, fill=A1)
        v_f, v_l, v_h = fit(d, val, "bodybold", max_w - 190, 100, 36, 26, 1.25)
        text_block(d, v_l, v_f, v_h, M + 190, y + 18, WHITE)
        y += max(80, len(v_l) * v_h + 40)
    d.line((M, y, W - M, y), fill=A1 + (70,), width=2)

    # QR code card
    q = 260
    top = H - M - 70 - q - 40
    d.rounded_rectangle((M, top, W - M, top + q + 40), radius=18, fill=(0, 12, 5, 230),
                        outline=A1 + (200,), width=2)
    img.paste(qr_image(config.REGISTER_URL, q), (M + 20, top + 20))
    tx = M + 20 + q + 40
    d.text((tx, top + 44), "Scan to register", font=F("head", 50), fill=WHITE)
    s_f, s_l, s_h = fit(d, "or tap the link in our bio. Open to all skill levels.",
                        "body", W - M - 30 - tx, 150, 32, 24, 1.35)
    text_block(d, s_l, s_f, s_h, tx, top + 118, SOFT)
    bottom_bar(d, page, total)
    return img


def agent_story(soft, page, total):
    img = soft_base(soft, "agent")
    glow(img, W // 2, 420, 420, A1, 45)
    img = img.convert("RGB")
    d = ImageDraw.Draw(img, "RGBA")
    top_bar(d)
    max_w = W - 2 * M
    tracked(d, (M, 200), "> HOW WAS THIS MADE?", F("label", 30), A1, spacing=4)
    h_f, h_l, h_h = fit(d, "This post was made by an AI agent.", "head", max_w, 200, 80, 56, 1.03)
    y = text_block(d, h_l, h_f, h_h, M, 252, WHITE)

    steps = ["Picked today's topic", "Wrote every slide", "Generated the artwork",
             "Designed the slides", "Published to Instagram"]
    y += 44
    step_f, num_f = F("bodybold", 36), F("label", 24)
    for i, s in enumerate(steps):
        cy = y + i * 72
        if i < len(steps) - 1:
            d.line((M + 23, cy + 46, M + 23, cy + 72), fill=A1 + (90,), width=2)
        d.rectangle((M, cy, M + 46, cy + 46), fill=(0, 20, 8), outline=A1, width=2)
        n = str(i + 1)
        d.text((M + 23 - d.textlength(n, font=num_f) / 2, cy + 8), n, font=num_f, fill=A1)
        d.text((M + 70, cy + 2), s, font=step_f, fill=WHITE)
    y = y + len(steps) * 72 + 6
    s_f, s_l, s_h = fit(d, config.AGENT_STORY.split(". ")[-1], "body", max_w, 90, 32, 26, 1.35)
    y = text_block(d, s_l, s_f, s_h, M, y, DIM)

    top, bottom = max(y + 36, H - M - 290), H - M - 50
    d.rounded_rectangle((M, top, W - M, bottom), radius=18, fill=(0, 12, 5, 235),
                        outline=A1 + (220,), width=2)
    gradient_text(img, (M + 44, top + 34), "That's agentic AI.", F("head", 50))
    j_f, j_l, j_h = fit(d, config.JOIN_INFO, "body", W - 2 * M - 88, bottom - top - 130, 36, 26, 1.38)
    text_block(d, j_l, j_f, j_h, M + 44, top + 104, SOFT)
    bottom_bar(d, page, total)
    return img


def render(plan, bg, guest_bg=None):
    bg = ImageOps.fit(bg, (W, H), method=Image.LANCZOS)
    soft = bg.filter(ImageFilter.GaussianBlur(36)).convert("RGBA")
    soft.alpha_composite(Image.new("RGBA", (W, H), config.BG_DARK + (215,)))
    extras = []
    if meeting_upcoming():
        if config.GUEST_LINE:
            extras.append("guest")
        extras.append("meeting")
    total = 1 + len(plan["slides"]) + len(extras) + 1
    out = [cover(bg, plan, total)]
    for i, s in enumerate(plan["slides"]):
        out.append(lesson(soft, s["heading"], s["body"], len(out) + 1, total))
    for e in extras:
        if e == "guest":
            out.append(guest_slide(guest_bg, soft, len(out) + 1, total))
        else:
            out.append(meeting_slide(soft, len(out) + 1, total))
    out.append(agent_story(soft, total, total))
    return out


# ================================================================ demo content
def demo_background(seed=1, castle=False):
    img = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=(0, int(30 * (1 - t)), int(12 * (1 - t))))
    if castle:  # crude placeholder silhouette for local testing only
        d.polygon([(300, 900), (300, 600), (340, 520), (380, 600), (380, 700), (480, 700), (480, 450),
                   (540, 330), (600, 450), (600, 700), (700, 700), (700, 600), (740, 520), (780, 600),
                   (780, 900)], fill=(0, 60, 25))
        for i in range(40):
            x, y = (i * 97) % W, 80 + (i * 53) % 400
            d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(150, 255, 180))
    else:
        rnd = random.Random(seed)
        for _ in range(26):
            x = rnd.randint(0, W)
            d.line((x, 0, x, rnd.randint(200, 900)), fill=(0, rnd.randint(80, 200), 40), width=2)
    return img.filter(ImageFilter.GaussianBlur(2))


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
    "caption": "This post was planned, written, designed and published by an AI agent 🤖 Swipe to see how agents actually work.",
    "hashtags": ["#AgenticAI", "#AI", "#AIAgents", "#AIClub", "#LearnAI", "#STEM"],
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
    caption = (plan["caption"].strip() + "\n\n" + meeting_caption() + "\n\n"
               + " ".join(plan.get("hashtags", [])[:10]))
    meta.update({"title": plan["title"], "caption": caption, "slides": names, "plan": plan,
                 "updated": now_iso()})
    (draft_dir / "draft.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (DRAFTS / "LATEST").write_text(meta["id"], encoding="utf-8")
    return meta


def new_draft(demo=False):
    topic = pick_topic()
    print(f"Topic: {topic}")
    if demo:
        plan, bg, guest_bg = DEMO_PLAN, demo_background(), demo_background(castle=True)
    else:
        from openai import OpenAI
        client = OpenAI()
        plan = make_plan(client, topic)
        print(f"Title: {plan['title']}")
        bg = make_background(client, plan["image_prompt"])
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
    plan = revise_plan(client, meta["plan"], feedback)
    if plan.pop("regenerate_image", False):
        print("Making new artwork")
        bg = make_background(client, plan.get("image_prompt") or meta["plan"]["image_prompt"])
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
