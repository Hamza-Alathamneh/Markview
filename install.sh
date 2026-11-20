#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
APP_DIR="$BIN_DIR/markview-app"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
APPLICATIONS_DIR="$DATA_DIR/applications"
ICONS_DIR="$DATA_DIR/icons"
ICON_FILE="$ICONS_DIR/markview.png"
BIN_LINK="$BIN_DIR/markview"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 is required." >&2
  exit 1
fi

mkdir -p "$APP_DIR/markview-files" "$APPLICATIONS_DIR" "$ICONS_DIR"

cp "$SCRIPT_DIR/markview" "$APP_DIR/markview"
cp "$SCRIPT_DIR/markview_app.py" "$APP_DIR/markview_app.py"
cp "$SCRIPT_DIR/markview_preview.py" "$APP_DIR/markview_preview.py"
cp "$SCRIPT_DIR/markview_renderer.py" "$APP_DIR/markview_renderer.py"
cp "$SCRIPT_DIR/markview_theme.py" "$APP_DIR/markview_theme.py"
cp "$SCRIPT_DIR/markview-files/render.cjs" "$APP_DIR/markview-files/render.cjs"
cp "$SCRIPT_DIR/markview-files/icon.png" "$APP_DIR/markview-files/icon.png"
chmod 644 "$APP_DIR/markview-files/icon.png"

rm -rf "$APP_DIR/markview-files/vendor"
cp -a "$SCRIPT_DIR/markview-files/vendor" "$APP_DIR/markview-files/vendor"

PYTHON_SHEBANG="#!/usr/bin/env python3"
if ! python3 -c "import PySide6.QtWebEngineWidgets" >/dev/null 2>&1; then
  python3 -m venv "$APP_DIR/.venv"
  "$APP_DIR/.venv/bin/pip" install --upgrade pip
  "$APP_DIR/.venv/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"
  PYTHON_SHEBANG="#!$APP_DIR/.venv/bin/python3"
fi

python3 - "$APP_DIR/markview" "$PYTHON_SHEBANG" <<'EOF'
import pathlib
import sys

target = pathlib.Path(sys.argv[1])
lines = target.read_text(encoding="utf-8").splitlines(keepends=True)
lines[0] = sys.argv[2] + "\n"
target.write_text("".join(lines), encoding="utf-8")
EOF
chmod 755 "$APP_DIR/markview"

ln -sfn "markview-app/markview" "$BIN_LINK"

cp "$SCRIPT_DIR/markview-files/icon.png" "$ICON_FILE"
chmod 644 "$ICON_FILE"

DESKTOP_FILE="$APPLICATIONS_DIR/markview.desktop"
python3 - "$SCRIPT_DIR/markview-files/markview.desktop" "$DESKTOP_FILE" "$BIN_LINK" "$ICON_FILE" <<'EOF'
import pathlib
import sys

src = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
out = []
exec_bin, icon_path = sys.argv[3], sys.argv[4]
for line in src:
    if line.startswith("Exec="):
        out.append(f"Exec={exec_bin} %f")
    elif line.startswith("TryExec="):
        out.append(f"TryExec={exec_bin}")
    elif line.startswith("Icon="):
        out.append(f"Icon={icon_path}")
    else:
        out.append(line)
pathlib.Path(sys.argv[2]).write_text("\n".join(out) + "\n", encoding="utf-8")
EOF
chmod 644 "$DESKTOP_FILE"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
fi

DESKTOP_DIR=""
if command -v xdg-user-dir >/dev/null 2>&1; then
  DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
fi
if [ -z "$DESKTOP_DIR" ] && [ -d "$HOME/Desktop" ]; then
  DESKTOP_DIR="$HOME/Desktop"
fi
if [ -n "$DESKTOP_DIR" ] && [ "$DESKTOP_DIR" != "$HOME" ] && [ -d "$DESKTOP_DIR" ]; then
  cp "$DESKTOP_FILE" "$DESKTOP_DIR/markview.desktop"
  chmod 755 "$DESKTOP_DIR/markview.desktop"
fi
