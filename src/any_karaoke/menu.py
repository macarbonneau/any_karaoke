"""Auto-hiding menu bar drawn directly in pygame.

The bar reveals itself when the mouse enters the top strip of the window and hides again
as soon as it leaves, unless a dropdown is open.

Each MenuItem owns both its action and its keyboard shortcut, so MenuBar.handle_event
dispatches clicks and key presses from the same definition. The shortcut printed next to
an item is therefore always the one that actually works.
"""

import pygame

from any_karaoke.game_config import (
    MENU_BACK_COLOR,
    MENU_BAR_HEIGHT,
    MENU_BORDER_COLOR,
    MENU_DISABLED_COLOR,
    MENU_FONT_SIZE,
    MENU_HOVER_COLOR,
    MENU_PANEL_COLOR,
    MENU_SHORTCUT_COLOR,
    MENU_TEXT_COLOR,
)

TITLE_PADDING = 16
ITEM_HEIGHT = 30
ITEM_PADDING = 14
SHORTCUT_GAP = 40
MARKER_WIDTH = 18

# Modifiers that must be absent when an item declares no modifier
EXCLUSIVE_MODS = pygame.KMOD_CTRL | pygame.KMOD_ALT


class MenuItem:
    def __init__(self, label, action, key=None, mods=0, shortcut_text="", checked=None, enabled=None):
        # label may be a callable for rows whose text changes, such as the live offset
        self.label = label
        self.action = action
        self.key = key
        self.mods = mods
        self.shortcut_text = shortcut_text
        # Optional callables evaluated at draw time
        self.checked = checked
        self.enabled = enabled

    def label_text(self):
        return self.label() if callable(self.label) else self.label

    def is_enabled(self):
        return True if self.enabled is None else bool(self.enabled())

    def is_checked(self):
        return None if self.checked is None else bool(self.checked())

    def matches(self, event):
        """True when a KEYDOWN event is this item's shortcut."""
        if self.key is None or self.action is None or event.key != self.key:
            return False

        if self.mods:
            return bool(event.mod & self.mods)

        # A bare shortcut must not fire while Ctrl or Alt is held
        return not event.mod & EXCLUSIVE_MODS

    def trigger(self):
        if self.action is not None and self.is_enabled():
            self.action()
            return True
        return False


class Menu:
    def __init__(self, title, items):
        self.title = title
        self.items = items


class MenuBar:
    def __init__(self, menus, height=MENU_BAR_HEIGHT, font_size=MENU_FONT_SIZE):
        self.menus = menus
        self.height = height
        self.font = pygame.font.Font(None, font_size)
        self.open_index = None
        self.hover_item = None
        # Recomputed on every draw and hit test
        self._title_rects = []
        self._panel_rect = None
        self._item_rects = []

    # ================================================
    # Geometry
    # ================================================
    def _layout_titles(self):
        rects = []
        x = 0
        for menu in self.menus:
            width = self.font.size(menu.title)[0] + TITLE_PADDING * 2
            rects.append(pygame.Rect(x, 0, width, self.height))
            x += width
        self._title_rects = rects
        return rects

    def _layout_panel(self, index):
        """Rect of the open dropdown and of each of its items."""
        menu = self.menus[index]
        title_rect = self._title_rects[index]

        widest = 0
        for item in menu.items:
            width = MARKER_WIDTH + self.font.size(item.label_text())[0]
            if item.shortcut_text:
                width += SHORTCUT_GAP + self.font.size(item.shortcut_text)[0]
            widest = max(widest, width)

        panel_width = widest + ITEM_PADDING * 2
        panel_height = ITEM_HEIGHT * len(menu.items) + 8
        panel = pygame.Rect(title_rect.left, self.height, panel_width, panel_height)

        item_rects = [
            pygame.Rect(panel.left, panel.top + 4 + i * ITEM_HEIGHT, panel_width, ITEM_HEIGHT)
            for i in range(len(menu.items))
        ]
        return panel, item_rects

    def bar_rect(self, screen_width):
        return pygame.Rect(0, 0, screen_width, self.height)

    # ================================================
    # State
    # ================================================
    def is_open(self):
        return self.open_index is not None

    def is_visible(self, mouse_pos, screen_width):
        """Shown while the mouse is in the top strip, or over an open dropdown."""
        if self.bar_rect(screen_width).collidepoint(mouse_pos):
            return True
        if self.is_open() and self._panel_rect and self._panel_rect.collidepoint(mouse_pos):
            return True
        return False

    def close(self):
        self.open_index = None
        self.hover_item = None
        self._panel_rect = None
        self._item_rects = []

    def title_at(self, position):
        for index, rect in enumerate(self._title_rects):
            if rect.collidepoint(position):
                return index
        return None

    def item_at(self, position):
        for index, rect in enumerate(self._item_rects):
            if rect.collidepoint(position):
                return index
        return None

    # ================================================
    # Events
    # ================================================
    def handle_event(self, event, screen_width=None):
        """Returns True when the menu consumed the event."""
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE and self.is_open():
                self.close()
                return True
            for menu in self.menus:
                for item in menu.items:
                    if item.matches(event):
                        return item.trigger()
            return False

        if event.type == pygame.MOUSEMOTION:
            self._layout_titles()
            if self.is_open():
                # Sliding across the bar switches menus, as a desktop menu would
                over_title = self.title_at(event.pos)
                if over_title is not None and over_title != self.open_index:
                    self.open_index = over_title
                    self._panel_rect, self._item_rects = self._layout_panel(over_title)
                self.hover_item = self.item_at(event.pos)
            return False

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._layout_titles()

            title = self.title_at(event.pos)
            if title is not None:
                self.open_index = None if title == self.open_index else title
                if self.is_open():
                    self._panel_rect, self._item_rects = self._layout_panel(title)
                else:
                    self.close()
                return True

            if self.is_open():
                index = self.item_at(event.pos)
                if index is not None:
                    item = self.menus[self.open_index].items[index]
                    self.close()
                    item.trigger()
                    return True
                self.close()
                # A click inside the bar strip should not fall through to the sliders
                return screen_width is not None and self.bar_rect(screen_width).collidepoint(event.pos)

        return False

    # ================================================
    # Drawing
    # ================================================
    def update_and_print(self, screen):
        mouse_pos = pygame.mouse.get_pos()
        width = screen.get_width()

        if not self.is_visible(mouse_pos, width) and not self.is_open():
            self.close()
            return

        self._layout_titles()
        self._draw_bar(screen, width, mouse_pos)

        if self.is_open():
            self._panel_rect, self._item_rects = self._layout_panel(self.open_index)
            self._draw_panel(screen, mouse_pos)

    def _draw_bar(self, screen, width, mouse_pos):
        bar = pygame.Surface((width, self.height), pygame.SRCALPHA)
        bar.fill(MENU_BACK_COLOR)
        screen.blit(bar, (0, 0))
        pygame.draw.line(screen, MENU_BORDER_COLOR, (0, self.height - 1), (width, self.height - 1))

        for index, (menu, rect) in enumerate(zip(self.menus, self._title_rects)):
            highlighted = index == self.open_index or (rect.collidepoint(mouse_pos) and not self.is_open())
            if highlighted:
                pygame.draw.rect(screen, MENU_HOVER_COLOR, rect)

            label = self.font.render(menu.title, True, MENU_TEXT_COLOR)
            screen.blit(label, label.get_rect(center=rect.center))

    def _draw_panel(self, screen, mouse_pos):
        panel = pygame.Surface(self._panel_rect.size, pygame.SRCALPHA)
        panel.fill(MENU_PANEL_COLOR)
        screen.blit(panel, self._panel_rect.topleft)
        pygame.draw.rect(screen, MENU_BORDER_COLOR, self._panel_rect, 1)

        for item, rect in zip(self.menus[self.open_index].items, self._item_rects):
            enabled = item.is_enabled()
            if enabled and rect.collidepoint(mouse_pos):
                pygame.draw.rect(screen, MENU_HOVER_COLOR, rect)

            color = MENU_TEXT_COLOR if enabled else MENU_DISABLED_COLOR

            checked = item.is_checked()
            if checked:
                marker = self.font.render("*", True, color)
                screen.blit(marker, (rect.left + ITEM_PADDING, rect.centery - marker.get_height() // 2))

            label = self.font.render(item.label_text(), True, color)
            screen.blit(
                label,
                (rect.left + ITEM_PADDING + MARKER_WIDTH, rect.centery - label.get_height() // 2),
            )

            if item.shortcut_text:
                shortcut_color = MENU_SHORTCUT_COLOR if enabled else MENU_DISABLED_COLOR
                shortcut = self.font.render(item.shortcut_text, True, shortcut_color)
                screen.blit(
                    shortcut,
                    (rect.right - ITEM_PADDING - shortcut.get_width(), rect.centery - shortcut.get_height() // 2),
                )
