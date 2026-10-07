"""Edit this file to match your club. Everything here is safe to share (no secrets)."""
import os

# --- About your club ---
CLUB_NAME = "AI Club"
INSTAGRAM_HANDLE = ""  # e.g. "@yourclub" - shown in small text on each slide
CLUB_DESCRIPTION = (
    "A student club where members learn how artificial intelligence works, "
    "build projects together, and explore how AI is changing the world. "
    "Right now the club is focused on agentic AI: AI systems that plan and take "
    "actions on their own, like the agent that makes this club's Instagram posts."
)
SERIES_LABEL = "Agentic AI"  # small label on the cover of every post
REGISTER_URL = "https://ai-club-site-lime.vercel.app/"  # the QR code on the slides points here

# --- Next meeting ---
# Shown on every post until the day after the meeting. Update these for each new meeting.
# After MEETING_DATE passes, posts automatically stop showing the meeting + guest slides.
MEETING_DATE = "2026-10-13"            # YYYY-MM-DD
MEETING_DAY = "Tuesday, Oct 13"
MEETING_TIME = "3:00 - 4:00 PM"
MEETING_PLACE = "Hawkers"
MEETING_PLACE_DETAIL = "The Grove, Windermere, FL"
MEETING_ADDRESS = "9100 Conroy Windermere Rd Ste 110, Windermere, FL 34786"
MEETING_ADDRESS_SHORT = "9100 Conroy Windermere Rd Ste 110, Windermere"
MEETING_TICKER = "TUE OCT 13 · 3–4 PM · HAWKERS"  # short version for the bottom of every slide

# Special guest (leave GUEST_LINE empty "" when there's no guest)
GUEST_LINE = "A head manager of AI at Disney"
GUEST_HEADING = "AI at Disney"
GUEST_BODY = "A head manager of AI at Disney is joining our next meeting."
GUEST_IMAGE_PROMPT = (
    "a generic fairytale castle with tall spires at night, fireworks bursting in the sky, "
    "magical sparkles and stardust, cinematic. Original design, not any real or famous castle"
)

# The "this post was made by an AI agent" reveal slide (second to last).
AGENT_APPROVAL_LINE = "A club member reviewed and approved it."
JOIN_INFO = "Want to learn how? Sign up with the link in our bio."

# --- Theme: Matrix / hacker green on black ---
ACCENT = "#00FF41"    # matrix green
ACCENT_2 = "#9CFFB8"  # pale mint
BG_DARK = (0, 4, 2)

# --- Which OpenAI models to use ---
# If OpenAI renames models, change these (or set them as GitHub Variables).
TEXT_MODEL = os.getenv("TEXT_MODEL") or "gpt-4.1-mini"
IMAGE_MODEL = os.getenv("IMAGE_MODEL") or "gpt-image-1"
IMAGE_QUALITY = os.getenv("IMAGE_QUALITY") or "high"  # low / medium / high

# --- Instagram ---
GRAPH_VERSION = os.getenv("GRAPH_VERSION") or "v26.0"
