param([switch]$BundleFFmpeg)
$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Push-Location $Root
try {
    python -m pip install -r requirements-build.txt

    $Arguments = @(
        "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
        "--name", "EazyFix AI Video Studio",
        "--collect-all", "PySide6.QtSvg",
        "--add-data", "sample_projects;sample_projects",
        "main.py"
    )
    if ($BundleFFmpeg) {
        $FFmpeg = Get-Command ffmpeg.exe -ErrorAction SilentlyContinue
        if (-not $FFmpeg) {
            throw "-BundleFFmpeg was requested, but ffmpeg.exe was not found in PATH."
        }
        $Arguments += @("--add-binary", "$($FFmpeg.Source);.")
    } else {
        Write-Host "FFmpeg will not be bundled; install it separately or rebuild with -BundleFFmpeg after license review."
    }
    & python @Arguments
    Write-Host "Build complete: $Root\dist\EazyFix AI Video Studio\EazyFix AI Video Studio.exe"
} finally {
    Pop-Location
}
