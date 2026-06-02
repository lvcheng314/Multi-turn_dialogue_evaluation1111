from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from dialogue_eval.storage.jsonl import append_jsonl


class RunStore:
    def __init__(self, runs_dir: str | Path) -> None:
        self.runs_dir = Path(runs_dir)
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        path = self.runs_dir / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_json(self, run_id: str, name: str, value: BaseModel | list[BaseModel] | dict) -> Path:
        path = self.run_dir(run_id) / name
        if isinstance(value, list):
            payload = [
                item.model_dump(mode="json") if isinstance(item, BaseModel) else item
                for item in value
            ]
        elif isinstance(value, BaseModel):
            payload = value.model_dump(mode="json")
        else:
            payload = value
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def append_trace(self, run_id: str, value: BaseModel) -> Path:
        path = self.run_dir(run_id) / "trace.jsonl"
        append_jsonl(path, value)
        return path

    def write_text(self, run_id: str, name: str, content: str) -> Path:
        path = self.run_dir(run_id) / name
        path.write_text(content, encoding="utf-8")
        return path
