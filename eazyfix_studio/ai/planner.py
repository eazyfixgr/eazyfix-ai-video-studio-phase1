"""DeepSeek vision/reasoning planner that returns validated JSON, never executable code."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..models import Project
from .deepseek import DeepSeekClient
from .images import image_data_url


SYSTEM_PROMPT = """You are the creative director for EazyFix AI Video Studio.
Understand the user request and propose a concise edit plan for the current editable video project.
Return a JSON object only, with exactly these keys: {\"reply\": \"short helpful response\", \"actions\": []}.
The actions array is a list of app operations, never code. You may use only:
1) {\"op\":\"create_project\",\"title\":string,\"duration\":number 5..60,\"aspect_ratio\":\"portrait|landscape|square\",\"theme\":\"website|restaurant|product|business|generic\",\"headlines\":[up to 3 strings],\"call_to_action\":string}
2) {\"op\":\"update_text\",\"layer_id\":string OR \"role\":string, optional \"scene_index\":integer, \"text\":string}
3) {\"op\":\"set_scene_duration\",\"scene_index\":integer,\"duration\":number}
4) {\"op\":\"set_aspect_ratio\",\"aspect_ratio\":\"portrait|landscape|square\"}
5) {\"op\":\"set_music_volume\",\"volume\":number 0..2}
6) {\"op\":\"set_transition\",\"scene_index\":integer,\"transition\":\"fade|wipe|push|cut\"}
7) {\"op\":\"set_animation\",\"layer_id\":string,\"animation\":\"fade|fade_up|zoom|slide_left|spring|word_reveal\"}
8) {\"op\":\"place_asset\",\"asset_id\":string,\"scene_index\":integer}
9) {\"op\":\"replace_asset\",\"layer_id\":string,\"asset_id\":string}
10) {\"op\":\"add_scene\",\"title\":string,\"duration\":number,\"headline\":string, optional \"subtitle\":string}
11) {\"op\":\"duplicate_scene\",\"scene_index\":integer}
12) {\"op\":\"delete_scene\",\"scene_index\":integer}
Use create_project only when the user asks for a new video. For a change request, update only the exact target and do not recreate unrelated scenes.
Prefer the currently selected element when the user says “this/selected”; its ID is included in the project summary.
Use asset IDs exactly as supplied. Do not invent IDs. Place images only if requested for the video. Preserve supplied brand, names, and text.
Do not ask the renderer to run code or shell commands. If the request cannot be expressed by these operations, explain that in reply and use no action.
All user-facing reply text should use the project's language. Keep the reply short. Example JSON: {\"reply\":\"Έτοιμο.\",\"actions\":[{\"op\":\"set_aspect_ratio\",\"aspect_ratio\":\"portrait\"}]}"""


@dataclass(frozen=True)
class AIPlan:
    reply: str
    actions: tuple[dict[str, Any], ...]
    model: str
    usage: dict[str, int]
    image_count: int


def project_summary(project: Project, selected_layer_id: str = "") -> dict[str, Any]:
    selected = None
    scenes = []
    for index, scene in enumerate(project.scenes):
        layers = []
        for layer in scene.layers:
            layer_summary = {
                "id": layer.id,
                "role": layer.role,
                "kind": layer.kind,
                "text": layer.text[:240],
                "asset_id": layer.asset_id,
                "animation": layer.animation,
            }
            layers.append(layer_summary)
            if layer.id == selected_layer_id:
                selected = {"id": layer.id, "role": layer.role, "kind": layer.kind, "text": layer.text[:240], "scene_index": index}
        scenes.append({"index": index, "title": scene.title[:80], "duration": round(scene.duration, 2), "transition": scene.transition, "layers": layers[:20]})
    return {
        "name": project.name[:80],
        "duration": round(project.duration, 2),
        "canvas": {"width": project.width, "height": project.height, "fps": project.fps},
        "language": project.language,
        "selected_element": selected,
        "assets": [
            {"id": item.id, "name": item.name[:100], "kind": item.kind, "role": item.role[:80], "description": item.description[:180], "use_in_video": item.use_in_video}
            for item in project.assets[:50]
        ],
        "scenes": scenes[:40],
    }


def _parse_plan(content: str, model: str, usage: dict[str, int], image_count: int) -> AIPlan:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError("The AI response was not valid JSON. Retry the request.") from error
    if not isinstance(payload, dict) or set(payload) != {"reply", "actions"}:
        raise ValueError("The AI response did not match the required project-plan format.")
    reply = payload["reply"]
    actions = payload["actions"]
    if not isinstance(reply, str) or len(reply) > 2400:
        raise ValueError("The AI response included an invalid reply.")
    if not isinstance(actions, list) or len(actions) > 12 or any(not isinstance(action, dict) for action in actions):
        raise ValueError("The AI returned an invalid action list.")
    return AIPlan(reply.strip(), tuple(actions), model, usage, image_count)


class DeepSeekPlanner:
    def __init__(self, endpoint: str, api_key: str, text_model: str, vision_model: str):
        self.client = DeepSeekClient(endpoint, api_key)
        self.text_model = text_model
        self.vision_model = vision_model

    def cancel(self) -> None:
        self.client.cancel()

    def create_plan(
        self,
        prompt: str,
        project: Project,
        *,
        selected_layer_id: str = "",
        conversation: list[dict[str, str]] | None = None,
        image_asset_ids: list[str] | None = None,
    ) -> AIPlan:
        summary = project_summary(project, selected_layer_id)
        user_text = f"Current editable project state (JSON):\n{json.dumps(summary, ensure_ascii=False)}\n\nUser request:\n{prompt}"
        content: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
        approved_ids = image_asset_ids or []
        if len(approved_ids) > 6:
            raise ValueError("Select up to six images for one vision request.")
        image_assets = [
            asset for asset_id in approved_ids
            if (asset := next((item for item in project.assets if item.id == asset_id and item.kind == "image"), None)) is not None
        ]
        image_parts: list[dict[str, Any]] = []
        for asset in image_assets:
            image_parts.append({"type": "image_url", "image_url": {"url": image_data_url(asset.path), "detail": "high"}})
        content.extend(image_parts)
        model = self.vision_model if image_parts else self.text_model
        if image_parts:
            models = self.client.list_models()
            capabilities = next((item for item in models if item.id == model), None)
            if capabilities and "image" not in capabilities.input_modalities:
                raise ValueError(f"The selected vision model '{model}' does not accept images. Choose a vision-capable model in AI Settings.")
            if not capabilities:
                raise ValueError(f"The selected vision model '{model}' was not returned by DeepSeek's model list.")

        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        for item in (conversation or [])[-10:]:
            role, text = item.get("role"), item.get("content")
            if role in {"user", "assistant"} and isinstance(text, str):
                messages.append({"role": role, "content": text[:2000]})
        messages.append({"role": "user", "content": content})
        completion = self.client.chat_completion(model=model, messages=messages, max_tokens=4096)
        return _parse_plan(completion.content, completion.model, completion.usage, len(image_parts))
