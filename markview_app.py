"""A native Markdown editor with embedded Crossnote preview for Qt 6 / Wayland."""
import argparse
import codecs
import os
from pathlib import Path
import re
import sys

from PySide6.QtCore import QIODevice, QSaveFile, Qt, QUrl
from PySide6.QtGui import (
    QAction, QColor, QDesktopServices, QFont, QFontDatabase, QIcon, QKeySequence,
    QSyntaxHighlighter, QTextCharFormat, QTextDocument,
)
from markview_theme import THEMES, appearance_settings, apply_theme, saved_theme
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPlainTextEdit, QPushButton, QStackedWidget, QTextBrowser,
    QVBoxLayout, QWidget,
)


class MarkdownHighlighter(QSyntaxHighlighter):
    theme = 'dark'

    def highlightBlock(self, text):
        if text.lstrip().startswith(("```", "~~~")):
            self.setCurrentBlockState(0 if self.previousBlockState() == 1 else 1)
            self.paint(0, len(text), "#e6be7a")
            return
        if self.previousBlockState() == 1:
            self.setCurrentBlockState(1)
            self.paint(0, len(text), "#e6be7a")
            return
        self.setCurrentBlockState(0)
        for pattern, color, bold in [
            (r"^#{1,6}\s+.*", "#8edbcc", True),
            (r"^\s*(?:[-*+] |\d+\. |>).*", "#acbfe6", False),
            (r"\*\*.+?\*\*|__.+?__", "#f1d3a1", True),
            (r"`[^`]+`", "#e6be7a", False),
            (r"!?\[[^\]]*\]\([^)]*\)", "#9fc4fa", False),
            (r"</?[^>]+>", "#b2a1df", False),
        ]:
            for match in re.finditer(pattern, text):
                self.paint(match.start(), len(match.group()), color, bold)

    def paint(self, start, length, color, bold=False):
        if self.theme == 'light':
            color = {'#e6be7a': '#875206', '#8edbcc': '#176c60', '#acbfe6': '#435c8c',
                     '#f1d3a1': '#82500c', '#9fc4fa': '#145ab6', '#b2a1df': '#7952a3'}.get(color, color)
        style = QTextCharFormat()
        style.setForeground(QColor(color))
        if bold:
            style.setFontWeight(QFont.Weight.Bold)
        self.setFormat(start, length, style)


class MarkdownWindow(QMainWindow):
    def __init__(self, enhanced=True, settings=None):
        super().__init__()
        self.enhanced = enhanced
        self.settings = settings if settings is not None else appearance_settings()
        self.theme = saved_theme(self.settings)
        self.path = None
        self.original_bytes = b""
        self.newline = "\n"
        self.bom = False
        self.preview_scroll = 0
        self.resize(1000, 760)
        self.setMinimumSize(600, 420)
        self.setAcceptDrops(True)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 16, 20, 12)
        layout.setSpacing(14)
        toolbar = QHBoxLayout()
        brand = QLabel("Markview")
        brand.setObjectName("brand")
        toolbar.addWidget(brand)
        toolbar.addSpacing(18)
        self.add_button(toolbar, "New", "Ctrl+N", self.new_file)
        self.add_button(toolbar, "Open…", "Ctrl+O", self.open_dialog)
        self.add_button(toolbar, "Save", "Ctrl+S", self.save_file)
        self.add_button(toolbar, "Save as…", "Ctrl+Shift+S", lambda: self.save_file(True))
        toolbar.addStretch()
        self.toggle = QPushButton("Preview")
        self.toggle.setObjectName("toggle")
        self.toggle.setCheckable(True)
        self.toggle.setToolTip("Switch between Markdown source and preview (Ctrl+E)")
        self.toggle.toggled.connect(self.set_preview)
        toolbar.addWidget(self.toggle)
        self.shortcut("Ctrl+E", self.toggle.click)
        self.shortcut("Ctrl+Q", self.close)
        layout.addLayout(toolbar)

        self.filename = QLabel()
        self.filename.setObjectName("filename")
        self.filename.setTextFormat(Qt.TextFormat.PlainText)
        details = QHBoxLayout()
        details.addWidget(self.filename, 1)
        self.theme_button = QPushButton()
        self.theme_button.setObjectName('themeSwitch')
        self.theme_button.setToolTip('Switch light / dark appearance (Ctrl+Shift+L)')
        self.theme_button.clicked.connect(self.toggle_theme)
        self.shortcut('Ctrl+Shift+L', self.toggle_theme)
        details.addWidget(self.theme_button)
        layout.addLayout(details)

        self.search_row = QWidget()
        search_layout = QHBoxLayout(self.search_row)
        search_layout.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find in this document…")
        self.search.returnPressed.connect(self.find_next)
        search_layout.addWidget(self.search)
        self.add_button(search_layout, "Previous", "Shift+F3", lambda: self.find_next(True))
        self.add_button(search_layout, "Next", "F3", self.find_next)
        close_search = QPushButton("×")
        close_search.setAccessibleName("Close search")
        close_search.clicked.connect(self.search_row.hide)
        search_layout.addWidget(close_search)
        self.search_row.hide()
        layout.addWidget(self.search_row)
        self.shortcut("Ctrl+F", self.show_search)
        self.shortcut("Escape", self.search_row.hide)

        self.editor = QPlainTextEdit()
        self.editor.setAcceptDrops(False)
        self.editor.setAccessibleName("Markdown source")
        self.editor.setPlaceholderText("# Your next idea\n\nWrite Markdown here, then click Preview.")
        mono = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        mono.setPointSize(12)
        self.editor.setFont(mono)
        self.editor.setTabStopDistance(self.editor.fontMetrics().horizontalAdvance(" ") * 4)
        self.editor.document().setDocumentMargin(24)
        self.highlighter = MarkdownHighlighter(self.editor.document())
        if enhanced:
            from markview_preview import EnhancedPreview
            self.preview = EnhancedPreview()
        else:
            self.preview = QTextBrowser()
            self.preview.setOpenLinks(False)
            self.preview.setAccessibleName("Rendered Markdown preview")
            self.preview.setFont(QFont("sans-serif", 12))
            self.preview.document().setDocumentMargin(32)
        self.preview.setAcceptDrops(False)
        self.preview.anchorClicked.connect(self.open_link)
        self.pages = QStackedWidget()
        self.pages.addWidget(self.editor)
        self.pages.addWidget(self.preview)
        layout.addWidget(self.pages, 1)
        self.status = QLabel()
        self.status.setObjectName("status")
        if enhanced:
            self.preview.renderStatus.connect(self.status.setText)
        layout.addWidget(self.status)
        self.setCentralWidget(root)
        self.editor.textChanged.connect(self.update_info)
        self.editor.cursorPositionChanged.connect(self.update_info)
        self.editor.document().modificationChanged.connect(self.update_info)
        self.editor.document().setModified(False)
        self.refresh_theme()
        self.update_info()

    def toggle_theme(self):
        self.theme = 'light' if self.theme == 'dark' else 'dark'
        self.settings.setValue('appearance/theme', self.theme)
        self.settings.sync()
        self.refresh_theme()

    def refresh_theme(self):
        apply_theme(QApplication.instance(), self.theme)
        self.theme_button.setText('Light mode' if self.theme == 'dark' else 'Dark mode')
        modified = self.editor.document().isModified()
        self.highlighter.theme = self.theme
        self.highlighter.rehighlight()
        self.editor.document().setModified(modified)
        if self.enhanced:
            self.preview.set_theme(self.theme)
        else:
            c = THEMES[self.theme]
            self.preview.document().setDefaultStyleSheet(
                f"a {{ color: {c['accent']}; }} pre {{ background-color: {c['button']}; }} "
                f"code {{ color: {c['code']}; }} blockquote {{ color: {c['quote']}; }} "
                f"th {{ background-color: {c['button']}; }} td, th {{ padding: 8px; }}"
            )
        if self.toggle.isChecked():
            self.preview_scroll = (self.preview.capture_scroll() if self.enhanced
                                   else self.preview.verticalScrollBar().value())
            self.set_preview(True)

    def shortcut(self, sequence, callback):
        action = QAction(self)
        action.setShortcut(QKeySequence(sequence))
        action.triggered.connect(lambda checked=False: callback())
        self.addAction(action)

    def add_button(self, layout, label, shortcut, callback):
        button = QPushButton(label)
        button.setToolTip(f"{label} ({shortcut})")
        button.clicked.connect(lambda checked=False: callback())
        layout.addWidget(button)
        self.shortcut(shortcut, callback)

    def update_info(self, *_):
        modified = self.editor.document().isModified()
        name = self.path.name if self.path else "Untitled.md"
        self.setWindowTitle(f"{'● ' if modified else ''}{name} — Markview")
        self.filename.setText(f"{name}   /   {'Unsaved changes' if modified else 'Markdown'}")
        self.filename.setToolTip(str(self.path) if self.path else "New document")
        cursor = self.editor.textCursor()
        mode = ("ENHANCED PREVIEW" if self.enhanced else "PREVIEW") if self.toggle.isChecked() else "WRITE"
        self.status.setText(
            f"{mode}   ·   {len(self.editor.toPlainText().split()):,} words"
            f"   ·   Ln {cursor.blockNumber() + 1}, Col {cursor.positionInBlock() + 1}"
            "   ·   UTF-8   ·   Ctrl+E: switch view"
        )

    def set_preview(self, enabled):
        if enabled:
            base = self.path.parent if self.path else Path.cwd()
            if self.enhanced:
                self.preview.show_markdown(self.editor.toPlainText(),
                                           self.path or base / 'Untitled.md', self.preview_scroll)
            else:
                self.preview.document().setBaseUrl(QUrl.fromLocalFile(str(base) + os.sep))
                self.preview.setMarkdown(self.editor.toPlainText())
            self.pages.setCurrentWidget(self.preview)
            if not self.enhanced:
                self.preview.verticalScrollBar().setValue(self.preview_scroll)
            self.preview.setFocus()
        else:
            if self.enhanced:
                self.preview_scroll = self.preview.capture_scroll()
                self.preview.cancel()
            else:
                self.preview_scroll = self.preview.verticalScrollBar().value()
            self.pages.setCurrentWidget(self.editor)
            self.editor.setFocus()
        self.toggle.setText("Edit Markdown" if enabled else "Preview")
        self.update_info()

    def confirm_discard(self):
        if not self.editor.document().isModified():
            return True
        result = QMessageBox.warning(
            self, "Save changes?", "Save your changes before leaving this document?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Save,
        )
        if result == QMessageBox.StandardButton.Save:
            return self.save_file()
        return result == QMessageBox.StandardButton.Discard

    def new_file(self):
        if not self.confirm_discard():
            return
        self.path, self.original_bytes, self.newline, self.bom = None, b"", "\n", False
        self.editor.setPlainText("")
        self.editor.document().setModified(False)
        self.preview_scroll = 0
        self.toggle.setChecked(False)
        self.preview_scroll = 0
        self.update_info()

    def open_dialog(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Open Markdown", str(self.path.parent if self.path else Path.home()),
            "Markdown (*.md *.markdown *.mdown *.mkd);;Text files (*.txt);;All files (*)",
        )
        if filename:
            self.load_file(filename)

    def load_file(self, filename):
        try:
            path = Path(filename).expanduser().resolve()
            data = path.read_bytes()
            content = data.decode("utf-8-sig")
        except (OSError, UnicodeError) as error:
            QMessageBox.critical(self, "Cannot open file", f"Could not read this UTF-8 file:\n{error}")
            return False
        if not self.confirm_discard():
            return False
        self.path, self.original_bytes = path, data
        self.bom = data.startswith(codecs.BOM_UTF8)
        self.newline = "\r\n" if b"\r\n" in data else ("\r" if b"\r" in data else "\n")
        self.editor.setPlainText(content.replace("\r\n", "\n").replace("\r", "\n"))
        self.editor.document().setModified(False)
        self.preview_scroll = 0
        self.set_preview(self.toggle.isChecked())
        return True

    def save_file(self, save_as=False):
        target = self.path
        if target is None or save_as:
            filename, _ = QFileDialog.getSaveFileName(
                self, "Save Markdown", str(target or Path.home() / "Untitled.md"),
                "Markdown (*.md);;All files (*)",
            )
            if not filename:
                return False
            target = Path(filename).expanduser().resolve()
        if target == self.path:
            try:
                changed = target.read_bytes() != self.original_bytes
            except FileNotFoundError:
                changed = True
            except OSError as error:
                QMessageBox.critical(self, "Cannot check file", str(error))
                return False
            if changed:
                answer = QMessageBox.warning(
                    self, "File changed on disk",
                    "This file was changed or removed outside Markview. Overwrite it with your version?",
                    QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if answer != QMessageBox.StandardButton.Save:
                    return False

        data = self.original_bytes
        if self.editor.document().isModified():
            data = self.editor.toPlainText().replace("\n", self.newline).encode("utf-8")
            if self.bom:
                data = codecs.BOM_UTF8 + data
        output = QSaveFile(str(target))
        if not output.open(QIODevice.OpenModeFlag.WriteOnly):
            QMessageBox.critical(self, "Cannot save file", output.errorString())
            return False
        if output.write(data) != len(data):
            output.cancelWriting()
            QMessageBox.critical(self, "Cannot save file", output.errorString())
            return False
        if not output.commit():
            QMessageBox.critical(self, "Cannot save file", output.errorString())
            return False
        self.path, self.original_bytes = target, data
        self.editor.document().setModified(False)
        if self.toggle.isChecked():
            self.set_preview(True)
        self.update_info()
        return True

    def show_search(self):
        self.search_row.show()
        self.search.setFocus()
        self.search.selectAll()

    def find_next(self, backwards=False):
        text = self.search.text()
        if not text:
            self.show_search()
            return
        widget = self.pages.currentWidget()
        if self.enhanced and widget is self.preview:
            self.preview.find_text(text, backwards)
            return
        flags = QTextDocument.FindFlag.FindBackward if backwards else QTextDocument.FindFlag(0)
        original = widget.textCursor()
        if not widget.find(text, flags):
            cursor = widget.textCursor()
            cursor.movePosition(cursor.MoveOperation.End if backwards else cursor.MoveOperation.Start)
            widget.setTextCursor(cursor)
            if not widget.find(text, flags):
                widget.setTextCursor(original)
                self.status.setText(f'No match for “{text}”')

    def open_link(self, url):
        if self.enhanced and url.hasFragment():

            without_fragment = QUrl(url)
            without_fragment.setFragment("")
            if not url.path() or without_fragment == self.preview.base or (
                self.path and without_fragment == QUrl.fromLocalFile(str(self.path))
            ):
                self.preview.scroll_to_anchor(url.fragment())
                return
        if url.isRelative() and not url.path() and url.hasFragment():
            self.preview.scrollToAnchor(url.fragment())
            return
        base = self.preview.base if self.enhanced else self.preview.document().baseUrl()
        resolved = base.resolved(url)
        if resolved.isLocalFile() and Path(resolved.toLocalFile()).suffix.lower() in {".md", ".markdown", ".mkd", ".mdown"}:
            self.load_file(resolved.toLocalFile())
        elif resolved.scheme() in {"https", "http", "mailto"}:
            QDesktopServices.openUrl(resolved)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and len(event.mimeData().urls()) == 1 and event.mimeData().urls()[0].isLocalFile():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if len(urls) == 1 and urls[0].isLocalFile() and self.load_file(urls[0].toLocalFile()):
            event.acceptProposedAction()

    def closeEvent(self, event):
        if self.confirm_discard():
            if self.enhanced:
                self.preview.shutdown()
            event.accept()
        else:
            event.ignore()


def configure_app(app):
    app.setApplicationName("Markview")
    app.setDesktopFileName("markview")
    icon_path = Path(__file__).resolve().parent / "markview-files" / "icon.png"
    if icon_path.is_file():
        app.setWindowIcon(QIcon(str(icon_path)))
    app.setStyle("Fusion")
    app.setFont(QFont("sans-serif", 11))
    apply_theme(app, saved_theme())


def main():
    parser = argparse.ArgumentParser(description="Markview — native Markdown editor and preview")
    parser.add_argument("file", nargs="?", help="Markdown file to open")
    parser.add_argument("--preview", action="store_true", help="Start in rendered preview mode")
    parser.add_argument("--basic", action="store_true", help="Use the lightweight Qt preview without enhanced syntax")
    args = parser.parse_args()
    if not args.basic:
        try:
            import markview_preview
        except ImportError as error:
            parser.exit(1, f"Enhanced preview needs Qt WebEngine: {error}\nInstall: sudo dnf install python3-pyside6 qt6-qtwebengine\nOr launch with --basic.\n")
    app = QApplication([sys.argv[0]])
    configure_app(app)
    window = MarkdownWindow(enhanced=not args.basic)
    if args.file:
        window.load_file(args.file)
    window.toggle.setChecked(args.preview)
    window.show()
    return app.exec()
