import os

# ================================================
# Paths
# ================================================
# Both can be overridden with environment variables so an installed (non-editable)
# package does not try to write inside site-packages.
_PACKAGE_PARENT = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), ".."))

MODEL_CACHE = os.path.abspath(os.environ.get("ANY_KARAOKE_MODELS", os.path.join(_PACKAGE_PARENT, "models")))

# ================================================
# Extractor
# ================================================
EXTRACT_MODEL = "htdemucs"
WHISPER_MODEL = "large-v3"
WHISPER_MODEL_CHOICES = ("large-v3", "large-v2", "medium", "small", "base", "tiny")

# Stems are written as mp3 to keep a library small. 320kbps is roughly a fifth of the
# wav size. "wav" is still accepted for lossless output.
OUTPUT_AUDIO_FORMAT = "mp3"
MP3_BITRATE = 320

# ================================================
# Game window
# ================================================
FPS = 60

# Seconds added to the playback clock before looking up lyrics. Positive values make
# lyrics appear earlier, to compensate for audio output latency. Adjustable at runtime
# from the View menu; this is only the starting value.
LYRICS_TIME_OFFSET = 0.0
LYRICS_NUDGE_STEP = 0.1

# ================================================
# Menu bar
# ================================================
MENU_BAR_HEIGHT = 34
MENU_FONT_SIZE = 26
MENU_BACK_COLOR = (24, 24, 28, 235)  # includes alpha, the bar sits over the lyrics
MENU_PANEL_COLOR = (32, 32, 38, 245)
MENU_HOVER_COLOR = (60, 90, 60)
MENU_TEXT_COLOR = (225, 225, 225)
MENU_DISABLED_COLOR = (110, 110, 110)
MENU_SHORTCUT_COLOR = (150, 150, 150)
MENU_BORDER_COLOR = (70, 70, 78)

# How long a transient message stays on screen
TOAST_SECONDS = 2.0
TOAST_FONT_SIZE = 34

# ================================================
# Logo on the idle screen
# ================================================
LOGO_HEIGHT_RATIO = 0.30
LOGO_CENTER_Y_RATIO = 0.36
# The song name sits below it rather than in the middle of the window
IDLE_TITLE_CENTER_Y_RATIO = 0.68

# ================================================
# Volume sliders
# ================================================
SLIDER_TRACK_WIDTH = 16
SLIDER_HEIGHT_RATIO = 0.46
SLIDER_CENTER_Y = 0.44
# The mixer is a fixed size control group pinned to the left edge, so it is placed in
# pixels. Scaling the gap with the window width would pull the pair apart on a wide
# screen and crush the labels together on a narrow one.
MIXER_LEFT = 62
MIXER_SPACING = 92
# Hidden again after this long without the mouse moving
SLIDER_IDLE_SECONDS = 2.5
# The visible track is slim, so the grab area is deliberately wider than it looks
SLIDER_HIT_WIDTH = 56
SLIDER_KNOB_HEIGHT = 16
SLIDER_FONT_SIZE = 26

SLIDER_TRACK_COLOR = (26, 26, 32, 200)  # translucent, the lyrics stay readable behind it
SLIDER_TRACK_BORDER = (86, 86, 98)
SLIDER_KNOB_COLOR = (242, 242, 247)
SLIDER_KNOB_BORDER = (28, 28, 34)
SLIDER_GRIP_COLOR = (150, 150, 160)
SLIDER_LABEL_COLOR = (226, 226, 232)
SLIDER_MUTED_COLOR = (128, 128, 138)
SLIDER_SHADOW_COLOR = (0, 0, 0, 90)

# One accent per stem, so the two sliders are told apart at a glance
SLIDER_MUSIC_ACCENT = (72, 190, 128)
SLIDER_VOCALS_ACCENT = (86, 158, 236)

# ================================================
# Play / stop button, sits under the sliders
# ================================================
BUTTON_WIDTH = 74
BUTTON_HEIGHT = 46
BUTTON_TOP_GAP = 34  # below the slider percentage labels
BUTTON_BACK_COLOR = (26, 26, 32, 200)
BUTTON_BORDER_COLOR = (86, 86, 98)
BUTTON_PLAY_COLOR = (72, 190, 128)
BUTTON_STOP_COLOR = (226, 92, 92)

# ================================================
# Colors
# ================================================
DEFAULT_OBJECT_COLOR = (255, 255, 255)
BACK_COLOR = (1, 1, 1)

DEFAULT_FONT_COLOR = (0, 255, 0)
FONT_COLOR_CURRENT = (128, 255, 128)
FONT_COLOR_PAST = (50, 50, 50)
FONT_COLOR_NEXT = (200, 200, 200)

# Word level highlight inside the line being sung, when the lyrics carry word timings.
# Words sweep from "not yet" through "now" to "sung", the usual karaoke fill.
FONT_COLOR_WORD_SUNG = (255, 226, 120)
FONT_COLOR_WORD_ACTIVE = (255, 255, 255)
