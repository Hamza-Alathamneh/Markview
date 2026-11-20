"""Shared colors and persisted appearance for Markview."""
from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor, QPalette


THEMES = {
    'dark': {
        'window': '#171e27', 'base': '#1b2430', 'text': '#e1e7ef',
        'button': '#283440', 'border': '#3a4656', 'hover': '#354457',
        'accent': '#8edbcc', 'accent_text': '#142723', 'muted': '#9cabbf',
        'placeholder': '#8191a5', 'selection': '#366e68',
        'checked': '#b7a7e8', 'checked_text': '#211a35',
        'code': '#e6be7a', 'quote': '#acbfe6',
        'web_base': '#24292e', 'web_text': '#cccccc',
    },
    'light': {
        'window': '#f3f5f8', 'base': '#ffffff', 'text': '#202b3a',
        'button': '#e7ecf2', 'border': '#c4ceda', 'hover': '#d9e3ed',
        'accent': '#176c60', 'accent_text': '#ffffff', 'muted': '#526175',
        'placeholder': '#6b7789', 'selection': '#287d71',
        'checked': '#7155ad', 'checked_text': '#ffffff',
        'code': '#875206', 'quote': '#435c8c',
        'web_base': '#ffffff', 'web_text': '#333333',
    },
}


def appearance_settings():
    return QSettings('Markview', 'Markview')


def saved_theme(settings=None):
    value = (settings if settings is not None else appearance_settings()).value('appearance/theme', 'dark')
    return value if value in THEMES else 'dark'


def apply_theme(app, theme):
    c = THEMES[theme]
    palette = QPalette()
    for role, color in {
        QPalette.ColorRole.Window: c['window'], QPalette.ColorRole.WindowText: c['text'],
        QPalette.ColorRole.Base: c['base'], QPalette.ColorRole.AlternateBase: c['button'],
        QPalette.ColorRole.Text: c['text'], QPalette.ColorRole.Button: c['button'],
        QPalette.ColorRole.ButtonText: c['text'], QPalette.ColorRole.Highlight: c['selection'],
        QPalette.ColorRole.HighlightedText: '#ffffff', QPalette.ColorRole.Link: c['accent'],
        QPalette.ColorRole.PlaceholderText: c['placeholder'],
        QPalette.ColorRole.ToolTipBase: c['button'], QPalette.ColorRole.ToolTipText: c['text'],
    }.items():
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet(f"""
        QPushButton {{ padding: 8px 12px; border: 1px solid {c['border']}; border-radius: 7px; }}
        QPushButton:hover {{ background: {c['hover']}; }}
        QPushButton:focus {{ border-color: {c['accent']}; }}
        QPushButton#toggle {{ background: {c['accent']}; color: {c['accent_text']}; font-weight: bold; min-width: 110px; }}
        QPushButton#toggle:checked {{ background: {c['checked']}; color: {c['checked_text']}; }}
        QLabel#brand {{ font-size: 21px; font-weight: bold; color: {c['accent']}; }}
        QLabel#filename, QLabel#status {{ color: {c['muted']}; }}
        QPlainTextEdit, QTextBrowser {{ border: 1px solid {c['border']}; border-radius: 10px; padding: 8px; }}
        QLineEdit {{ padding: 8px; border: 1px solid {c['border']}; border-radius: 6px; }}
        QToolTip {{ color: {c['text']}; background: {c['button']}; border: 1px solid {c['border']}; }}
    """)
