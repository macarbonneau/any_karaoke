from cProfile import label
import pygame
from any_karaoke.game_config import DEFAULT_FONT_COLOR, DEFAULT_OBJECT_COLOR


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
