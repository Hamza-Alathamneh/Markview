"""Run Crossnote without blocking Qt's event loop."""
import json
from pathlib import Path
import shutil
from PySide6.QtCore import QObject, QProcess, QTimer, Signal

SUPPORT = Path(__file__).resolve().parent / 'markview-files'


def node_executable():
    executable = shutil.which('node')
    if executable:
        return executable
    candidates = sorted((Path.home() / '.nvm/versions/node').glob('v*/bin/node'),
                        key=lambda p: tuple(int(n) for n in p.parts[-3][1:].split('.')))
    if candidates:
        return str(candidates[-1])
    raise RuntimeError('Node.js is required for enhanced preview. Install it with: sudo dnf install nodejs')


class Renderer(QObject):
    rendered = Signal(str)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self._timeout)
        self.process.started.connect(self._send_source)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._process_error)
        self.active = False
        self.payload = b''

    def render(self, source, filename, theme='dark'):
        self.cancel()
        try:
            node = node_executable()
        except RuntimeError as error:
            self.failed.emit(str(error))
            return
        self.process.setProgram(node)
        self.process.setArguments([str(SUPPORT / 'render.cjs')])
        self.payload = json.dumps({'markdown': source, 'filename': str(filename), 'theme': theme}).encode()
        self.active = True
        self.timeout.start(30000)
        self.process.start()

    def _send_source(self):
        if self.active:
            self.process.write(self.payload)
            self.process.closeWriteChannel()

    def _process_error(self, error):
        if self.active and error == QProcess.ProcessError.FailedToStart:
            self.active = False
            self.timeout.stop()
            self.failed.emit(self.process.errorString())

    def _timeout(self):
        if self.active:
            self.cancel()
            self.failed.emit('Rendering exceeded 30 seconds. Check imported files and diagrams, then toggle Preview to retry.')

    def _finished(self, code, status):
        self.timeout.stop()
        if not self.active:
            return
        self.active = False
        try:
            result = json.loads(bytes(self.process.readAllStandardOutput()))
            if code or result.get('error'):
                raise ValueError(result.get('error', 'Renderer exited unexpectedly'))
            self.rendered.emit(result['html'])
        except (ValueError, KeyError) as error:
            self.failed.emit(str(error))

    def cancel(self):
        self.active = False
        self.timeout.stop()
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.kill()
            self.process.waitForFinished(1000)
