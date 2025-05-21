"""Custom styles for the GUI application."""

import tkinter as tk
from tkinter import ttk

# Brand Colors - More modern, professional palette
COLORS = {
    'primary': '#7000FF',       # Rich purple (primary brand color)
    'primary_dark': '#5200BD',  # Darker purple for hover/active states
    'primary_light': '#9E56FF', # Lighter purple for accents
    'accent': '#00D9C0',        # Teal accent color for contrast and highlights
    'accent_alt': '#FF4D8F',    # Pink for secondary accent and warnings
    'bg_dark': '#121212',       # Nearly black for main background
    'bg_medium': '#1E1E1E',     # Slightly lighter black for secondary backgrounds
    'bg_light': '#2A2A2A',      # Dark gray for tertiary backgrounds / cards
    'text_primary': '#FFFFFF',  # White text for high contrast
    'text_secondary': '#B0B0B0',# Light gray for secondary text
    'text_disabled': '#707070', # Mid gray for disabled text
    'border': '#333333',        # Dark gray for subtle borders
    'success': '#4CD964',       # Green for success states
    'warning': '#FFC107',       # Amber for warning states
    'error': '#FF3B30',         # Red for error states
    'separator': '#383838'      # Gray for dividers
}

# Status Colors for GUI
STATUS_COLORS = {
    'sdk_loaded': '#87CEEB',    # Sky Blue
    'sdk_initialized': '#1E90FF',# Dodger Blue
    'connecting': '#FFC107',    # Amber
    'connected': '#4CD964',     # Green
    'disconnected': '#FF9500',  # Orange
    'disconnected_error': '#FF3B30', # Red
    'shutdown': '#808080'       # Gray
}

# Font configurations - More consistent type scale
FONTS = {
    'display': ('SF Pro Display', 36, 'bold'),  # For major headers
    'headline': ('SF Pro Text', 24, 'bold'),    # For section headers
    'title': ('SF Pro Text', 18, 'bold'),       # For subsection headers
    'subtitle': ('SF Pro Text', 16),            # For emphasized text
    'body': ('SF Pro Text', 14),                # Main text
    'caption': ('SF Pro Text', 12),             # Smaller text
    'button': ('SF Pro Text', 14, 'bold')       # Button text
}

# Custom styles for ttk widgets with glass morphism effects
STYLE_CONFIG = {
    'TFrame': {
        'configure': {
            'background': COLORS['bg_dark']
        }
    },
    'Card.TFrame': {
        'configure': {
            'background': COLORS['bg_light'],
            'borderwidth': 1,
            'relief': 'solid'
        }
    },
    'TLabelframe': {
        'configure': {
            'background': COLORS['bg_medium'],
            'foreground': COLORS['text_primary'],
            'padding': 15,
            'borderwidth': 1,
            'relief': 'solid'
        }
    },
    'Card.TLabelframe': {
        'configure': {
            'background': COLORS['bg_light'],
            'foreground': COLORS['primary'],
            'padding': 15,
            'borderwidth': 1,
            'relief': 'solid'
        }
    },
    'TLabelframe.Label': {
        'configure': {
            'background': COLORS['bg_medium'],
            'foreground': COLORS['text_primary'],
            'font': FONTS['title']
        }
    },
    'Card.TLabelframe.Label': {
        'configure': {
            'background': COLORS['bg_light'],
            'foreground': COLORS['text_primary'],
            'font': FONTS['title']
        }
    },
    'TLabel': {
        'configure': {
            'background': COLORS['bg_medium'],
            'foreground': COLORS['text_primary'],
            'font': FONTS['body'],
            'padding': 5
        }
    },
    'Title.TLabel': {
        'configure': {
            'background': COLORS['bg_medium'],
            'foreground': COLORS['primary'],
            'font': FONTS['headline'],
            'padding': 5
        }
    },
    'Status.TLabel': {
        'configure': {
            'background': COLORS['bg_medium'],
            'foreground': COLORS['text_secondary'],
            'font': FONTS['caption'],
            'padding': 5
        }
    },
    'Info.TLabel': {
        'configure': {
            'background': COLORS['bg_medium'],
            'foreground': COLORS['primary'],
            'font': FONTS['subtitle'],
            'padding': 5
        }
    },
    'Error.TLabel': {
        'configure': {
            'background': COLORS['bg_medium'],
            'foreground': COLORS['error'],
            'font': FONTS['caption'],
            'padding': 5
        }
    },
    'Stats.TLabel': {
        'configure': {
            'background': COLORS['bg_medium'],
            'foreground': COLORS['accent'],
            'font': ('SF Pro Text', 14, 'bold'),
            'padding': 5
        }
    },
    'StatusIcon.TLabel': {
        'configure': {
            'background': COLORS['bg_medium'],
            'font': ('Arial', 16, 'bold'),
            'padding': (0, 0, 0, 0)
        }
    },
    'TButton': {
        'configure': {
            'font': FONTS['button'],
            'background': COLORS['primary'],
            'foreground': COLORS['text_primary'],
            'padding': [15, 8],
            'relief': 'flat',
            'borderwidth': 0
        },
        'map': {
            'background': [('active', COLORS['primary_dark']), ('disabled', COLORS['bg_light'])],
            'foreground': [('disabled', COLORS['text_disabled'])]
        }
    },
    'Accent.TButton': {
        'configure': {
            'font': FONTS['button'],
            'background': COLORS['accent'],
            'foreground': COLORS['bg_dark'],
            'padding': [15, 8],
            'relief': 'flat',
            'borderwidth': 0
        },
        'map': {
            'background': [('active', COLORS['accent_alt']), ('disabled', COLORS['bg_light'])],
            'foreground': [('disabled', COLORS['text_disabled'])]
        }
    },
    'Danger.TButton': {
        'configure': {
            'font': FONTS['button'],
            'background': COLORS['error'],
            'foreground': COLORS['text_primary'],
            'padding': [15, 8],
            'relief': 'flat',
            'borderwidth': 0
        },
        'map': {
            'background': [('active', '#CC2E26'), ('disabled', COLORS['bg_light'])],
            'foreground': [('disabled', COLORS['text_disabled'])]
        }
    }
}

def create_gradient_frame(parent, bg_color=COLORS['bg_dark'], highlight_color=COLORS['primary']):
    """Create a frame with a subtle gradient border effect."""
    frame = tk.Frame(
        parent,
        background=bg_color,
        highlightbackground=highlight_color,
        highlightcolor=COLORS['primary_light'],
        highlightthickness=1,
        bd=0
    )
    return frame

def setup_styles(root):
    """Initializes and applies all custom ttk styles."""
    style = ttk.Style(root)
    
    # Set theme to 'clam' for better styling control
    style.theme_use('clam')
    
    # Apply base styles
    for widget, config in STYLE_CONFIG.items():
        style.configure(widget, **config.get('configure', {}))
        if 'map' in config:
            style.map(widget, **config['map'])

    # Configure specific elements
    style.configure("Vertical.TScrollbar",
                    background=COLORS['primary_dark'],
                    troughcolor=COLORS['bg_dark'],
                    bordercolor=COLORS['primary'],
                    arrowcolor=COLORS['text_primary'])
    style.map("Vertical.TScrollbar",
              background=[('active', COLORS['primary'])])

    # Configure horizontal separator
    style.configure("TSeparator", 
                   background=COLORS['separator'])
