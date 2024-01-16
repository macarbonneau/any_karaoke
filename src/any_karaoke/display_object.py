from cProfile import label
import pygame
from any_karaoke.game_config import (
    DEFAULT_FONT_COLOR,
    DEFAULT_OBJECT_COLOR,
    FONT_COLOR_PAST,
    FONT_COLOR_CURRENT,
    FONT_COLOR_NEXT,
)
from any_karaoke.text_utils import split_into_sub_sentences


class Announce:
    def __init__(self, font_size=200, color=DEFAULT_FONT_COLOR):
        self.color = color
        # Set up font
        self.font = pygame.font.Font(None, font_size)
        self.font_size = font_size

    def update_and_print(self, screen, text, color=None):
        if text:
            WIDTH, HEIGHT = screen.get_size()

            if not color:
                text_surface = self.font.render(text, True, self.color)
            else:
                text_surface = self.font.render(text, True, color)

            scale_factor = WIDTH * 0.9 / text_surface.get_width()

            # scale the text
            scaled_text = pygame.transform.scale(
                text_surface,
                (
                    text_surface.get_width() * scale_factor,
                    text_surface.get_height() * scale_factor,
                ),
            )

            # Get the rectangle and set initial position
            text_rect = scaled_text.get_rect(center=(WIDTH // 2, HEIGHT // 2))
            # Draw the text on the screen
            screen.blit(scaled_text, text_rect.topleft)


class VolumeSlider:
    def __init__(self, label_txt, x, y, color=DEFAULT_OBJECT_COLOR, slider_value=50):
        self.label = label_txt
        self.x = x
        self.y = y
        self.color = color
        self.slider_rect = pygame.Rect(50, 150, 300, 20)
        self.slider_value = slider_value
        self.font = pygame.font.Font(None, 100)

    def update_and_print(self, screen):
        pygame.draw.rect(
            screen,
            DEFAULT_OBJECT_COLOR,
            (
                self.slider_rect.x
                + self.slider_value * self.slider_rect.width / 100
                - 2,
                self.slider_rect.y - 5,
                4,
                30,
            ),
        )

        label = self.font.render(
            f"Music Volume: {int(self.slider_value)}%", True, DEFAULT_OBJECT_COLOR
        )

        screen.blit(label, (400, 150))

    def set_volume(self, mouse_x, mouse_y):
        if self.slider_rect.collidepoint(mouse_x, mouse_y):
            self.slider_value = max(
                0,
                min(100, (mouse_x - self.slider_rect.x) / self.slider_rect.width * 100),
            )

        return self.slider_value / 100


class LyricsDisplay:
    def __init__(self, min_font_size=60, nb_lines_before=2, nb_lines_after=1):
        # Set up font
        self.font = pygame.font.Font(None, min_font_size)
        self.min_font_size = min_font_size

    def update_and_print(self, screen, current_line, past_lines, next_lines):
        WIDTH, HEIGHT = screen.get_size()
        display_lines = []

        for i in past_lines:
            lines = self.split_line_to_fit_in_screen(screen, i)
            for j in lines:
                display_lines.append(
                    {
                        "text": j,
                        "type": "past",
                        "rect": self.font.render(j, True, FONT_COLOR_PAST),
                    }
                )

        lines = self.split_line_to_fit_in_screen(screen, current_line)
        for j in lines:
            display_lines.append(
                {
                    "text": j,
                    "type": "current",
                    "rect": self.font.render(j, True, FONT_COLOR_CURRENT),
                }
            )

        for i in next_lines:
            lines = self.split_line_to_fit_in_screen(screen, i)
            for j in lines:
                display_lines.append(
                    {
                        "text": j,
                        "type": "next",
                        "rect": self.font.render(j, True, FONT_COLOR_NEXT),
                    }
                )

        # Display the current text at a fixed position, then the following lines
        current_y_pos = HEIGHT // 3
        first_next_line = True
        for i in display_lines:
            if i["type"] == "current":
                text_rect = i["rect"].get_rect(center=(WIDTH // 2, current_y_pos))
                current_y_pos += i["rect"].get_height() * 1.1
                # Draw the text on the screen
                screen.blit(i["rect"], text_rect.topleft)

            elif current_y_pos < HEIGHT and i["type"] != "past":
                if first_next_line:
                    current_y_pos += i["rect"].get_height() * 0.9
                    first_next_line = False
                text_rect = i["rect"].get_rect(center=(WIDTH // 2, current_y_pos))
                current_y_pos += i["rect"].get_height() * 1.1
                # Draw the text on the screen
                screen.blit(i["rect"], text_rect.topleft)

        # display past lines
        current_y_pos = HEIGHT // 3 - (display_lines[0]["rect"].get_height() * 2)
        for i in reversed(display_lines):
            if current_y_pos > -10 and i["type"] == "past":
                text_rect = i["rect"].get_rect(center=(WIDTH // 2, current_y_pos))
                current_y_pos -= i["rect"].get_height() * 1.1
                # Draw the text on the screen
                screen.blit(i["rect"], text_rect.topleft)

    def split_line_to_fit_in_screen(self, screen, line):
        WIDTH, HEIGHT = screen.get_size()
        display_lines = [line]

        # check each line if they fit in the window

        does_not_fit = True
        nb_sub_line_necessary = 1
        while does_not_fit:
            for l in display_lines:
                text_surface = self.font.render(l, True, DEFAULT_FONT_COLOR)
                if text_surface.get_width() > WIDTH - 10:
                    does_not_fit = True
                    break
            else:
                does_not_fit = False
                return display_lines
            nb_sub_line_necessary += 1
            display_lines = split_into_sub_sentences(line, nb_sub_line_necessary)
