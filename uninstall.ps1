param(
    [switch]$Purge
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$ScriptDir = (Resolve-Path $PSScriptRoot).Path.TrimEnd("\")
$LocalAppData = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $HOME "AppData\Local" }
$InstallDir = Join-Path $LocalAppData "Markview"
$BinDir = Join-Path $InstallDir "bin"

$DesktopDir = [Environment]::GetFolderPath("Desktop")
if ($DesktopDir) {
    $DesktopShortcut = Join-Path $DesktopDir "Markview.lnk"
    if (Test-Path $DesktopShortcut) {
        Remove-Item -Force $DesktopShortcut
    }
}

$ProgramsDir = [Environment]::GetFolderPath("Programs")
if ($ProgramsDir) {
    $StartShortcut = Join-Path $ProgramsDir "Markview.lnk"
    if (Test-Path $StartShortcut) {
        Remove-Item -Force $StartShortcut
    }
}

$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($UserPath) {
    $NormBin = $BinDir.TrimEnd("\")
    $Original = @($UserPath -split ";" | Where-Object { $_ })
    $Filtered = @($Original | Where-Object { $_.TrimEnd("\") -ine $NormBin })
    if ($Filtered.Count -ne $Original.Count) {
        [Environment]::SetEnvironmentVariable("Path", ($Filtered -join ";"), "User")
    }
}

if (Test-Path $InstallDir) {
    $InstallReal = (Resolve-Path $InstallDir).Path.TrimEnd("\")
    $InsideInstall = ($ScriptDir -ieq $InstallReal) -or ($ScriptDir.StartsWith("$InstallReal\", [System.StringComparison]::OrdinalIgnoreCase))
    if ($InsideInstall) {
        foreach ($name in @("markview_app.py", "markview_complete.py", "markview_preview.py", "markview_renderer.py", "markview_settings.py", "markview_spell.py", "markview_theme.py")) {
            $p = Join-Path $InstallDir $name
            if (Test-Path $p) { Remove-Item -Force $p }
        }
        foreach ($sub in @(".venv", "__pycache__", "bin", "markview-files\vendor", "markview-files\render.cjs", "markview-files\en_words.txt.gz", "markview-files\icon.png", "markview-files\icon.ico")) {
            $p = Join-Path $InstallDir $sub
            if (Test-Path $p) { Remove-Item -Recurse -Force $p }
        }
    } else {
        Remove-Item -Recurse -Force $InstallDir
    }
}

if ($Purge -and (Test-Path "HKCU:\Software\Markview")) {
    Remove-Item -Path "HKCU:\Software\Markview" -Recurse -Force
}
