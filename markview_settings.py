"""Persisted preferences and Settings dialog for Markview."""
from dataclasses import dataclass

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QFrame, QGridLayout,
    QGroupBox, QHBoxLayout, QLabel, QPushButton, QRadioButton, QSpinBox,
    QVBoxLayout,
)

from markview_theme import THEMES

SPELLING_MODES = ('dropdown', 'right_click', 'off')

PREFERRED_MONO = (
    'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Cascadia Mono', 'Hack',
    'Source Code Pro', 'IBM Plex Mono', 'Adwaita Mono', 'Ubuntu Mono',
    'DejaVu Sans Mono', 'Liberation Mono', 'Consolas', 'Courier New',
)

PREFERRED_PREVIEW = (
    'Inter', 'Adwaita Sans', 'Cantarell', 'Segoe UI', 'Roboto', 'Noto Sans',
    'Source Sans 3', 'IBM Plex Sans', 'DejaVu Sans', 'Liberation Sans',
    'Georgia', 'Merriweather', 'Noto Serif', 'DejaVu Serif', 'JetBrains Mono',
)


@dataclass
class AppPreferences:
    suggestions_enabled: bool = True
    markdown_suggestions: bool = True
    word_suggestions: bool = True
    spelling_mode: str = 'dropdown'  # 'dropdown' | 'right_click' | 'off'
    auto_correct: bool = True
    editor_font_family: str = ''
    editor_font_size: int = 12
    preview_font_family: str = ''
    preview_font_size: int = 12


def _as_bool(value, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {'false', '0', 'no', ''}
    return bool(value)


def _as_int(value, default: int, low: int, high: int) -> int:
    try:
        num = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, num))


def load_preferences(settings: QSettings | None) -> AppPreferences:
    if settings is None:
        return AppPreferences()
    mode = str(settings.value('spelling/mode', 'dropdown') or 'dropdown')
    if mode not in SPELLING_MODES:
        mode = 'dropdown'
    return AppPreferences(
        suggestions_enabled=_as_bool(settings.value('completion/enabled', True), True),
        markdown_suggestions=_as_bool(settings.value('completion/markdown_rules', True), True),
        word_suggestions=_as_bool(settings.value('completion/english_words', True), True),
        spelling_mode=mode,
        auto_correct=_as_bool(settings.value('spelling/auto_correct', True), True),
        editor_font_family=str(settings.value('fonts/editor_family', '') or ''),
        editor_font_size=_as_int(settings.value('fonts/editor_size', 12), 12, 9, 28),
        preview_font_family=str(settings.value('fonts/preview_family', '') or ''),
        preview_font_size=_as_int(settings.value('fonts/preview_size', 12), 12, 9, 28),
    )


def save_preferences(settings: QSettings | None, prefs: AppPreferences):
    if settings is None:
        return
    settings.setValue('completion/enabled', prefs.suggestions_enabled)
    settings.setValue('completion/markdown_rules', prefs.markdown_suggestions)
    settings.setValue('completion/english_words', prefs.word_suggestions)
    settings.setValue('spelling/mode', prefs.spelling_mode)
    settings.setValue('spelling/auto_correct', prefs.auto_correct)
    settings.setValue('fonts/editor_family', prefs.editor_font_family)
    settings.setValue('fonts/editor_size', prefs.editor_font_size)
    settings.setValue('fonts/preview_family', prefs.preview_font_family)
    settings.setValue('fonts/preview_size', prefs.preview_font_size)
    settings.sync()


def resolve_editor_font(prefs: AppPreferences) -> QFont:
    if prefs.editor_font_family:
        font = QFont(prefs.editor_font_family, prefs.editor_font_size)
    else:
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        font.setPointSize(prefs.editor_font_size)
    return font


def resolve_preview_font(prefs: AppPreferences) -> QFont:
    return QFont(prefs.preview_font_family or 'sans-serif', prefs.preview_font_size)


def _installed_families():
    families = [f for f in QFontDatabase.families() if not f.startswith('.')]
    return families, set(families)


def list_editor_fonts() -> list[tuple[str, str]]:
    families, fam_set = _installed_families()
    result: list[tuple[str, str]] = [('System Monospace (Default)', '')]
    seen: set[str] = set()
    for name in PREFERRED_MONO:
        if name in fam_set and name not in seen:
            seen.add(name)
            result.append((name, name))
    for name in families:
        if name not in seen and QFontDatabase.isFixedPitch(name):
            seen.add(name)
            result.append((name, name))
    for name in families:
        if name not in seen:
            seen.add(name)
            result.append((name, name))
    return result


def list_preview_fonts() -> list[tuple[str, str]]:
    families, fam_set = _installed_families()
    result: list[tuple[str, str]] = [('System Default', '')]
    seen: set[str] = set()
    for name in PREFERRED_PREVIEW:
        if name in fam_set and name not in seen:
            seen.add(name)
            result.append((name, name))
    for name in families:
        if name not in seen:
            seen.add(name)
            result.append((name, name))
    return result


class SettingsDialog(QDialog):
    """Settings dialog for suggestions, spell-check mode, auto-correct, and fonts."""

    def __init__(self, prefs: AppPreferences, theme: str = 'dark', parent=None):
        super().__init__(parent)
        self.setWindowTitle('Markview Settings')
        self.setModal(True)
        self.setMinimumWidth(520)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(14)

        # 1. Auto-complete suggestions
        comp_box = QGroupBox('Auto-Complete Suggestions')
        comp_layout = QVBoxLayout(comp_box)
        comp_layout.setSpacing(8)
        self.cb_suggestions = QCheckBox('Enable suggestions dropdown while typing')
        self.cb_md_rules = QCheckBox('Markdown rules & syntax (code fences, diagrams, links, images, headings, callouts, LaTeX, /snippets)')
        self.cb_eng_words = QCheckBox('English & document words (next-word predictions, document terms, English dictionary)')
        self.cb_md_rules.setStyleSheet('margin-left: 20px;')
        self.cb_eng_words.setStyleSheet('margin-left: 20px;')
        comp_layout.addWidget(self.cb_suggestions)
        comp_layout.addWidget(self.cb_md_rules)
        comp_layout.addWidget(self.cb_eng_words)
        root.addWidget(comp_box)

        # 2. Spell check & auto-correct
        spell_box = QGroupBox('Spell Check & Auto-Correct')
        spell_layout = QVBoxLayout(spell_box)
        spell_layout.setSpacing(8)
        self.spell_group = QButtonGroup(self)
        self.rb_dropdown = QRadioButton('Dropdown list + red highlight + right-click suggestions')
        self.rb_right_click = QRadioButton('Red highlight + right-click only (no spelling dropdown while typing)')
        self.rb_off = QRadioButton('Off (no red highlights or spelling suggestions)')
        self.spell_group.addButton(self.rb_dropdown)
        self.spell_group.addButton(self.rb_right_click)
        self.spell_group.addButton(self.rb_off)
        self.cb_autocorrect = QCheckBox('Auto-correct clear typos automatically on Space / punctuation (Ctrl+Z reverts)')
        spell_layout.addWidget(self.rb_dropdown)
        spell_layout.addWidget(self.rb_right_click)
        spell_layout.addWidget(self.rb_off)
        spell_layout.addSpacing(4)
        spell_layout.addWidget(self.cb_autocorrect)
        root.addWidget(spell_box)

        # 3. Fonts
        font_box = QGroupBox('Fonts')
        font_grid = QGridLayout(font_box)
        font_grid.setSpacing(8)
        self.editor_font_combo = QComboBox()
        for label, value in list_editor_fonts():
            self.editor_font_combo.addItem(label, value)
        self.editor_size_spin = QSpinBox()
        self.editor_size_spin.setRange(9, 28)
        self.editor_size_spin.setSuffix(' pt')

        self.preview_font_combo = QComboBox()
        for label, value in list_preview_fonts():
            self.preview_font_combo.addItem(label, value)
        self.preview_size_spin = QSpinBox()
        self.preview_size_spin.setRange(9, 28)
        self.preview_size_spin.setSuffix(' pt')

        font_grid.addWidget(QLabel('Editor font:'), 0, 0)
        font_grid.addWidget(self.editor_font_combo, 0, 1)
        font_grid.addWidget(self.editor_size_spin, 0, 2)
        font_grid.addWidget(QLabel('Preview font:'), 1, 0)
        font_grid.addWidget(self.preview_font_combo, 1, 1)
        font_grid.addWidget(self.preview_size_spin, 1, 2)
        font_grid.setColumnStretch(1, 1)

        preview_frame = QFrame()
        preview_frame.setObjectName('fontPreviewFrame')
        pf_layout = QVBoxLayout(preview_frame)
        pf_layout.setContentsMargins(10, 8, 10, 8)
        pf_layout.setSpacing(4)
        self.editor_sample = QLabel('# Editor sample: **Markdown** `code` 0123')
        self.preview_sample = QLabel('Preview sample: The quick brown fox jumps over the lazy dog.')
        self.editor_sample.setWordWrap(True)
        self.preview_sample.setWordWrap(True)
        pf_layout.addWidget(self.editor_sample)
        pf_layout.addWidget(self.preview_sample)
        font_grid.addWidget(preview_frame, 2, 0, 1, 3)
        root.addWidget(font_box)

        # Buttons
        buttons = QHBoxLayout()
        self.reset_btn = QPushButton('Reset Defaults')
        self.cancel_btn = QPushButton('Cancel')
        self.save_btn = QPushButton('Save')
        self.save_btn.setObjectName('primaryButton')
        self.save_btn.setDefault(True)
        buttons.addWidget(self.reset_btn)
        buttons.addStretch()
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.save_btn)
        root.addLayout(buttons)

        # Signals
        self.cb_suggestions.toggled.connect(self._sync_enabled_states)
        self.rb_dropdown.toggled.connect(self._sync_enabled_states)
        self.rb_right_click.toggled.connect(self._sync_enabled_states)
        self.rb_off.toggled.connect(self._sync_enabled_states)
        self.editor_font_combo.currentIndexChanged.connect(self._update_font_samples)
        self.editor_size_spin.valueChanged.connect(self._update_font_samples)
        self.preview_font_combo.currentIndexChanged.connect(self._update_font_samples)
        self.preview_size_spin.valueChanged.connect(self._update_font_samples)
        self.reset_btn.clicked.connect(self._reset_defaults)
        self.cancel_btn.clicked.connect(self.reject)
        self.save_btn.clicked.connect(self.accept)

        self._apply_theme(theme)
        self._load_into_widgets(prefs)

    def _apply_theme(self, theme: str):
        c = THEMES[theme]
        self.setStyleSheet(f"""
            QDialog {{ background: {c['window']}; color: {c['text']}; }}
            QGroupBox {{
                font-weight: bold; color: {c['accent']};
                border: 1px solid {c['border']}; border-radius: 8px;
                margin-top: 10px; padding: 12px 10px 10px 10px;
            }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 6px; }}
            QCheckBox, QRadioButton, QLabel {{ color: {c['text']}; font-weight: normal; }}
            QComboBox, QSpinBox {{
                background: {c['base']}; color: {c['text']};
                border: 1px solid {c['border']}; border-radius: 6px; padding: 5px 8px;
            }}
            QFrame#fontPreviewFrame {{
                background: {c['base']}; border: 1px solid {c['border']}; border-radius: 6px;
            }}
            QPushButton#primaryButton {{
                background: {c['accent']}; color: {c['accent_text']}; font-weight: bold; min-width: 84px;
            }}
        """)

    def _select_combo_value(self, combo: QComboBox, value: str):
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        elif value:
            combo.addItem(value, value)
            combo.setCurrentIndex(combo.count() - 1)
        else:
            combo.setCurrentIndex(0)

    def _load_into_widgets(self, prefs: AppPreferences):
        self.cb_suggestions.setChecked(prefs.suggestions_enabled)
        self.cb_md_rules.setChecked(prefs.markdown_suggestions)
        self.cb_eng_words.setChecked(prefs.word_suggestions)
        if prefs.spelling_mode == 'right_click':
            self.rb_right_click.setChecked(True)
        elif prefs.spelling_mode == 'off':
            self.rb_off.setChecked(True)
        else:
            self.rb_dropdown.setChecked(True)
        self.cb_autocorrect.setChecked(prefs.auto_correct)
        self._select_combo_value(self.editor_font_combo, prefs.editor_font_family)
        self.editor_size_spin.setValue(prefs.editor_font_size)
        self._select_combo_value(self.preview_font_combo, prefs.preview_font_family)
        self.preview_size_spin.setValue(prefs.preview_font_size)
        self._sync_enabled_states()
        self._update_font_samples()

    def _sync_enabled_states(self):
        comp_on = self.cb_suggestions.isChecked()
        self.cb_md_rules.setEnabled(comp_on)
        self.cb_eng_words.setEnabled(comp_on)
        self.cb_autocorrect.setEnabled(not self.rb_off.isChecked())

    def _update_font_samples(self):
        prefs = self.preferences()
        self.editor_sample.setFont(resolve_editor_font(prefs))
        self.preview_sample.setFont(resolve_preview_font(prefs))

    def _reset_defaults(self):
        self._load_into_widgets(AppPreferences())

    def preferences(self) -> AppPreferences:
        if self.rb_right_click.isChecked():
            mode = 'right_click'
        elif self.rb_off.isChecked():
            mode = 'off'
        else:
            mode = 'dropdown'
        return AppPreferences(
            suggestions_enabled=self.cb_suggestions.isChecked(),
            markdown_suggestions=self.cb_md_rules.isChecked(),
            word_suggestions=self.cb_eng_words.isChecked(),
            spelling_mode=mode,
            auto_correct=self.cb_autocorrect.isChecked(),
            editor_font_family=str(self.editor_font_combo.currentData() or ''),
            editor_font_size=int(self.editor_size_spin.value()),
            preview_font_family=str(self.preview_font_combo.currentData() or ''),
            preview_font_size=int(self.preview_size_spin.value()),
        )
