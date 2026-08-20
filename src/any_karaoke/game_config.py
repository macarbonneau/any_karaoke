import os

# ================================================
# Paths
# ================================================
# Both can be overridden with environment variables so an installed (non-editable)
# package does not try to write inside site-packages.
_PACKAGE_PARENT = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), ".."))

TEMP_PATH = os.path.abspath(os.environ.get("ANY_KARAOKE_TEMP", os.path.join(_PACKAGE_PARENT, "tmp")))
MODEL_CACHE = os.path.abspath(os.environ.get("ANY_KARAOKE_MODELS", os.path.join(_PACKAGE_PARENT, "models")))

# ================================================
# Extractor
# ================================================
EXTRACT_MODEL = "htdemucs"
WHISPER_MODEL = "large-v3"

# ================================================
# Game window
# ================================================
FPS = 60
FONT_SIZE = 100

# Seconds added to the playback clock before looking up lyrics. Positive values make
# lyrics appear earlier, to compensate for audio output latency.
LYRICS_TIME_OFFSET = 0.0

# ================================================
# Colors
# ================================================
WHITE = (255, 255, 255)

DEFAULT_OBJECT_COLOR = (255, 255, 255)
BACK_COLOR = (1, 1, 1)

DEFAULT_FONT_COLOR = (0, 255, 0)
FONT_COLOR_CURRENT = (128, 255, 128)
FONT_COLOR_PAST = (50, 50, 50)
FONT_COLOR_NEXT = (200, 200, 200)
