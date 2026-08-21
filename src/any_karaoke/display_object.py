import time

import pygame

from any_karaoke.assets import logo_path
from any_karaoke.game_config import (
    BUTTON_BACK_COLOR,
    BUTTON_BORDER_COLOR,
    BUTTON_HEIGHT,
    BUTTON_PLAY_COLOR,
    BUTTON_STOP_COLOR,
    BUTTON_WIDTH,
    DEFAULT_FONT_COLOR,
    DEFAULT_OBJECT_COLOR,
    FONT_COLOR_PAST,
    FONT_COLOR_CURRENT,
    FONT_COLOR_NEXT,
    FONT_COLOR_WORD_ACTIVE,
    FONT_COLOR_WORD_SUNG,
    LOGO_CENTER_Y_RATIO,
    LOGO_HEIGHT_RATIO,
    MENU_BAR_HEIGHT,
    SLIDER_FONT_SIZE,
    SLIDER_GRIP_COLOR,
    SLIDER_HEIGHT_RATIO,
    SLIDER_HIT_WIDTH,
    SLIDER_KNOB_BORDER,
    SLIDER_KNOB_COLOR,
    SLIDER_KNOB_HEIGHT,
    SLIDER_LABEL_COLOR,
    SLIDER_MUSIC_ACCENT,
    SLIDER_MUTED_COLOR,
    SLIDER_SHADOW_COLOR,
    SLIDER_TRACK_BORDER,
    SLIDER_TRACK_COLOR,
    SLIDER_TRACK_WIDTH,
    TOAST_FONT_SIZE,
    TOAST_SECONDS,
)
from any_karaoke.text_utils import split_into_sub_sentences, wrap_to_width


class Announce:
    """One big centred line, sized to fit the window.

    The text is rendered at the size it needs rather than rendered once and scaled, so a
    long song title and a short one are both sharp.
    """

    MIN_FONT_SIZE = 12

    # Kept well inside the window so a song name does not run over the mixer on the left
    def __init__(
        self,
        font_size=200,
        color=DEFAULT_FONT_COLOR,
        width_ratio=0.62,
        height_ratio=0.18,
        center_y_ratio=0.5,
    ):
        self.color = color
        self.font_size = font_size
        self.width_ratio = width_ratio
        self.height_ratio = height_ratio
        self.center_y_ratio = center_y_ratio
        self._fonts = {}
        self.font = self._font(font_size)

    def _font(self, size):
        size = max(self.MIN_FONT_SIZE, int(size))
        if size not in self._fonts:
            self._fonts[size] = pygame.font.Font(None, size)
        return self._fonts[size]

    def fitted_font_size(self, text, screen):
        """Largest size where the text fits the width and height budget."""
        width, height = screen.get_size()
        text_width, text_height = self.font.size(text)
        if text_width <= 0 or text_height <= 0:
            return self.font_size

        scale = min(
            (width * self.width_ratio) / text_width,
            (height * self.height_ratio) / text_height,
        )
        return max(self.MIN_FONT_SIZE, int(self.font_size * scale))

    def update_and_print(self, screen, text, color=None):
        if not text:
            return

        width, height = screen.get_size()
        surface = self._font(self.fitted_font_size(text, screen)).render(text, True, color or self.color)
        center = (width // 2, int(height * self.center_y_ratio))
        screen.blit(surface, surface.get_rect(center=center).topleft)


class VolumeSlider:
    """Slim vertical fader: translucent pill track, coloured fill and a rounded knob.

    The track is deliberately narrow so it does not sit on top of the lyrics, so the grab
    area (hit_rect) is kept much wider than the drawn track.
    """

    def __init__(self, label_txt, norm_x, norm_y, accent=SLIDER_MUSIC_ACCENT, slider_value=50, pixel_x=None):
        self.label = label_txt
        self.norm_x = norm_x  # normalized position (0, 1)
        # Fixed pixel offset from the left edge, used instead of norm_x when set, so a
        # group of sliders keeps its spacing whatever the window width
        self.pixel_x = pixel_x
        self.norm_y = norm_y
        self.accent = accent
        self.slider_value = slider_value
        self.font = pygame.font.Font(None, SLIDER_FONT_SIZE)
        self.dragging = False
        # Empty until the slider has been drawn once, so it cannot catch stray clicks
        self.track_rect = pygame.Rect(0, 0, 0, 0)
        self.hit_rect = pygame.Rect(0, 0, 0, 0)

    @property
    def volume(self):
        """Slider position as a pygame mixer volume (0.0 - 1.0)."""
        return self.slider_value / 100.0

    @property
    def muted(self):
        return self.slider_value <= 0

    def set_percent(self, value):
        """Move the slider to a percentage. Returns the matching mixer volume."""
        self.slider_value = max(0, min(100, value))
        return self.volume

    def layout(self, screen):
        """Work out the track and grab rectangles for the current window size."""
        width, height = screen.get_size()
        track_height = SLIDER_HEIGHT_RATIO * height
        centre_x = self.pixel_x if self.pixel_x is not None else width * self.norm_x
        centre_y = height * self.norm_y

        self.track_rect = rectangle_cs(centre_x, centre_y, SLIDER_TRACK_WIDTH, track_height)
        self.hit_rect = rectangle_cs(
            centre_x,
            centre_y,
            max(SLIDER_HIT_WIDTH, SLIDER_TRACK_WIDTH * 3),
            track_height + SLIDER_KNOB_HEIGHT,
        )
        return self.track_rect

    def update_drag(self, mouse_pos, pressed):
        """Adjust the level while the button is held. Returns the new volume, or None.

        Once a drag starts the slider keeps following the mouse even if it wanders off
        the track, which is what every other fader does.
        """
        if not pressed:
            self.dragging = False
            return None

        if not self.dragging:
            if not self.hit_rect.collidepoint(mouse_pos):
                return None
            self.dragging = True

        if not self.track_rect.height:
            return None

        ratio = 1 - (mouse_pos[1] - self.track_rect.top) / self.track_rect.height
        return self.set_percent(ratio * 100)

    def update_and_print(self, screen):
        track = self.layout(screen)
        radius = SLIDER_TRACK_WIDTH // 2
        hovered = self.dragging or self.hit_rect.collidepoint(pygame.mouse.get_pos())

        self._draw_shadow(screen, track, radius)
        self._draw_track(screen, track, radius)
        fill_top = self._draw_fill(screen, track, radius, hovered)
        self._draw_knob(screen, track, fill_top, hovered)
        self._draw_labels(screen, track)

    # --- pieces
    def _draw_shadow(self, screen, track, radius):
        shadow = pygame.Surface((track.width + 6, track.height + 6), pygame.SRCALPHA)
        pygame.draw.rect(shadow, SLIDER_SHADOW_COLOR, shadow.get_rect(), border_radius=radius + 3)
        screen.blit(shadow, (track.left - 3, track.top - 1))

    def _draw_track(self, screen, track, radius):
        panel = pygame.Surface(track.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, SLIDER_TRACK_COLOR, panel.get_rect(), border_radius=radius)
        screen.blit(panel, track.topleft)
        pygame.draw.rect(screen, SLIDER_TRACK_BORDER, track, width=1, border_radius=radius)

    def _draw_fill(self, screen, track, radius, hovered):
        """Colour from the bottom up to the current level. Returns the y of the level."""
        fill_height = int(track.height * self.volume)
        fill_top = track.bottom - fill_height
        if fill_height <= 0:
            return track.bottom

        colour = brighten(self.accent, 1.15) if hovered else self.accent
        fill = pygame.Rect(track.left, fill_top, track.width, fill_height)
        # A short fill cannot take the full corner radius without looking pinched
        pygame.draw.rect(screen, colour, fill, border_radius=min(radius, fill_height // 2))

        return fill_top

    def _draw_knob(self, screen, track, fill_top, hovered):
        knob_width = SLIDER_TRACK_WIDTH * (2.6 if hovered else 2.2)
        knob = rectangle_cs(track.centerx, fill_top, knob_width, SLIDER_KNOB_HEIGHT)
        knob_radius = SLIDER_KNOB_HEIGHT // 2

        pygame.draw.rect(screen, SLIDER_KNOB_COLOR, knob, border_radius=knob_radius)
        pygame.draw.rect(screen, SLIDER_KNOB_BORDER, knob, width=1, border_radius=knob_radius)
        # Grip line, so the knob reads as something you can grab
        pygame.draw.line(
            screen,
            SLIDER_GRIP_COLOR,
            (knob.left + 5, knob.centery),
            (knob.right - 5, knob.centery),
        )

    def _draw_labels(self, screen, track):
        colour = SLIDER_MUTED_COLOR if self.muted else SLIDER_LABEL_COLOR

        name = self.font.render(self.label.upper(), True, colour)
        screen.blit(name, name.get_rect(midbottom=(track.centerx, track.top - 10)))

        reading = "muted" if self.muted else f"{int(round(self.slider_value))}%"
        value = self.font.render(reading, True, colour)
        screen.blit(value, value.get_rect(midtop=(track.centerx, track.bottom + 8)))


def brighten(color, factor):
    return tuple(min(255, int(channel * factor)) for channel in color[:3])


class PlayStopButton:
    """Transport button under the mixer, showing a play triangle or a stop square.

    `playing` is a callable so the icon always reflects the real state rather than a
    copy that could drift from it.
    """

    def __init__(self, playing, width=BUTTON_WIDTH, height=BUTTON_HEIGHT):
        self.playing = playing
        self.width = width
        self.height = height
        # Empty until laid out, so it cannot catch clicks before it is on screen
        self.rect = pygame.Rect(0, 0, 0, 0)

    @property
    def showing_stop(self):
        return bool(self.playing())

    def layout(self, center_x, top):
        self.rect = pygame.Rect(int(center_x - self.width // 2), int(top), self.width, self.height)
        return self.rect

    def hit(self, position):
        return self.rect.collidepoint(position)

    def update_and_print(self, screen):
        hovered = self.hit(pygame.mouse.get_pos())
        colour = BUTTON_STOP_COLOR if self.showing_stop else BUTTON_PLAY_COLOR
        if hovered:
            colour = brighten(colour, 1.2)

        panel = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, BUTTON_BACK_COLOR, panel.get_rect(), border_radius=10)
        screen.blit(panel, self.rect.topleft)

        border = colour if hovered else BUTTON_BORDER_COLOR
        pygame.draw.rect(screen, border, self.rect, width=2, border_radius=10)

        self._draw_icon(screen, colour)

    def _draw_icon(self, screen, colour):
        size = self.height // 3
        centre_x, centre_y = self.rect.center

        if self.showing_stop:
            square = pygame.Rect(0, 0, size * 2, size * 2)
            square.center = (centre_x, centre_y)
            pygame.draw.rect(screen, colour, square, border_radius=3)
            return

        # Nudged right so the triangle looks centred rather than measuring centred
        left = centre_x - size + 2
        pygame.draw.polygon(
            screen,
            colour,
            [(left, centre_y - size), (left, centre_y + size), (left + size * 2, centre_y)],
        )


class Logo:
    """The app logo, scaled to a share of the window height.

    Loaded once and rescaled only when the window size changes, since scaling a 1254px
    image every frame would be wasteful. Draws nothing when the artwork is missing.
    """

    def __init__(self, height_ratio=LOGO_HEIGHT_RATIO, center_y_ratio=LOGO_CENTER_Y_RATIO):
        self.height_ratio = height_ratio
        self.center_y_ratio = center_y_ratio
        self.source = None
        self._scaled = None
        self._scaled_height = None

        path = logo_path()
        if path:
            try:
                self.source = pygame.image.load(path).convert_alpha()
            except pygame.error:
                self.source = None

    @property
    def available(self):
        return self.source is not None

    def scaled_to(self, height):
        if self.source is None or height <= 0:
            return None
        if self._scaled is None or self._scaled_height != height:
            ratio = height / self.source.get_height()
            width = max(1, int(self.source.get_width() * ratio))
            self._scaled = pygame.transform.smoothscale(self.source, (width, int(height)))
            self._scaled_height = height
        return self._scaled

    def update_and_print(self, screen):
        if self.source is None:
            return

        width, height = screen.get_size()
        scaled = self.scaled_to(int(height * self.height_ratio))
        if scaled is None:
            return

        position = scaled.get_rect(center=(width // 2, int(height * self.center_y_ratio)))
        screen.blit(scaled, position.topleft)


class Toast:
    """Short lived message under the menu bar.

    Keyboard shortcuts fire while the bar is hidden, so actions like muting or nudging the
    lyric offset need some confirmation on screen.
    """

    def __init__(self, font_size=TOAST_FONT_SIZE, seconds=TOAST_SECONDS, color=DEFAULT_OBJECT_COLOR):
        self.font = pygame.font.Font(None, font_size)
        self.seconds = seconds
        self.color = color
        self.message = None
        self.shown_at = 0.0

    def show(self, message):
        self.message = message
        self.shown_at = time.time()

    def clear(self):
        self.message = None

    @property
    def expired(self):
        return self.message is None or (time.time() - self.shown_at) > self.seconds

    def update_and_print(self, screen):
        if self.expired:
            self.message = None
            return

        surface = self.font.render(self.message, True, self.color)
        position = surface.get_rect(midtop=(screen.get_width() // 2, MENU_BAR_HEIGHT + 12))

        background = pygame.Surface((surface.get_width() + 20, surface.get_height() + 10), pygame.SRCALPHA)
        background.fill((0, 0, 0, 170))
        screen.blit(background, (position.left - 10, position.top - 5))
        screen.blit(surface, position.topleft)


class LyricsDisplay:
    def __init__(self, min_font_size=60):
        # Set up font
        self.font = pygame.font.Font(None, min_font_size)
        self.min_font_size = min_font_size

    def word_color(self, word, time_stamp):
        """Karaoke fill: sung words behind the playhead, the one being sung picked out."""
        start, end = word.get("start"), word.get("end")
        if start is None or end is None:
            return FONT_COLOR_CURRENT
        if time_stamp > end:
            return FONT_COLOR_WORD_SUNG
        if time_stamp >= start:
            return FONT_COLOR_WORD_ACTIVE
        return FONT_COLOR_CURRENT

    def wrap_words(self, words, max_width):
        """Pack timed words into rows that fit, keeping them as words rather than text."""
        rows, row = [], []
        for word in words:
            candidate = row + [word]
            text = " ".join(entry.get("word", "") for entry in candidate)
            if row and self.measure_width(text) > max_width:
                rows.append(row)
                row = [word]
            else:
                row = candidate
        if row:
            rows.append(row)
        return rows

    def render_highlighted_row(self, row, time_stamp):
        """One row of the current line, each word coloured by where the playhead is."""
        space = self.measure_width(" ")
        surfaces = [self.font.render(word.get("word", ""), True, self.word_color(word, time_stamp)) for word in row]
        width = sum(surface.get_width() for surface in surfaces) + space * max(0, len(surfaces) - 1)
        height = max((surface.get_height() for surface in surfaces), default=self.font.get_height())

        strip = pygame.Surface((max(1, width), height), pygame.SRCALPHA)
        offset = 0
        for surface in surfaces:
            strip.blit(surface, (offset, 0))
            offset += surface.get_width() + space

        return strip

    def update_and_print(self, screen, current_line, past_lines, next_lines, current_words=None, time_stamp=None):
        WIDTH, HEIGHT = screen.get_size()
        display_lines = []
        max_width = WIDTH - 10

        highlighting = bool(current_words) and time_stamp is not None

        sections = (
            ("past", past_lines, FONT_COLOR_PAST),
            ("current", [] if highlighting else ([current_line] if current_line else []), FONT_COLOR_CURRENT),
            ("next", next_lines, FONT_COLOR_NEXT),
        )

        for line_type, lines, color in sections:
            for line in lines:
                for sub_line in self.split_line_to_fit_in_screen(screen, line):
                    display_lines.append(
                        {
                            "text": sub_line,
                            "type": line_type,
                            "surface": self.font.render(sub_line, True, color),
                        }
                    )

        if highlighting:
            rows = self.wrap_words(current_words, max_width)
            highlighted = [
                {
                    "text": " ".join(word.get("word", "") for word in row),
                    "type": "current",
                    "surface": self.render_highlighted_row(row, time_stamp),
                }
                for row in rows
            ]
            # Slot the current line back between the past and next lines
            insert_at = sum(1 for entry in display_lines if entry["type"] == "past")
            display_lines[insert_at:insert_at] = highlighted

        if not display_lines:
            return

        # Display the current text at a fixed position, then the following lines
        current_y_pos = HEIGHT // 3
        first_next_line = True
        for entry in display_lines:
            if entry["type"] == "current":
                text_rect = entry["surface"].get_rect(center=(WIDTH // 2, current_y_pos))
                current_y_pos += entry["surface"].get_height() * 1.1
                # Draw the text on the screen
                screen.blit(entry["surface"], text_rect.topleft)

            elif current_y_pos < HEIGHT and entry["type"] != "past":
                if first_next_line:
                    current_y_pos += entry["surface"].get_height() * 0.9
                    first_next_line = False
                text_rect = entry["surface"].get_rect(center=(WIDTH // 2, current_y_pos))
                current_y_pos += entry["surface"].get_height() * 1.1
                # Draw the text on the screen
                screen.blit(entry["surface"], text_rect.topleft)

        # display past lines, going up from just above the current line
        current_y_pos = HEIGHT // 3 - (self.font.get_height() * 2)
        for entry in reversed(display_lines):
            if current_y_pos > -10 and entry["type"] == "past":
                text_rect = entry["surface"].get_rect(center=(WIDTH // 2, current_y_pos))
                current_y_pos -= entry["surface"].get_height() * 1.1
                # Draw the text on the screen
                screen.blit(entry["surface"], text_rect.topleft)

    def split_line_to_fit_in_screen(self, screen, line):
        """Split a lyric line into sub-lines that fit the window width.

        Punctuation breaks are tried first because they read better, then the line is
        word wrapped as a fallback. Always terminates.
        """
        if not line:
            return []

        max_width = screen.get_width() - 10
        if self.measure_width(line) <= max_width:
            return [line]

        # Try punctuation aware splits, bounded by the number of words in the line
        max_sub_lines = max(2, len(line.split()))
        for nb_sub_lines in range(2, max_sub_lines + 1):
            display_lines = split_into_sub_sentences(line, nb_sub_lines)
            if display_lines and all(self.measure_width(sub) <= max_width for sub in display_lines):
                return display_lines

        # Fallback: greedy word wrap, breaking words that are too wide on their own
        return wrap_to_width(line, self.measure_width, max_width)

    def measure_width(self, text):
        # font.size avoids allocating a surface just to measure
        return self.font.size(text)[0]


def rectangle_cs(center_pos_x, center_pos_y, width, height):
    # Calculate the left and top positions
    left = center_pos_x - width // 2
    top = center_pos_y - height // 2
    # Create a rectangle using pygame.Rect
    return pygame.Rect(left, top, width, height)
