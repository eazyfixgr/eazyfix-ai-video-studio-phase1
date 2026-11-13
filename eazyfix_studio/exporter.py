"""Cancelable background MP4 exporter using FFmpeg and the shared frame renderer."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .models import Project
from .renderer import render_frame


def find_ffmpeg() -> str | None:
    configured = os.environ.get("FFMPEG_BINARY")
    if configured and Path(configured).is_file():
        return configured
    available = shutil.which("ffmpeg")
    if available:
        return available
    bundle_dir = getattr(sys, "_MEIPASS", "")
    if bundle_dir:
        bundled = Path(bundle_dir) / "ffmpeg.exe"
        if bundled.is_file():
            return str(bundled)
    return None


class ExportWorker(QThread):
    progress = Signal(int)
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, project: Project, output_path: str, parent=None):
        super().__init__(parent)
        self.project = project
        self.output_path = str(Path(output_path).expanduser().resolve())
        self.cancel_event = threading.Event()
        self.process: subprocess.Popen | None = None

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        output = Path(self.output_path)
        temp_output = output.with_name(f"{output.stem}.rendering{output.suffix or '.mp4'}")
        try:
            binary = find_ffmpeg()
            if not binary:
                raise RuntimeError("FFmpeg was not found. Install FFmpeg or set FFMPEG_BINARY.")
            self.project.validate()
            output.parent.mkdir(parents=True, exist_ok=True)
            frame_count = max(1, round(self.project.duration * self.project.fps))
            command = [
                binary, "-y", "-hide_banner", "-loglevel", "error",
                "-f", "rawvideo", "-pix_fmt", "rgb24",
                "-s", f"{self.project.width}x{self.project.height}",
                "-r", str(self.project.fps), "-i", "pipe:0",
            ]
            audio = next((asset for asset in self.project.assets if asset.id == self.project.music_asset_id), None)
            has_audio = bool(audio and audio.use_in_video and Path(audio.path).is_file())
            if has_audio:
                command += ["-i", audio.path]
            command += ["-map", "0:v:0", "-c:v", "libx264", "-preset", "medium", "-crf", str(self.project.export_crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
            if has_audio:
                fade_out_start = max(0.0, self.project.duration - self.project.music_fade_out)
                audio_filter = (
                    f"apad,atrim=duration={self.project.duration:.3f},volume={self.project.music_volume:.3f},"
                    f"afade=t=in:st=0:d={self.project.music_fade_in:.3f},"
                    f"afade=t=out:st={fade_out_start:.3f}:d={min(self.project.music_fade_out, self.project.duration):.3f}"
                )
                command += ["-map", "1:a:0", "-af", audio_filter, "-c:a", "aac", "-b:a", "192k"]
            else:
                command += ["-an"]
            command += ["-t", f"{self.project.duration:.3f}", "-r", str(self.project.fps), str(temp_output)]
            self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            assert self.process.stdin is not None
            for index in range(frame_count):
                if self.cancel_event.is_set():
                    self.process.terminate()
                    self.process.wait(timeout=10)
                    raise InterruptedError("Export cancelled.")
                frame = render_frame(self.project, index / self.project.fps, (self.project.width, self.project.height))
                self.process.stdin.write(frame.tobytes())
                if index % max(1, self.project.fps // 2) == 0 or index + 1 == frame_count:
                    self.progress.emit(round((index + 1) * 100 / frame_count))
            self.process.stdin.close()
            stderr = self.process.stderr.read().decode("utf-8", errors="replace") if self.process.stderr else ""
            if self.process.stderr:
                self.process.stderr.close()
            return_code = self.process.wait()
            self.process = None
            if return_code != 0:
                raise RuntimeError(stderr.strip() or f"FFmpeg exited with code {return_code}.")
            if not temp_output.is_file() or temp_output.stat().st_size < 1024:
                raise RuntimeError("FFmpeg did not produce a valid video file.")
            temp_output.replace(output)
            self.completed.emit(str(output))
        except InterruptedError:
            if self.process and self.process.stdin:
                self.process.stdin.close()
            if self.process and self.process.poll() is None:
                self.process.kill()
                self.process.wait()
            if self.process and self.process.stderr:
                self.process.stderr.close()
            self.process = None
            if temp_output.exists():
                temp_output.unlink()
        except Exception as error:  # Surface actionable errors in the UI.
            if self.process and self.process.stdin:
                try:
                    self.process.stdin.close()
                except OSError:
                    pass
            if self.process and self.process.poll() is None:
                self.process.kill()
                self.process.wait()
            if self.process and self.process.stderr:
                self.process.stderr.close()
            self.process = None
            if temp_output.exists():
                temp_output.unlink()
            self.failed.emit(str(error))
