#!/usr/bin/env bash
set -euo pipefail

PURGE=0
for arg in "$@"; do
  case "$arg" in
    --purge) PURGE=1 ;;
    *)
      echo "Error: unknown option: $arg" >&2
      exit 1
      ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
APP_DIR="$BIN_DIR/markview-app"
DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}"
APPLICATIONS_DIR="$DATA_DIR/applications"
ICONS_DIR="$DATA_DIR/icons"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/Markview"

rm -f "$BIN_DIR/markview"
rm -f "$ICONS_DIR/markview.png"
rm -f "$APPLICATIONS_DIR/markview.desktop"

DESKTOP_DIR=""
if command -v xdg-user-dir >/dev/null 2>&1; then
  DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
fi
if [ -z "$DESKTOP_DIR" ] && [ -d "$HOME/Desktop" ]; then
  DESKTOP_DIR="$HOME/Desktop"
fi
if [ -n "$DESKTOP_DIR" ] && [ "$DESKTOP_DIR" != "$HOME" ] && [ -d "$DESKTOP_DIR" ]; then
  rm -f "$DESKTOP_DIR/markview.desktop"
fi

if [ -d "$APP_DIR" ]; then
  APP_REAL="$(cd "$APP_DIR" && pwd -P)"
  case "$SCRIPT_DIR/" in
    "$APP_REAL/"*)
      rm -f "$APP_DIR/markview" \
            "$APP_DIR/markview_app.py" \
            "$APP_DIR/markview_complete.py" \
            "$APP_DIR/markview_preview.py" \
            "$APP_DIR/markview_renderer.py" \
            "$APP_DIR/markview_settings.py" \
            "$APP_DIR/markview_spell.py" \
            "$APP_DIR/markview_theme.py"
      rm -rf "$APP_DIR/.venv" "$APP_DIR/__pycache__" \
             "$APP_DIR/markview-files/vendor" \
             "$APP_DIR/markview-files/render.cjs" \
             "$APP_DIR/markview-files/en_words.txt.gz" \
             "$APP_DIR/markview-files/icon.png"
      ;;
    *)
      rm -rf "$APP_DIR"
      ;;
  esac
fi

if command -v update-desktop-database >/dev/null 2>&1 && [ -d "$APPLICATIONS_DIR" ]; then
  update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
fi

if [ "$PURGE" -eq 1 ]; then
  rm -rf "$CONFIG_DIR"
fi
