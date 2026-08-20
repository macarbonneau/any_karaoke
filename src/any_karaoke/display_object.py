import pygame

from any_karaoke.game_config import (
    DEFAULT_FONT_COLOR,
    DEFAULT_OBJECT_COLOR,
    FONT_COLOR_PAST,
    FONT_COLOR_CURRENT,
    FONT_COLOR_NEXT,
)
from any_karaoke.text_utils import split_into_sub_sentences, wrap_to_width


class Announce:
    def __init__(self, font_size=200, color=DEFAULT_FONT_COLOR):
        self.color = color
        # Set up font
        self.font = pygame.font.Font(None, font_size)
        self.font_size = font_size

    def update_and_print(self, screen, text, color=None):
        if not text:
            return

        WIDTH, HEIGHT = screen.get_size()
        text_surface = self.font.render(text, True, color or self.color)

        if text_surface.get_width() <= 0:
            return

        scale_factor = WIDTH * 0.9 / text_surface.get_width()

        # scale the text
        scaled_text = pygame.transform.scale(
            text_surface,
            (
                int(text_surface.get_width() * scale_factor),
                int(text_surface.get_height() * scale_factor),
            ),
        )

        # Get the rectangle and set initial position
        text_rect = scaled_text.get_rect(center=(WIDTH // 2, HEIGHT // 2))
        # Draw the text on the screen
        screen.blit(scaled_text, text_rect.topleft)


class VolumeSlider:
    def __init__(self, label_txt, norm_x, norm_y, color=DEFAULT_OBJECT_COLOR, slider_value=50):
        self.label = label_txt
        self.norm_x = norm_x  # normalized position (0, 1)
        self.norm_y = norm_y
        self.color = color
        self.slider_value = slider_value
        self.font = pygame.font.Font(None, 50)
        # Empty until the slider has been drawn once, so it cannot catch stray clicks
        self.outline_rect = pygame.Rect(0, 0, 0, 0)

    @property
    def volume(self):
        """Slider position as a pygame mixer volume (0.0 - 1.0)."""
        return self.slider_value / 100.0

    def update_and_print(self, screen):
        WIDTH, HEIGHT = screen.get_size()
        slider_width = 0.1 * WIDTH
        slider_height = 0.66 * HEIGHT
        x = WIDTH * self.norm_x
        y = HEIGHT * self.norm_y

        # print the outline of the slider
        self.outline_rect = rectangle_cs(x, y, slider_width, slider_height)
        pygame.draw.rect(screen, self.color, self.outline_rect)

        # print the cursor
        y_cursor = y + slider_height // 2 - (self.slider_value / 100.0 * slider_height)
        cursor_rect = rectangle_cs(x, y_cursor, slider_width * 1.5, slider_height * 0.1)
        pygame.draw.rect(screen, self.color, cursor_rect)

        label = self.font.render(f"{self.label}: {int(self.slider_value)}%", True, self.color)

        screen.blit(label, (x - label.get_width() // 2, y - slider_height // 2 - slider_height * 0.1))

    def handle_drag(self, mouse_x, mouse_y):
        """Move the slider if the mouse is over it. Returns the new volume, or None if untouched."""
        if not self.outline_rect.collidepoint(mouse_x, mouse_y):
            return None

        slider_top = self.outline_rect.top
        val = 1 - ((mouse_y - slider_top) / self.outline_rect.height)
        self.slider_value = max(0, min(100, val * 100))

        return self.volume


class LyricsDisplay:
    def __init__(self, min_font_size=60):
        # Set up font
        self.font = pygame.font.Font(None, min_font_size)
        self.min_font_size = min_font_size

    def update_and_print(self, screen, current_line, past_lines, next_lines):
        WIDTH, HEIGHT = screen.get_size()
        display_lines = []

        sections = (
            ("past", past_lines, FONT_COLOR_PAST),
            ("current", [current_line] if current_line else [], FONT_COLOR_CURRENT),
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
