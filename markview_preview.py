"""Asynchronous Crossnote rendering in an embedded Qt WebEngine preview."""
import html
import json
from pathlib import Path
import tempfile

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QColor
from PySide6.QtWebEngineCore import (
    QWebEnginePage, QWebEngineProfile, QWebEngineSettings,
    QWebEngineUrlRequestInfo, QWebEngineUrlRequestInterceptor,
)
from PySide6.QtWebEngineWidgets import QWebEngineView

from markview_renderer import Renderer
from markview_theme import THEMES


class LocalResources(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        scheme = info.requestUrl().scheme()
        if scheme in {'file', 'data', 'about', 'blob', 'qrc'}:
            return
        if scheme in {'http', 'https'} and info.resourceType() in {
            QWebEngineUrlRequestInfo.ResourceType.ResourceTypeImage,
            QWebEngineUrlRequestInfo.ResourceType.ResourceTypeMedia,
        }:
            return
        info.block(True)


class PreviewPage(QWebEnginePage):
    linkClicked = Signal(QUrl)

    def acceptNavigationRequest(self, url, kind, is_main_frame):
        if kind == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            if url.toString().split('#')[0] == self.url().toString().split('#')[0]:
                return True
            self.linkClicked.emit(url)
            return False
        return True


class EnhancedPreview(QWebEngineView):
    anchorClicked = Signal(QUrl)
    renderStatus = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAccessibleName('Markdown Preview Enhanced')
        self.theme = 'dark'
        self.font_family = ''
        self.font_size = 12
        self.profile = QWebEngineProfile(self)
        self.interceptor = LocalResources(self.profile)
        self.profile.setUrlRequestInterceptor(self.interceptor)
        page = PreviewPage(self.profile, self)
        self.setPage(page)
        page.linkClicked.connect(self.anchorClicked)
        page.setBackgroundColor(QColor('#0d1117'))
        settings = page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.AutoLoadImages, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, False)
        self.renderer = Renderer(self)
        self.renderer.rendered.connect(self._rendered)
        self.renderer.failed.connect(self.show_error)
        self.temporary = tempfile.TemporaryDirectory(prefix='markview-preview-', ignore_cleanup_errors=True)
        self.generation = 0
        self.scroll_y = 0
        self.base = QUrl()
        self.output_html = ''
        self.loadFinished.connect(self._loaded)

    def show_markdown(self, source, filename, scroll=0):
        self.cancel()
        self.generation += 1
        self.scroll_y = scroll
        self.base = QUrl.fromLocalFile(Path(filename).parent.as_posix().rstrip('/') + '/')
        self.renderStatus.emit('Rendering enhanced preview…')
        self.setHtml(self.message_page('Rendering preview…'))
        self.renderer.render(source, filename, self.theme, self.font_family, self.font_size)

    def set_theme(self, theme):
        self.theme = theme
        self.page().setBackgroundColor(QColor(THEMES[theme]['web_base']))

    def set_font(self, family, size):
        self.font_family = family or ''
        self.font_size = int(size) if size else 12

    def message_page(self, content):
        c = THEMES[self.theme]
        return (f'<body style="background:{c["web_base"]};color:{c["web_text"]};'
                f'font:16px sans-serif;padding:32px">{content}</body>')

    def _rendered(self, markup):
        try:
            self.output_html = markup
            target = Path(self.temporary.name) / f'preview-{self.generation}.html'
            target.write_text(self.output_html, encoding='utf-8')
            self.load(QUrl.fromLocalFile(str(target)))
            for older in Path(self.temporary.name).glob('preview-*.html'):
                if int(older.stem.split('-')[-1]) < self.generation - 1:
                    older.unlink(missing_ok=True)
        except (ValueError, OSError) as error:
            self.show_error(str(error))

    def _loaded(self, ok):
        if ok and self.url().isLocalFile():
            self.page().runJavaScript(f'window.scrollTo(0, {int(self.scroll_y)})')
            self.renderStatus.emit('Enhanced preview · Crossnote · Ctrl+E: edit Markdown')

    def show_error(self, message):
        self.renderStatus.emit('Preview could not be rendered')
        self.setHtml(self.message_page('<h2>Preview could not be rendered</h2><p>' + html.escape(message) + '</p>'))

    def capture_scroll(self):
        self.scroll_y = self.page().scrollPosition().y()
        return self.scroll_y

    def find_text(self, text, backwards=False):
        flags = QWebEnginePage.FindFlag.FindBackward if backwards else QWebEnginePage.FindFlag(0)
        self.findText(text, flags)

    def scroll_to_anchor(self, anchor):
        self.page().runJavaScript(
            f'document.getElementById({json.dumps(anchor)})?.scrollIntoView()')

    def cancel(self):
        self.renderer.cancel()

    def shutdown(self):
        self.cancel()
        self.stop()
        self.temporary.cleanup()
