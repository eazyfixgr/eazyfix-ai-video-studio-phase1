from __future__ import annotations

import tempfile
import unittest
import json
import math
import shutil
import struct
import subprocess
import wave
from pathlib import Path

from PIL import Image, ImageChops

from eazyfix_studio.assistant import apply_offline_edit, create_from_prompt
from eazyfix_studio.models import Asset, Layer, Project, new_id, sample_project
from eazyfix_studio.exporter import ExportWorker, find_ffmpeg
from eazyfix_studio.project_io import load_project, save_project
from eazyfix_studio.renderer import render_frame


class ProjectModelTests(unittest.TestCase):
    def test_sample_project_has_editable_ten_second_story(self):
        project = sample_project()
        project.validate()
        self.assertAlmostEqual(project.duration, 10.0)
        self.assertEqual(len(project.scenes), 3)
        self.assertTrue(any(layer.role == "intro_headline" for layer in project.scenes[0].layers))

    def test_invalid_transition_is_rejected(self):
        project = sample_project()
        project.scenes[0].transition = "run_arbitrary_code"
        with self.assertRaises(ValueError):
            project.validate()

    def test_project_save_load_keeps_asset_relative_and_editable(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            original = root / "logo.png"
            Image.new("RGBA", (32, 32), "purple").save(original)
            project = sample_project()
            asset = Asset("asset-logo", "logo.png", str(original), role="brand_logo")
            project.assets.append(asset)
            project.scenes[-1].layers.append(Layer("layer-logo", "closing_logo", kind="image", asset_id=asset.id))
            path = root / "promo.eazyproj"
            save_project(project, path)
            loaded = load_project(path)
            self.assertEqual(loaded.scenes[-1].layers[-1].role, "closing_logo")
            self.assertTrue(Path(loaded.assets[0].path).is_file())
            self.assertEqual(loaded.scenes[-1].layers[-1].asset_id, "asset-logo")


class RenderingAndOfflineAssistantTests(unittest.TestCase):
    def test_shared_renderer_outputs_frames_for_different_scenes(self):
        project = sample_project()
        first = render_frame(project, 1.0, (180, 320))
        second = render_frame(project, 5.5, (180, 320))
        self.assertEqual(first.size, (180, 320))
        self.assertIsNotNone(ImageChops.difference(first, second).getbbox())

    def test_prompt_builder_honors_duration_and_aspect_ratio(self):
        project = create_from_prompt("Create a professional 20-second landscape website advertisement")
        self.assertAlmostEqual(project.duration, 20.0)
        self.assertEqual((project.width, project.height), (1920, 1080))

    def test_svg_asset_renders_through_qtsvg(self):
        with tempfile.TemporaryDirectory() as folder:
            svg = Path(folder) / "brand.svg"
            svg.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><circle cx="50" cy="50" r="42" fill="#C5FA72"/></svg>', encoding="utf-8")
            project = sample_project()
            asset = Asset("svg-brand", "brand.svg", str(svg), kind="image", role="brand_logo")
            project.assets.append(asset)
            project.scenes[0].layers.append(Layer("svg-layer", "closing_logo", kind="image", asset_id=asset.id, x=0.5, y=0.78, width=0.25, height=0.12))
            frame = render_frame(project, 2.0, (180, 320))
            self.assertEqual(frame.size, (180, 320))

    def test_offline_edit_targets_second_headline_only(self):
        project = sample_project()
        first_headline = project.scenes[0].layers[1].text
        selected_first_layer = project.scenes[0].layers[1].id
        summary, changed = apply_offline_edit(project, "Change the second headline to 'Ιστοσελίδες στα μέτρα σου'.", selected_first_layer)
        self.assertTrue(changed)
        self.assertIn("Ιστοσελίδες στα μέτρα σου", summary)
        self.assertEqual(project.scenes[1].layers[1].text, "Ιστοσελίδες στα μέτρα σου")
        self.assertEqual(project.scenes[0].layers[1].text, first_headline)


@unittest.skipUnless(find_ffmpeg() and shutil.which("ffprobe"), "FFmpeg and ffprobe are required for the export smoke test")
class ExportIntegrationTests(unittest.TestCase):
    def test_real_h264_mp4_is_exported(self):
        project = sample_project()
        project.scenes = [project.scenes[0]]
        project.scenes[0].duration = 1.0
        project.scenes[0].transition = "cut"
        project.width, project.height, project.fps = 270, 480, 2
        with tempfile.TemporaryDirectory() as folder:
            audio_path = Path(folder) / "tone.wav"
            with wave.open(str(audio_path), "wb") as audio_file:
                audio_file.setparams((1, 2, 44100, 44100, "NONE", "not compressed"))
                samples = (struct.pack("<h", int(5000 * math.sin(2 * math.pi * 440 * index / 44100))) for index in range(44100))
                audio_file.writeframes(b"".join(samples))
            music = Asset(new_id(), "tone.wav", str(audio_path), kind="audio", role="background_music")
            project.assets.append(music)
            project.music_asset_id = music.id
            output = Path(folder) / "smoke.mp4"
            worker = ExportWorker(project, str(output))
            errors: list[str] = []
            worker.failed.connect(errors.append)
            worker.run()
            self.assertFalse(errors, errors[0] if errors else "")
            self.assertTrue(output.is_file())
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height", "-show_entries", "format=duration", "-of", "json", str(output)],
                check=True,
                capture_output=True,
                text=True,
            )
            metadata = json.loads(probe.stdout)
            video = next(stream for stream in metadata["streams"] if stream["codec_name"] == "h264")
            self.assertEqual((video["width"], video["height"]), (270, 480))
            self.assertTrue(any(stream["codec_name"] == "aac" for stream in metadata["streams"]))
            self.assertGreater(float(metadata["format"]["duration"]), 0.5)


if __name__ == "__main__":
    unittest.main()
