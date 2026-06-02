from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel


def append_jsonl(path: Path, item: BaseModel | dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = item.model_dump(mode="json") if isinstance(item, BaseModel) else item
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                yield json.loads(line)
