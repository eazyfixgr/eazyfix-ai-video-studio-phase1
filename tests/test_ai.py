from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import types
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from eazyfix_studio.ai.actions import AIActionError, apply_project_actions
from eazyfix_studio.ai.config import AISettings, AISettingsStore, SecureKeyStore
from eazyfix_studio.ai.deepseek import Completion, DeepSeekClient, ModelInfo
from eazyfix_studio.ai.images import image_data_url
from eazyfix_studio.ai.planner import DeepSeekPlanner, _parse_plan, project_summary
from eazyfix_studio.models import Asset, Layer, sample_project


class SafeActionTests(unittest.TestCase):
    def test_text_edit_targets_a_single_layer(self):
        project = sample_project()
        original = project.scenes[0].layers[1].text
        applied = apply_project_actions(project, [{
            "op": "update_text",
            "role": "showcase_headline",
            "scene_index": 1,
            "text": "New Greek headline",
        }])
        self.assertEqual(applied.project.scenes[1].layers[1].text, "New Greek headline")
        self.assertEqual(applied.project.scenes[0].layers[1].text, original)
        self.assertEqual(project.scenes[1].layers[1].text, "ΙΣΤΟΣΕΛΙΔΕΣ\nΣΤΑ ΜΕΤΡΑ ΣΟΥ")

    def test_unrecognized_or_shell_like_operation_is_rejected_atomically(self):
        project = sample_project()
        before = project.to_dict()
        actions = [
            {"op": "update_text", "role": "showcase_headline", "scene_index": 1, "text": "temporary"},
            {"op": "run_shell", "command": "whoami"},
        ]
        with self.assertRaises(AIActionError):
            apply_project_actions(project, actions)
        self.assertEqual(project.to_dict(), before)

    def test_replacement_preserves_image_layer_animation_and_position(self):
        project = sample_project()
        first = Asset("asset-a", "one.png", "one.png", role="project_one")
        second = Asset("asset-b", "two.png", "two.png", role="project_two")
        project.assets.extend((first, second))
        layer = Layer("image-layer", "project_showcase", kind="image", asset_id=first.id, x=0.33, y=0.7, animation="slide_left")
        project.scenes[1].layers.append(layer)
        project.validate()
        applied = apply_project_actions(project, [{"op": "replace_asset", "layer_id": layer.id, "asset_id": second.id}])
        updated = applied.project.scenes[1].layers[-1]
        self.assertEqual(updated.asset_id, second.id)
        self.assertEqual((updated.x, updated.y, updated.animation), (0.33, 0.7, "slide_left"))

    def test_create_project_keeps_existing_asset_library(self):
        project = sample_project()
        asset = Asset("logo-1", "logo.png", "logo.png", role="company_logo")
        project.assets.append(asset)
        project.validate()
        applied = apply_project_actions(project, [{
            "op": "create_project",
            "title": "Restaurant Reel",
            "duration": 20,
            "aspect_ratio": "portrait",
            "theme": "restaurant",
            "headlines": ["Fresh food", "Made today", "Visit us"],
            "call_to_action": "Book a table",
        }])
        self.assertAlmostEqual(applied.project.duration, 20)
        self.assertEqual(applied.project.assets[0].id, asset.id)
        self.assertEqual(applied.project.scenes[1].layers[1].text, "Made today")
        self.assertTrue(applied.created_project)


class DeepSeekContractTests(unittest.TestCase):
    def test_http_client_uses_official_paths_and_hides_secret_from_payload(self):
        class Handler(BaseHTTPRequestHandler):
            authorization = ""
            requests: list[tuple[str, dict]] = []

            def do_GET(self):
                type(self).authorization = self.headers.get("Authorization", "")
                body = {"object": "list", "data": [{"id": "deepseek-flash", "input_modalities": ["text", "image"]}]}
                self._json(body)

            def do_POST(self):
                type(self).authorization = self.headers.get("Authorization", "")
                request = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                type(self).requests.append((self.path, request))
                self._json({"model": "deepseek-v4-pro", "choices": [{"message": {"content": '{"reply":"ok","actions":[]}'}}], "usage": {"prompt_tokens": 4, "completion_tokens": 3, "total_tokens": 7}})

            def _json(self, value):
                payload = json.dumps(value).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *_args):
                pass

        Handler.requests = []
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = DeepSeekClient(f"http://127.0.0.1:{server.server_port}", "test-secret")
            models = client.list_models()
            result = client.chat_completion(model="deepseek-v4-pro", messages=[{"role": "user", "content": "test"}])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.assertEqual(models[0], ModelInfo("deepseek-flash", ("text", "image")))
        self.assertEqual(result.usage["total_tokens"], 7)
        self.assertEqual(Handler.authorization, "Bearer test-secret")
        path, sent_payload = Handler.requests[0]
        self.assertEqual(path, "/chat/completions")
        self.assertNotIn("test-secret", json.dumps(sent_payload))
        self.assertEqual(sent_payload["response_format"], {"type": "json_object"})

    def test_cancel_closes_an_in_flight_provider_request(self):
        response_started = threading.Event()

        class SlowHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", "100")
                self.end_headers()
                response_started.set()
                time.sleep(1.0)
                try:
                    self.wfile.write(b"{}")
                except OSError:
                    pass

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), SlowHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        client = DeepSeekClient(f"http://127.0.0.1:{server.server_port}", "test-secret", timeout=5)
        errors: list[Exception] = []
        request_thread = threading.Thread(target=lambda: self._capture_error(client, errors), daemon=True)
        request_thread.start()
        try:
            self.assertTrue(response_started.wait(2))
            client.cancel()
            request_thread.join(timeout=2)
            self.assertFalse(request_thread.is_alive(), "cancel should close the active HTTP connection")
            self.assertTrue(errors)
            self.assertIn("cancelled", str(errors[0]).casefold())
        finally:
            server.shutdown()
            server.server_close()
            server_thread.join(timeout=2)

    def test_json_plan_has_strict_top_level_contract(self):
        plan = _parse_plan('{"reply":"ready","actions":[]}', "deepseek-v4-pro", {"total_tokens": 4}, 0)
        self.assertEqual(plan.reply, "ready")
        with self.assertRaises(ValueError):
            _parse_plan('{"reply":"bad","actions":[],"shell":"no"}', "model", {}, 0)

    def test_project_summary_never_contains_original_file_paths(self):
        project = sample_project()
        project.assets.append(Asset("image-1", "client.png", "C:/private/user/client.png", description="Client site screenshot"))
        summary = json.dumps(project_summary(project), ensure_ascii=False)
        self.assertIn("client.png", summary)
        self.assertNotIn("C:/private/user", summary)

    def test_vision_images_are_only_added_when_explicitly_selected(self):
        project = sample_project()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "screen.png"
            Image.new("RGB", (24, 24), "blue").save(path)
            asset = Asset("screen-1", "screen.png", str(path))
            project.assets.append(asset)
            with patch("eazyfix_studio.ai.planner.DeepSeekClient") as client_class:
                client = client_class.return_value
                client.chat_completion.return_value = Completion('{"reply":"ok","actions":[]}', "deepseek-v4-pro", {})
                planner = DeepSeekPlanner("https://api.deepseek.com", "secret", "deepseek-v4-pro", "deepseek-flash")
                planner.create_plan("Describe the project", project)
                text_only = client.chat_completion.call_args.kwargs["messages"][-1]["content"]
                self.assertFalse(any(item.get("type") == "image_url" for item in text_only))
                client.list_models.return_value = [ModelInfo("deepseek-flash", ("text", "image"))]
                planner.create_plan("Analyze the selected image", project, image_asset_ids=[asset.id])
                with_image = client.chat_completion.call_args.kwargs["messages"][-1]["content"]
                part = next(item for item in with_image if item.get("type") == "image_url")
                self.assertTrue(part["image_url"]["url"].startswith("data:image/jpeg;base64,"))

    def test_api_key_is_stored_outside_settings_file(self):
        class FakeBackend:
            __module__ = "keyring.backends.Windows"

        secret = {"value": ""}
        fake_keyring = types.ModuleType("keyring")
        fake_keyring.get_keyring = lambda: FakeBackend()
        fake_keyring.set_password = lambda _service, _user, value: secret.update(value=value)
        fake_keyring.get_password = lambda _service, _user: secret["value"] or None
        class FakeDeleteError(Exception):
            pass
        fake_keyring.delete_password = lambda _service, _user: secret.update(value="")
        fake_keyring.errors = types.SimpleNamespace(PasswordDeleteError=FakeDeleteError)

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "settings.json"
            with patch.dict(sys.modules, {"keyring": fake_keyring}), patch("eazyfix_studio.ai.config.settings_path", return_value=path):
                key_store = SecureKeyStore()
                key_store.set("deepseek-private-key")
                AISettingsStore().save(AISettings(provider="deepseek", allow_project_context=True))
                self.assertEqual(key_store.get(), "deepseek-private-key")
                self.assertNotIn("deepseek-private-key", path.read_text(encoding="utf-8"))

    @staticmethod
    def _capture_error(client: DeepSeekClient, errors: list[Exception]) -> None:
        try:
            client.chat_completion(model="deepseek-flash", messages=[{"role": "user", "content": "cancel"}])
        except Exception as error:
            errors.append(error)


if __name__ == "__main__":
    unittest.main()
