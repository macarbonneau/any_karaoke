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
