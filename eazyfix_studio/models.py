"""Validated, serializable project objects used by both preview and export."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

PROJECT_VERSION = 1
CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920


def new_id() -> str:
    return uuid4().hex


@dataclass
class Asset:
    id: str
    name: str
    path: str
    kind: str = "image"
    role: str = "inspiration"
    description: str = ""
    use_in_video: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Asset":
        return cls(
            id=str(data.get("id") or new_id()),
            name=str(data.get("name") or Path(data.get("path", "asset")).name),
            path=str(data.get("path", "")),
            kind=str(data.get("kind", "image")),
            role=str(data.get("role", "inspiration")),
            description=str(data.get("description", "")),
            use_in_video=bool(data.get("use_in_video", True)),
        )


@dataclass
class Layer:
    """A nondestructive text, image, shape, or generated browser mockup layer."""

    id: str
    role: str
    kind: str = "text"
    text: str = ""
    asset_id: str = ""
    x: float = 0.5
    y: float = 0.5
    width: float = 0.8
    height: float = 0.12
    font_size: int = 64
    color: str = "#F7F8FF"
    accent_color: str = "#36D7F4"
    align: str = "center"
    animation: str = "fade_up"
    animation_duration: float = 0.55
    start: float = 0.0
    opacity: float = 1.0
    fit: str = "cover"
    background: str = ""
    radius: float = 0.025

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Layer":
        allowed = cls.__dataclass_fields__
        values = {key: value for key, value in data.items() if key in allowed}
        values.setdefault("id", new_id())
        values.setdefault("role", "visual_element")
        return cls(**values)


@dataclass
class Scene:
    id: str
    title: str
    duration: float
    background_top: str = "#0A0D20"
    background_bottom: str = "#161A38"
    transition: str = "fade"
    transition_duration: float = 0.45
    layers: list[Layer] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Scene":
        return cls(
            id=str(data.get("id") or new_id()),
            title=str(data.get("title", "Scene")),
            duration=float(data.get("duration", 3.0)),
            background_top=str(data.get("background_top", "#0A0D20")),
            background_bottom=str(data.get("background_bottom", "#161A38")),
            transition=str(data.get("transition", "fade")),
            transition_duration=float(data.get("transition_duration", 0.45)),
            layers=[Layer.from_dict(item) for item in data.get("layers", [])],
        )


@dataclass
class Project:
    id: str
    name: str
    width: int = CANVAS_WIDTH
    height: int = CANVAS_HEIGHT
    fps: int = 30
    language: str = "el"
    assets: list[Asset] = field(default_factory=list)
    scenes: list[Scene] = field(default_factory=list)
    music_asset_id: str = ""
    music_volume: float = 0.22
    music_fade_in: float = 0.6
    music_fade_out: float = 1.0
    schema_version: int = PROJECT_VERSION
    export_crf: int = 20

    @property
    def duration(self) -> float:
        return sum(scene.duration for scene in self.scenes)

    def validate(self) -> None:
        if self.schema_version != PROJECT_VERSION:
            raise ValueError(f"Unsupported project version: {self.schema_version}")
        if not 1 <= self.width <= 7680 or not 1 <= self.height <= 4320:
            raise ValueError("Canvas dimensions must be between 1 and 7680 × 4320.")
        if not 1 <= self.fps <= 120:
            raise ValueError("Frame rate must be between 1 and 120 FPS.")
        if not self.scenes:
            raise ValueError("A project needs at least one scene.")
        ids: set[str] = set()
        for asset in self.assets:
            if asset.id in ids:
                raise ValueError("Project object IDs must be unique.")
            ids.add(asset.id)
            if asset.kind not in {"image", "audio", "video"}:
                raise ValueError(f"Unknown asset type: {asset.kind}")
        asset_ids = {asset.id for asset in self.assets}
        if self.music_asset_id and not any(asset.id == self.music_asset_id and asset.kind == "audio" for asset in self.assets):
            raise ValueError("Background music must refer to an imported audio asset.")
        for scene in self.scenes:
            if scene.id in ids:
                raise ValueError("Scene and layer IDs must be unique.")
            ids.add(scene.id)
            if not 0.2 <= scene.duration <= 300:
                raise ValueError(f"Scene '{scene.title}' duration is out of range.")
            if scene.transition not in {"fade", "wipe", "push", "cut"}:
                raise ValueError(f"Unknown transition: {scene.transition}")
            if not 0 <= scene.transition_duration <= scene.duration:
                raise ValueError(f"Scene '{scene.title}' transition duration is out of range.")
            for layer in scene.layers:
                if layer.id in ids:
                    raise ValueError("Scene and layer IDs must be unique.")
                ids.add(layer.id)
                if layer.kind not in {"text", "image", "shape", "mockup"}:
                    raise ValueError(f"Unknown layer type: {layer.kind}")
                if layer.animation not in {"fade", "fade_up", "zoom", "slide_left", "spring", "word_reveal"}:
                    raise ValueError(f"Unknown animation preset: {layer.animation}")
                if not 0 <= layer.x <= 1 or not 0 <= layer.y <= 1:
                    raise ValueError(f"Layer '{layer.role}' position must be normalized.")
                if not 0 < layer.width <= 1.5 or not 0 < layer.height <= 1.5:
                    raise ValueError(f"Layer '{layer.role}' size must be normalized.")
                if not 0 <= layer.opacity <= 1 or layer.font_size < 1:
                    raise ValueError(f"Layer '{layer.role}' style values are out of range.")
                if layer.kind == "image" and layer.asset_id and layer.asset_id not in asset_ids:
                    raise ValueError(f"Layer '{layer.role}' refers to a missing asset.")
        if not 0 <= self.music_volume <= 2:
            raise ValueError("Music volume must be between 0 and 2.")

    def to_dict(self, asset_paths: dict[str, str] | None = None) -> dict[str, Any]:
        result = asdict(self)
        if asset_paths:
            for asset in result["assets"]:
                asset["path"] = asset_paths.get(asset["id"], asset["path"])
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Project":
        version = int(data.get("schema_version", 1))
        if version > PROJECT_VERSION:
            raise ValueError("This project was created by a newer version of EazyFix Studio.")
        # Version 1 is intentionally the initial format; future migrations live here.
        project = cls(
            id=str(data.get("id") or new_id()),
            name=str(data.get("name", "Untitled project")),
            width=int(data.get("width", CANVAS_WIDTH)),
            height=int(data.get("height", CANVAS_HEIGHT)),
            fps=int(data.get("fps", 30)),
            language=str(data.get("language", "el")),
            assets=[Asset.from_dict(item) for item in data.get("assets", [])],
            scenes=[Scene.from_dict(item) for item in data.get("scenes", [])],
            music_asset_id=str(data.get("music_asset_id", "")),
            music_volume=float(data.get("music_volume", 0.22)),
            music_fade_in=float(data.get("music_fade_in", 0.6)),
            music_fade_out=float(data.get("music_fade_out", 1.0)),
            schema_version=PROJECT_VERSION,
            export_crf=int(data.get("export_crf", 20)),
        )
        project.validate()
        return project


def sample_project() -> Project:
    """Create a fully editable 10-second Greek website-promotion project."""
    project = Project(
        id=new_id(),
        name="EazyFix Website Promo",
        scenes=[
            Scene(
                id=new_id(),
                title="Δυνατό ξεκίνημα",
                duration=3.0,
                background_top="#090C1E",
                background_bottom="#1A1E43",
                transition="fade",
                layers=[
                    Layer(new_id(), "brand_label", text="EAZYFIX  •  DIGITAL STUDIO", y=0.12, height=0.04, font_size=26, color="#AAB4D5", animation="fade"),
                    Layer(new_id(), "intro_headline", text="Η ΕΠΙΧΕΙΡΗΣΗ\nΣΟΥ ΕΙΝΑΙ", y=0.34, height=0.20, font_size=90, animation="fade_up"),
                    Layer(new_id(), "intro_accent", text="ΜΟΝΑΔΙΚΗ.", y=0.50, height=0.09, font_size=100, color="#C5FA72", animation="zoom"),
                    Layer(new_id(), "intro_subtitle", text="Η ιστοσελίδα σου μπορεί να είναι επίσης.", y=0.63, height=0.07, font_size=34, color="#C3C9DF", animation="fade_up"),
                ],
            ),
            Scene(
                id=new_id(),
                title="Παρουσίαση έργου",
                duration=4.0,
                background_top="#10132D",
                background_bottom="#20234B",
                transition="wipe",
                layers=[
                    Layer(new_id(), "showcase_kicker", text="ΣΧΕΔΙΑΣΜΕΝΗ ΓΙΑ ΝΑ ΞΕΧΩΡΙΖΕΙ", y=0.14, height=0.05, font_size=27, color="#36D7F4", animation="fade"),
                    Layer(new_id(), "showcase_headline", text="ΙΣΤΟΣΕΛΙΔΕΣ\nΣΤΑ ΜΕΤΡΑ ΣΟΥ", y=0.27, height=0.17, font_size=72, animation="fade_up"),
                    Layer(new_id(), "project_showcase", kind="mockup", text="Η ψηφιακή εικόνα της επιχείρησής σου", x=0.5, y=0.62, width=0.84, height=0.35, animation="zoom", background="#F7F8FD", accent_color="#6758F5"),
                    Layer(new_id(), "showcase_caption", text="Μοντέρνος σχεδιασμός. Εμπειρία που μένει.", y=0.88, height=0.05, font_size=28, color="#C3C9DF", animation="fade_up"),
                ],
            ),
            Scene(
                id=new_id(),
                title="Κλείσιμο και επικοινωνία",
                duration=3.0,
                background_top="#0B1022",
                background_bottom="#161B39",
                transition="push",
                layers=[
                    Layer(new_id(), "closing_brand", text="EazyFix", y=0.30, height=0.12, font_size=112, animation="zoom"),
                    Layer(new_id(), "closing_headline", text="ΙΣΤΟΣΕΛΙΔΕΣ\nΣΤΑ ΜΕΤΡΑ ΣΟΥ.", y=0.48, height=0.17, font_size=70, color="#C5FA72", animation="fade_up"),
                    Layer(new_id(), "call_to_action", text="Πες μου την ιδέα σου  •  eazyfix.gr", y=0.70, height=0.07, font_size=36, color="#F7F8FF", animation="fade_up", background="#6856FF"),
                    Layer(new_id(), "closing_footer", text="WEB DESIGN  •  WEB APPS  •  CUSTOM SOLUTIONS", y=0.86, height=0.05, font_size=22, color="#AAB4D5", animation="fade"),
                ],
            ),
        ],
    )
    project.validate()
    return project
