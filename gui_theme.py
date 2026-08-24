"""
Shared dark theme for Migaku Enforcer's Tk windows.

Pulled out of MigakuStatusWindow/ReflectionDialog (migaku_enforcer.py) so the
onboarding wizard and Settings dialog match the existing look instead of each
re-declaring their own copies of the same hex codes.
"""

import tkinter as tk

# Core palette (matches MigakuStatusWindow)
BG = '#1a1a2e'
BG_PANEL = '#0d0d1a'
ACCENT = '#e94560'
ACCENT_HOVER = '#1e3a5f'
BUTTON_BG = '#16213e'
SEPARATOR = '#2d2d4e'
FG = 'white'
FG_MUTED = '#a8a8b3'
FG_DIM = '#6a6a8a'
FG_GOOD = '#00ff88'
FG_BAD = '#ff6b6b'

# Danger palette (matches ReflectionDialog)
BG_DANGER = '#2d0000'
BG_DANGER_PANEL = '#1a0000'
FG_DANGER = '#ff4444'

FONT_TITLE = ('Arial', 17, 'bold')
FONT_HEADING = ('Arial', 12, 'bold')
FONT_BODY = ('Arial', 10)
FONT_BODY_BOLD = ('Arial', 10, 'bold')
FONT_SMALL = ('Arial', 9)
FONT_SMALL_ITALIC = ('Arial', 9, 'italic')


def make_dark_button(parent, text, command, bg=BUTTON_BG, hover=ACCENT_HOVER, **kw):
    """Flat dark button matching MigakuStatusWindow's button style."""
    defaults = dict(
        fg='white', font=FONT_BODY, padx=12, pady=6,
        relief='flat', cursor='hand2',
        activebackground=hover, activeforeground='white',
    )
    defaults.update(kw)
    return tk.Button(parent, text=text, command=command, bg=bg, **defaults)


def make_separator(parent, color=SEPARATOR, height=1, pady=8):
    frame = tk.Frame(parent, bg=color, height=height)
    frame.pack(fill='x', pady=pady)
    return frame


def make_section_label(parent, text, bg=BG, fg=FG_MUTED):
    label = tk.Label(parent, text=text, font=FONT_BODY_BOLD, fg=fg, bg=bg)
    label.pack(anchor='w', pady=(6, 2))
    return label


def style_toplevel(win, title, bg=BG):
    win.title(title)
    win.configure(bg=bg)
