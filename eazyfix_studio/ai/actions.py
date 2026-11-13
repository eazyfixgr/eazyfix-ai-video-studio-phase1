"""Strict allow-listed project mutations returned by AI planning."""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import Any

from ..assistant import create_from_prompt
from ..models import Layer, Project, Scene, new_id


class AIActionError(ValueError):
    pass


ASPECT_RATIOS = {"portrait": (1080, 1920), "landscape": (1920, 1080), "square": (1080, 1080)}
ANIMATIONS = {"fade", "fade_up", "zoom", "slide_left", "spring", "word_reveal"}
TRANSITIONS = {"fade", "wipe", "push", "cut"}


@dataclass(frozen=True)
class AppliedPlan:
    project: Project
    summaries: tuple[str, ...]
    created_project: bool = False


def _keys(action: dict[str, Any], allowed: set[str]) -> None:
    extra = set(action) - allowed
    if extra:
        raise AIActionError(f"Unsupported action field: {sorted(extra)[0]}")


def _text(action: dict[str, Any], key: str, *, required: bool = True, maximum: int = 240, default: str = "") -> str:
    value = action.get(key, default)
    if not required and key not in action:
        return default
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        raise AIActionError(f"Action field '{key}' must be text under {maximum} characters.")
    return value.strip()


def _index(action: dict[str, Any], key: str = "scene_index", *, required: bool = True) -> int | None:
    value = action.get(key)
    if value is None and not required:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AIActionError(f"Action field '{key}' must be a zero-based scene number.")
    return value


def _number(action: dict[str, Any], key: str, *, low: float, high: float) -> float:
    value = action.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise AIActionError(f"Action field '{key}' must be a finite number.")
    result = float(value)
    if not low <= result <= high:
        raise AIActionError(f"Action field '{key}' must be between {low:g} and {high:g}.")
    return result


def _scene(project: Project, index: int) -> Scene:
    if index >= len(project.scenes):
        raise AIActionError(f"Scene {index + 1} no longer exists.")
    return project.scenes[index]


def _find_text_layer(project: Project, action: dict[str, Any], selected_layer_id: str) -> Layer:
    layer_id = action.get("layer_id")
    role = action.get("role")
    if layer_id is not None and role is not None:
        raise AIActionError("Choose either a layer ID or a semantic role for a text edit.")
    if layer_id is None and role is None:
        layer_id = selected_layer_id
    if layer_id is not None:
        if not isinstance(layer_id, str) or len(layer_id) > 80:
            raise AIActionError("A text action must use a valid layer ID.")
        candidates = [layer for scene in project.scenes for layer in scene.layers if layer.id == layer_id and layer.kind == "text"]
    elif role is not None:
        if not isinstance(role, str) or len(role) > 80:
            raise AIActionError("A text action must use a valid semantic role.")
        index = _index(action, required=False)
        scenes = [_scene(project, index)] if index is not None else project.scenes
        candidates = [layer for scene in scenes for layer in scene.layers if layer.role == role and layer.kind == "text"]
    else:
        candidates = []
    if len(candidates) != 1:
        raise AIActionError("The requested text target is missing or ambiguous. Select an element and retry.")
    return candidates[0]


def _apply_one(project: Project, action: dict[str, Any], selected_layer_id: str) -> tuple[str, Project | None]:
    if not isinstance(action, dict) or len(action) > 12:
        raise AIActionError("An AI action must be a small JSON object.")
    operation = action.get("op")
    if not isinstance(operation, str):
        raise AIActionError("An AI action is missing its operation name.")

    if operation == "create_project":
        _keys(action, {"op", "title", "duration", "aspect_ratio", "theme", "headlines", "call_to_action"})
        title = _text(action, "title", maximum=80)
        duration = _number(action, "duration", low=5, high=60)
        ratio = _text(action, "aspect_ratio", maximum=16)
        theme = _text(action, "theme", maximum=20)
        if ratio not in ASPECT_RATIOS or theme not in {"website", "restaurant", "product", "business", "generic"}:
            raise AIActionError("The requested project format or theme is not supported.")
        ratio_prompt = {"portrait": "portrait", "landscape": "landscape", "square": "square"}[ratio]
        project = create_from_prompt(f"Create a {theme} {duration:g}-second {ratio_prompt} advertisement")
        project.name = title
        project.width, project.height = ASPECT_RATIOS[ratio]
        heads = action.get("headlines", [])
        if not isinstance(heads, list) or len(heads) > 3 or any(not isinstance(value, str) or len(value) > 100 for value in heads):
            raise AIActionError("Project headlines must be a list of at most three short strings.")
        roles = {layer.role: layer for scene in project.scenes for layer in scene.layers}
        for role, value in zip(("intro_headline", "showcase_headline", "closing_headline"), heads):
            if role in roles:
                roles[role].text = value
        cta = _text(action, "call_to_action", required=False, maximum=120)
        if cta:
            roles["call_to_action"].text = cta
        project.validate()
        return f"Created editable {title} project", project

    if operation == "update_text":
        _keys(action, {"op", "layer_id", "role", "scene_index", "text"})
        layer = _find_text_layer(project, action, selected_layer_id)
        layer.text = _text(action, "text")
        return f"Updated text in {layer.role}", None

    if operation == "set_scene_duration":
        _keys(action, {"op", "scene_index", "duration"})
        index = _index(action)
        scene = _scene(project, index)
        scene.duration = _number(action, "duration", low=0.5, high=300)
        scene.transition_duration = min(scene.transition_duration, scene.duration * 0.5)
        return f"Changed duration of Scene {index + 1}", None

    if operation == "set_aspect_ratio":
        _keys(action, {"op", "aspect_ratio"})
        ratio = _text(action, "aspect_ratio", maximum=16)
        if ratio not in ASPECT_RATIOS:
            raise AIActionError("Aspect ratio must be portrait, landscape, or square.")
        project.width, project.height = ASPECT_RATIOS[ratio]
        return f"Set {ratio} aspect ratio", None

    if operation == "set_music_volume":
        _keys(action, {"op", "volume"})
        project.music_volume = _number(action, "volume", low=0, high=2)
        return "Updated background music volume", None

    if operation == "set_transition":
        _keys(action, {"op", "scene_index", "transition"})
        index = _index(action)
        transition = _text(action, "transition", maximum=20)
        if transition not in TRANSITIONS:
            raise AIActionError("That transition preset is not available.")
        _scene(project, index).transition = transition
        return f"Changed Scene {index + 1} transition", None

    if operation == "set_animation":
        _keys(action, {"op", "layer_id", "animation"})
        layer_id = _text(action, "layer_id", maximum=80)
        animation = _text(action, "animation", maximum=30)
        if animation not in ANIMATIONS:
            raise AIActionError("That animation preset is not available.")
        layer = next((item for scene in project.scenes for item in scene.layers if item.id == layer_id), None)
        if not layer:
            raise AIActionError("The requested element no longer exists.")
        layer.animation = animation
        return f"Changed animation for {layer.role}", None

    if operation == "place_asset":
        _keys(action, {"op", "asset_id", "scene_index"})
        asset_id = _text(action, "asset_id", maximum=80)
        index = _index(action)
        asset = next((item for item in project.assets if item.id == asset_id and item.kind == "image"), None)
        if not asset:
            raise AIActionError("The requested image asset is not available.")
        scene = _scene(project, index)
        asset.use_in_video = True
        scene.layers.append(Layer(new_id(), "project_showcase", kind="image", asset_id=asset.id, x=0.5, y=0.65, width=0.82, height=0.31, animation="zoom", fit="cover"))
        return f"Placed {asset.name} in Scene {index + 1}", None

    if operation == "replace_asset":
        _keys(action, {"op", "layer_id", "asset_id"})
        layer_id = _text(action, "layer_id", maximum=80)
        asset_id = _text(action, "asset_id", maximum=80)
        layer = next((item for scene in project.scenes for item in scene.layers if item.id == layer_id and item.kind == "image"), None)
        asset = next((item for item in project.assets if item.id == asset_id and item.kind == "image"), None)
        if not layer or not asset:
            raise AIActionError("The selected image layer or replacement asset was not found.")
        layer.asset_id = asset.id
        asset.use_in_video = True
        return f"Replaced image in {layer.role}", None

    if operation == "add_scene":
        _keys(action, {"op", "title", "duration", "headline", "subtitle"})
        title = _text(action, "title", maximum=80)
        duration = _number(action, "duration", low=0.5, high=30)
        headline = _text(action, "headline", maximum=120)
        subtitle = _text(action, "subtitle", required=False, maximum=160)
        project.scenes.append(Scene(
            id=new_id(),
            title=title,
            duration=duration,
            transition="fade",
            transition_duration=min(0.45, duration * 0.5),
            layers=[
                Layer(new_id(), "scene_headline", text=headline, y=0.42, font_size=76, animation="fade_up"),
                Layer(new_id(), "scene_subtitle", text=subtitle, y=0.56, font_size=34, color="#C5FA72", animation="fade_up"),
            ],
        ))
        return f"Added scene: {title}", None

    if operation == "duplicate_scene":
        _keys(action, {"op", "scene_index"})
        index = _index(action)
        duplicate = copy.deepcopy(_scene(project, index))
        duplicate.id = new_id()
        duplicate.title += " (copy)"
        for layer in duplicate.layers:
            layer.id = new_id()
        project.scenes.insert(index + 1, duplicate)
        return f"Duplicated Scene {index + 1}", None

    if operation == "delete_scene":
        _keys(action, {"op", "scene_index"})
        index = _index(action)
        if len(project.scenes) <= 1:
            raise AIActionError("A project must keep at least one scene.")
        title = _scene(project, index).title
        project.scenes.pop(index)
        return f"Deleted scene: {title}", None

    raise AIActionError(f"Unsupported operation: {operation}")


def apply_project_actions(project: Project, actions: list[dict[str, Any]], selected_layer_id: str = "") -> AppliedPlan:
    """Apply only validated app operations to a copy; failures leave the project intact."""
    if not isinstance(actions, list) or len(actions) > 12:
        raise AIActionError("The AI plan must contain no more than 12 actions.")
    working = copy.deepcopy(project)
    summaries: list[str] = []
    created_project = False
    for action in actions:
        summary, new_project = _apply_one(working, action, selected_layer_id)
        if new_project:
            new_project.assets = copy.deepcopy(working.assets)
            new_project.music_asset_id = working.music_asset_id
            new_project.music_volume = working.music_volume
            new_project.music_fade_in = working.music_fade_in
            new_project.music_fade_out = working.music_fade_out
            working = new_project
            created_project = True
        working.validate()
        summaries.append(summary)
    return AppliedPlan(working, tuple(summaries), created_project)
