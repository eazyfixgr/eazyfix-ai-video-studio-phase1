"""Project persistence, portable sidecar assets, and crash-safe writes."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from uuid import uuid4

from .models import Asset, Project


def project_asset_directory(project_path: str | Path) -> Path:
    path = Path(project_path)
    return path.with_name(f"{path.stem}_assets")


def save_project(project: Project, project_path: str | Path) -> None:
    project.validate()
    path = Path(project_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    asset_dir = project_asset_directory(path)
    asset_dir.mkdir(parents=True, exist_ok=True)
    serialized_paths: dict[str, str] = {}
    for asset in project.assets:
        source = Path(asset.path).expanduser()
        if not source.is_file():
            raise FileNotFoundError(f"Cannot save missing asset: {asset.name}")
        target_name = f"{asset.id}_{source.name}"
        target = asset_dir / target_name
        if source.resolve() != target.resolve():
            source_info = source.stat()
            target_info = target.stat() if target.exists() else None
            if not target_info or source_info.st_size != target_info.st_size or source_info.st_mtime_ns != target_info.st_mtime_ns:
                shutil.copy2(source, target)
        serialized_paths[asset.id] = f"{asset_dir.name}/{target_name}"

    payload = project.to_dict(serialized_paths)
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def load_project(project_path: str | Path) -> Project:
    path = Path(project_path).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Project file must contain a JSON object.")
    asset_dir = path.parent
    for raw in payload.get("assets", []):
        asset_path = Path(raw.get("path", ""))
        if not asset_path.is_absolute():
            raw["path"] = str((asset_dir / asset_path).resolve())
    project = Project.from_dict(payload)
    for asset in project.assets:
        if not Path(asset.path).is_file():
            # Keep missing assets visible in the asset manager so users can relink them.
            continue
    return project


def autosave_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "EazyFixAIStudio"
    base.mkdir(parents=True, exist_ok=True)
    return base / "recovery.eazyproj"


def import_asset(source_path: str | Path, asset: Asset, destination: str | Path) -> Asset:
    """Copy an imported file into managed storage, retaining the original file."""
    source = Path(source_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    target_dir = Path(destination).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{asset.id}_{source.name}"
    if source != target:
        shutil.copy2(source, target)
    asset.path = str(target)
    asset.name = source.name
    return asset
