import os

# EXTRACTOR
EXTRACT_MODEL = "htdemucs"
WHISPER_MODEL = "large"
TEMP_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "tmp")

# GAME WINDOW
FPS = 60
FONT_SIZE = 100

# COLORS
WHITE = (255, 255, 255)

DEFAULT_OBJECT_COLOR = (255, 255, 255)
BACK_COLOR = (1, 1, 1)

DEFAULT_FONT_COLOR = (0, 255, 0)
FONT_COLOR_CURRENT = (128, 255, 128)
FONT_COLOR_PAST = (50, 50, 50)
FONT_COLOR_NEXT = (200, 200, 200)
