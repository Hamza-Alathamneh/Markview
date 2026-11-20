$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$ScriptDir = $PSScriptRoot
$LocalAppData = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $HOME "AppData\Local" }
$InstallDir = Join-Path $LocalAppData "Markview"
$FilesDir = Join-Path $InstallDir "markview-files"
$BinDir = Join-Path $InstallDir "bin"
$VenvDir = Join-Path $InstallDir ".venv"

function Find-Python {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $candidates = @(
            @{ Cmd = "python"; Args = @() },
            @{ Cmd = "py"; Args = @("-3") },
            @{ Cmd = "python3"; Args = @() }
        )
        foreach ($item in $candidates) {
            if (-not (Get-Command $item.Cmd -ErrorAction SilentlyContinue)) {
                continue
            }
            & $item.Cmd @($item.Args) -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) {
                $pathOut = & $item.Cmd @($item.Args) -c "import sys; print(sys.executable)" 2>$null
                if ($LASTEXITCODE -eq 0 -and $pathOut) {
                    $trimmed = ($pathOut | Select-Object -First 1).Trim()
                    if ($trimmed -and (Test-Path $trimmed)) {
                        return $trimmed
                    }
                }
            }
        }
    } finally {
        $ErrorActionPreference = $prev
    }
    return $null
}

$PythonExe = Find-Python
if (-not $PythonExe) {
    [Console]::Error.WriteLine("Error: Python 3.10 or newer is required.")
    exit 1
}

New-Item -ItemType Directory -Force -Path $FilesDir, $BinDir | Out-Null

if ((Resolve-Path $ScriptDir).Path -ne (Resolve-Path $InstallDir).Path) {
    foreach ($name in @("markview_app.py", "markview_complete.py", "markview_preview.py", "markview_renderer.py", "markview_settings.py", "markview_spell.py", "markview_theme.py")) {
        Copy-Item -Force (Join-Path $ScriptDir $name) (Join-Path $InstallDir $name)
    }
    Copy-Item -Force (Join-Path $ScriptDir "markview-files\render.cjs") (Join-Path $FilesDir "render.cjs")
    Copy-Item -Force (Join-Path $ScriptDir "markview-files\en_words.txt.gz") (Join-Path $FilesDir "en_words.txt.gz")
    Copy-Item -Force (Join-Path $ScriptDir "markview-files\icon.png") (Join-Path $FilesDir "icon.png")

    $VendorDest = Join-Path $FilesDir "vendor"
    if (Test-Path $VendorDest) {
        Remove-Item -Recurse -Force $VendorDest
    }
    Copy-Item -Recurse -Force (Join-Path $ScriptDir "markview-files\vendor") $VendorDest
}

$RunPython = $PythonExe
$prev = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
    @'
import sys
try:
    import PySide6.QtWebEngineWidgets
except Exception:
    sys.exit(1)
'@ | & $PythonExe - 2>$null | Out-Null
    $HasWebEngine = ($LASTEXITCODE -eq 0)

    if (-not $HasWebEngine) {
        $VenvPython = Join-Path $VenvDir "Scripts\python.exe"
        if (-not (Test-Path $VenvPython)) {
            & $PythonExe -m venv $VenvDir | Out-Null
            if ($LASTEXITCODE -ne 0) {
                [Console]::Error.WriteLine("Error: Failed to create Python virtual environment.")
                exit 1
            }
        }
        $RunPython = $VenvPython
        & $RunPython -m pip install --disable-pip-version-check -q -r (Join-Path $ScriptDir "requirements.txt") | Out-Null
        if ($LASTEXITCODE -ne 0) {
            [Console]::Error.WriteLine("Error: Failed to install dependencies from requirements.txt.")
            exit 1
        }
    }
} finally {
    $ErrorActionPreference = $prev
}

$PythonDir = Split-Path -Parent $RunPython
$PythonW = Join-Path $PythonDir "pythonw.exe"
$GuiPython = if (Test-Path $PythonW) { $PythonW } else { $RunPython }

$IconPng = Join-Path $FilesDir "icon.png"
$IconIco = Join-Path $FilesDir "icon.ico"
$prev = $ErrorActionPreference
$ErrorActionPreference = "Continue"
try {
    @'
import pathlib, struct, sys
from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage, QPainter

src, dst = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
img = QImage(str(src))
if img.isNull():
    raise SystemExit(1)
canvas = QImage(256, 256, QImage.Format.Format_ARGB32)
canvas.fill(Qt.GlobalColor.transparent)
scaled = img.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
p = QPainter(canvas)
p.drawImage((256 - scaled.width()) // 2, (256 - scaled.height()) // 2, scaled)
p.end()
if not canvas.save(str(dst), "ICO"):
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    if not canvas.save(buf, "PNG"):
        raise SystemExit(1)
    png = bytes(buf.data())
    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png), 22)
    dst.write_bytes(header + entry + png)
'@ | & $RunPython - $IconPng $IconIco 2>$null | Out-Null
} finally {
    $ErrorActionPreference = $prev
}

$CmdPath = Join-Path $BinDir "markview.cmd"
$CmdContent = "@echo off`r`nchcp 65001 >nul`r`n`"$RunPython`" `"$InstallDir\markview_app.py`" %*`r`n"
[System.IO.File]::WriteAllText($CmdPath, $CmdContent, (New-Object System.Text.UTF8Encoding($false)))

$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
$PathEntries = if ($UserPath) { $UserPath -split ";" | Where-Object { $_ } } else { @() }
if (-not ($PathEntries | Where-Object { $_.TrimEnd("\") -ieq $BinDir.TrimEnd("\") })) {
    $NewPath = if ($UserPath) { "$UserPath;$BinDir" } else { $BinDir }
    [Environment]::SetEnvironmentVariable("Path", $NewPath, "User")
}

$WshShell = New-Object -ComObject WScript.Shell
$AppEntry = Join-Path $InstallDir "markview_app.py"
$WorkDir = [Environment]::GetFolderPath("UserProfile")
$IconLoc = if (Test-Path $IconIco) { "$IconIco,0" } else { "$GuiPython,0" }

$ShortcutTargets = @()
$DesktopDir = [Environment]::GetFolderPath("Desktop")
if ($DesktopDir -and (Test-Path $DesktopDir)) {
    $ShortcutTargets += (Join-Path $DesktopDir "Markview.lnk")
}
$ProgramsDir = [Environment]::GetFolderPath("Programs")
if ($ProgramsDir -and (Test-Path $ProgramsDir)) {
    $ShortcutTargets += (Join-Path $ProgramsDir "Markview.lnk")
}

foreach ($ShortcutPath in $ShortcutTargets) {
    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $GuiPython
    $Shortcut.Arguments = "`"$AppEntry`""
    $Shortcut.WorkingDirectory = $WorkDir
    $Shortcut.IconLocation = $IconLoc
    $Shortcut.Description = "Native Markdown editor and preview"
    $Shortcut.Save()
}
