"""Run Crossnote without blocking Qt's event loop."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import threading
from PySide6.QtCore import QObject, QTimer, Qt, Signal

SUPPORT = Path(__file__).resolve().parent / 'markview-files'


def _version_key(path):
    version_part = next((part for part in reversed(path.parts) if part.startswith('v')), '')
    parts = re.findall(r'\d+', version_part)
    return tuple(int(n) for n in parts) if parts else (0,)


def node_executable():
    if sys.platform == 'win32':
        executable = shutil.which('node.exe')
        if executable:
            return executable
        which_any = shutil.which('node')
        if which_any and Path(which_any).suffix.lower() in {'.exe', '.com'}:
            return which_any
        bases = [
            os.environ.get('ProgramFiles', r'C:\Program Files'),
            os.environ.get('ProgramW6432', ''),
            os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'),
            os.environ.get('NVM_SYMLINK', ''),
        ]
        if os.environ.get('LOCALAPPDATA'):
            bases.append(str(Path(os.environ['LOCALAPPDATA']) / 'Programs'))
        if os.environ.get('USERPROFILE'):
            bases.append(str(Path(os.environ['USERPROFILE']) / 'scoop' / 'apps' / 'nodejs' / 'current'))
        for base in bases:
            if not base:
                continue
            for candidate in (Path(base) / 'nodejs' / 'node.exe', Path(base) / 'node.exe'):
                if candidate.is_file():
                    return str(candidate)
        nvm_dirs = [os.environ.get('NVM_HOME', '')]
        if os.environ.get('APPDATA'):
            nvm_dirs.append(str(Path(os.environ['APPDATA']) / 'nvm'))
        for nvm_dir in nvm_dirs:
            if nvm_dir:
                found = sorted(Path(nvm_dir).glob('v*/node.exe'), key=_version_key)
                if found:
                    return str(found[-1])
        if os.environ.get('LOCALAPPDATA'):
            volta = sorted((Path(os.environ['LOCALAPPDATA']) / 'Volta/tools/image/node').glob('*/node.exe'),
                           key=lambda p: tuple(int(n) for n in re.findall(r'\d+', p.parent.name) or ['0']))
            if volta:
                return str(volta[-1])
        if which_any:
            return which_any
        raise RuntimeError('Node.js is required for enhanced preview. Install it from https://nodejs.org/')

    executable = shutil.which('node')
    if executable:
        return executable
    nvm = sorted((Path.home() / '.nvm/versions/node').glob('v*/bin/node'), key=_version_key)
    if nvm:
        return str(nvm[-1])
    for direct in (
        Path('/opt/homebrew/bin/node'),
        Path('/usr/local/bin/node'),
        Path('/usr/bin/node'),
        Path.home() / '.volta/bin/node',
    ):
        if direct.is_file() and os.access(direct, os.X_OK):
            return str(direct)
    for fnm_root in (Path.home() / '.local/share/fnm/node-versions', Path.home() / '.fnm/node-versions'):
        found = sorted(fnm_root.glob('v*/installation/bin/node'), key=_version_key)
        if found:
            return str(found[-1])
    if sys.platform == 'darwin':
        raise RuntimeError('Node.js is required for enhanced preview. Install it with: brew install node')
    raise RuntimeError('Node.js is required for enhanced preview. Install it with: sudo dnf install nodejs (or from https://nodejs.org/)')


class Renderer(QObject):
    rendered = Signal(str)
    failed = Signal(str)
    _completed = Signal(int, int, bytes, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self._timeout)
        self._completed.connect(self._finished, Qt.ConnectionType.QueuedConnection)
        self.lock = threading.Lock()
        self.process = None
        self.generation = 0
        self.active = False

    def render(self, source, filename, theme='dark', font_family='', font_size=None):
        self.cancel()
        try:
            node = node_executable()
        except RuntimeError as error:
            self.failed.emit(str(error))
            return
        payload = json.dumps({
            'markdown': source,
            'filename': str(filename),
            'theme': theme,
            'fontFamily': font_family or '',
            'fontSize': font_size,
        }).encode('utf-8')
        with self.lock:
            self.generation += 1
            gen = self.generation
            self.active = True
        self.timeout.start(30000)
        threading.Thread(target=self._run, args=(gen, node, payload), daemon=True).start()

    def _emit_done(self, gen, code, out, err_text):
        try:
            self._completed.emit(gen, code, out, err_text)
        except RuntimeError:
            pass

    @staticmethod
    def _close_streams(proc):
        for stream in (getattr(proc, 'stdin', None), getattr(proc, 'stdout', None), getattr(proc, 'stderr', None)):
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass

    @staticmethod
    def _terminate(proc, close_streams=False):
        try:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=1)
        except (OSError, subprocess.TimeoutExpired):
            pass
        if close_streams:
            Renderer._close_streams(proc)

    def _run(self, gen, node, payload):
        kwargs = {}
        if sys.platform == 'win32':
            kwargs['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
        try:
            proc = subprocess.Popen(
                [node, str(SUPPORT / 'render.cjs')],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                **kwargs,
            )
        except OSError as error:
            self._emit_done(gen, -1, b'', str(error))
            return
        with self.lock:
            if not self.active or gen != self.generation:
                self._terminate(proc, close_streams=True)
                return
            self.process = proc
        try:
            out, err = proc.communicate(payload)
            code = proc.returncode
        except (OSError, ValueError) as error:
            self._emit_done(gen, -1, b'', str(error))
            return
        finally:
            with self.lock:
                if self.process is proc:
                    self.process = None
            self._close_streams(proc)
        self._emit_done(gen, code, out, err.decode('utf-8', errors='replace').strip())

    def _timeout(self):
        if self.active:
            self.cancel()
            self.failed.emit('Rendering exceeded 30 seconds. Check imported files and diagrams, then toggle Preview to retry.')

    def _finished(self, gen, code, out, err_text):
        with self.lock:
            if not self.active or gen != self.generation:
                return
            self.active = False
        self.timeout.stop()
        try:
            if not out and err_text:
                raise ValueError(err_text)
            result = json.loads(out)
            if code or result.get('error'):
                raise ValueError(result.get('error', err_text or 'Renderer exited unexpectedly'))
            self.rendered.emit(result['html'])
        except (ValueError, KeyError) as error:
            self.failed.emit(str(error) if out else (err_text or str(error)))

    def cancel(self):
        self.timeout.stop()
        with self.lock:
            self.active = False
            self.generation += 1
            proc = self.process
            self.process = None
        if proc is not None:
            self._terminate(proc)
