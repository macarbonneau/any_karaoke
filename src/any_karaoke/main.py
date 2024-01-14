import pygame
import pygame.mixer
from pygame.locals import QUIT
import os
from tkinter import Tk, filedialog

# Initialize Pygame
pygame.init()

# Set up display
width, height = 800, 400
screen = pygame.display.set_mode((width, height))
pygame.display.set_caption("Sound Mixer")


# Load audio files
def load_audio():
    root = Tk()
    root.withdraw()  # Hide the main window

    file_path = filedialog.askopenfilename(filetypes=[("Audio Files", "*.mp3;*.wav")])

    if file_path:
        return file_path
    else:
        return None


file1_path = load_audio()
file2_path = load_audio()

if not file1_path or not file2_path:
    print("Please select both audio files.")
    pygame.quit()
    exit()

# Create mixer channels
pygame.mixer.init()
channel1 = pygame.mixer.Channel(0)
channel2 = pygame.mixer.Channel(1)

# Load audio files into mixer.Sound objects
file1 = pygame.mixer.Sound(file1_path)
file2 = pygame.mixer.Sound(file2_path)

# Set initial volumes
channel1.set_volume(0.5)
channel2.set_volume(0.5)

# Play the sounds
channel1.play(file1, loops=-1)
channel2.play(file2, loops=-1)

# Colors
white = (255, 255, 255)
black = (0, 0, 0)

# Fonts
font = pygame.font.Font(None, 36)

# Sliders
slider1_rect = pygame.Rect(50, 150, 300, 20)
slider2_rect = pygame.Rect(50, 250, 300, 20)

slider1_value = 50
slider2_value = 50

running = True
while running:
    for event in pygame.event.get():
        if event.type == QUIT:
            running = False

    # Get mouse position
    mouse_x, mouse_y = pygame.mouse.get_pos()

    # Check for slider interactions
    if pygame.mouse.get_pressed()[0]:
        if slider1_rect.collidepoint(mouse_x, mouse_y):
            slider1_value = max(
                0, min(100, (mouse_x - slider1_rect.x) / slider1_rect.width * 100)
            )
            channel1.set_volume(slider1_value / 100)
        elif slider2_rect.collidepoint(mouse_x, mouse_y):
            slider2_value = max(
                0, min(100, (mouse_x - slider2_rect.x) / slider2_rect.width * 100)
            )
            channel2.set_volume(slider2_value / 100)

    # Draw everything
    screen.fill(white)
    pygame.draw.rect(screen, black, slider1_rect)
    pygame.draw.rect(screen, black, slider2_rect)

    pygame.draw.rect(
        screen,
        black,
        (
            slider1_rect.x + slider1_value * slider1_rect.width / 100 - 2,
            slider1_rect.y - 5,
            4,
            30,
        ),
    )
    pygame.draw.rect(
        screen,
        black,
        (
            slider2_rect.x + slider2_value * slider2_rect.width / 100 - 2,
            slider2_rect.y - 5,
            4,
            30,
        ),
    )

    text1 = font.render(f"File 1 Volume: {int(slider1_value)}%", True, black)
    text2 = font.render(f"File 2 Volume: {int(slider2_value)}%", True, black)

    screen.blit(text1, (400, 150))
    screen.blit(text2, (400, 250))

    pygame.display.flip()

pygame.quit()
