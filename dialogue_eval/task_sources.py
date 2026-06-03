from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import TypedDict

from dialogue_eval.parser import load_task

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_LIBRARY_DIR = PROJECT_ROOT / "tasks"
TASK_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
SUPPORTED_TASK_SUFFIXES = {".json", ".xlsx", ".xls"}


class TaskSourceEntry(TypedDict):
    id: str
    name: str
    file_name: str
    path: str


class UploadedTaskResult(TypedDict):
    status: str
    file_name: str
    path: str
    duplicate_of: TaskSourceEntry | None


def list_task_sources() -> list[TaskSourceEntry]:
    entries: list[TaskSourceEntry] = []
    for path in sorted(TASK_LIBRARY_DIR.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_TASK_SUFFIXES:
            continue
        try:
            task = load_task(path)
            task_id = task.task_id
            name = task.task
        except Exception:
            task_id = path.stem
            name = path.stem
        entries.append(
            {
                "id": task_id,
                "name": name,
                "file_name": path.name,
                "path": str(path),
            }
        )
    return entries


def task_sources_map() -> dict[str, TaskSourceEntry]:
    return {entry["id"]: entry for entry in list_task_sources()}


def resolve_task_path(task_source_id: str) -> Path:
    try:
        return Path(task_sources_map()[task_source_id]["path"])
    except KeyError as exc:
        raise KeyError(f"Unknown task source: {task_source_id}") from exc


def store_uploaded_task(filename: str, content: bytes) -> Path:
    inspection = inspect_uploaded_task(filename, content)
    if inspection["status"] == "duplicate":
        duplicate = inspection["duplicate_of"]
        if duplicate is None:
            raise RuntimeError("Duplicate task result is missing duplicate_of metadata")
        return Path(duplicate["path"])
    path = Path(inspection["path"])
    path.write_bytes(content)
    return path


def load_uploaded_task_content(filename: str, content: bytes):
    suffix = Path(filename).suffix.lower() or ".json"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
        temp.write(content)
        temp_path = Path(temp.name)
    try:
        return load_task(temp_path)
    finally:
        temp_path.unlink(missing_ok=True)


def inspect_uploaded_task(filename: str, content: bytes) -> UploadedTaskResult:
    duplicate = _find_duplicate_task(filename, content)
    if duplicate is not None:
        return {
            "status": "duplicate",
            "file_name": duplicate["file_name"],
            "path": duplicate["path"],
            "duplicate_of": duplicate,
        }

    path = _unique_task_path(filename)
    return {
        "status": "new",
        "file_name": path.name,
        "path": str(path),
        "duplicate_of": None,
    }


def _unique_task_path(filename: str) -> Path:
    source = Path(filename)
    safe_name = source.name or "task.json"
    stem = source.stem or "task"
    suffix = source.suffix.lower() or ".json"
    if suffix not in SUPPORTED_TASK_SUFFIXES:
        raise ValueError(f"Unsupported task file type: {suffix}")

    target = TASK_LIBRARY_DIR / safe_name
    if not target.exists():
        return target

    for index in range(1, 1000):
        candidate = TASK_LIBRARY_DIR / f"{stem}-{index:03d}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError("Unable to allocate a unique task filename")


def _find_duplicate_task(filename: str, content: bytes) -> TaskSourceEntry | None:
    semantic_fingerprint = _task_fingerprint_from_content(filename, content)
    target_digest = hashlib.sha256(content).hexdigest()
    for entry in list_task_sources():
        path = Path(entry["path"])
        if not path.exists() or not path.is_file():
            continue
        existing_fingerprint = _task_fingerprint_from_path(path)
        if semantic_fingerprint is not None and existing_fingerprint == semantic_fingerprint:
            return entry
        if hashlib.sha256(path.read_bytes()).hexdigest() == target_digest:
            return entry
    return None


def _task_fingerprint_from_content(filename: str, content: bytes) -> str | None:
    try:
        task = load_uploaded_task_content(filename, content)
    except Exception:
        return None
    normalized = json.dumps(task.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _task_fingerprint_from_path(path: Path) -> str | None:
    try:
        task = load_task(path)
    except Exception:
        return None
    normalized = json.dumps(task.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
