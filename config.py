"""Edit this file to match your club. Everything here is safe to share (no secrets)."""
import os

# --- About your club (edit these!) ---
CLUB_NAME = "AI Club"
INSTAGRAM_HANDLE = ""  # e.g. "@yourclub" - shown in small text on each slide
CLUB_DESCRIPTION = (
    "A student club where members learn how artificial intelligence works, "
    "build projects together, and explore how AI is changing the world. "
    "Right now the club is focused on agentic AI: AI systems that plan and take "
    "actions on their own, like the agent that makes this club's Instagram posts."
)
SERIES_LABEL = "Agentic AI"  # small label on the cover of every post

# Last slide of every post: the "how was this made?" hook.
AGENT_STORY = (
    "An AI agent picked this topic, wrote every slide, generated the artwork, "
    "and published it here. A club member just tapped approve."
)
JOIN_INFO = "Want to know how it works? Come to our meetings. Check our bio for times."

# --- Colors (hex) ---
ACCENT = "#8B5CF6"    # violet
ACCENT_2 = "#22D3EE"  # cyan
BG_DARK = (7, 9, 24)

# --- Which OpenAI models to use ---
# If OpenAI renames models, change these (or set them as GitHub Variables).
TEXT_MODEL = os.getenv("TEXT_MODEL") or "gpt-4.1-mini"
IMAGE_MODEL = os.getenv("IMAGE_MODEL") or "gpt-image-1"
IMAGE_QUALITY = os.getenv("IMAGE_QUALITY") or "high"  # low / medium / high

# --- Instagram ---
GRAPH_VERSION = os.getenv("GRAPH_VERSION") or "v26.0"
