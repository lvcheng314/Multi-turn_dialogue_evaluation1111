from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from dialogue_eval.schemas import RunSummary, TaskSpec


def init_archive(db_path: str | Path) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS eval_runs (
                run_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                task_name TEXT NOT NULL,
                model_name TEXT NOT NULL,
                status TEXT NOT NULL,
                total_score REAL NOT NULL,
                scenario_count INTEGER NOT NULL,
                report_md_path TEXT NOT NULL,
                report_html_path TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS eval_run_groups (
                group_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                task_name TEXT NOT NULL,
                model_name TEXT NOT NULL,
                latest_run_id TEXT NOT NULL,
                run_count INTEGER NOT NULL,
                best_score REAL NOT NULL,
                avg_score REAL NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


def archive_run(db_path: str | Path, task: TaskSpec, model_name: str, summary: RunSummary) -> None:
    init_archive(db_path)
    now = datetime.now(timezone.utc).isoformat()
    group_id = group_key(task.task_id, model_name)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO eval_runs
            (run_id, task_id, task_name, model_name, status, total_score, scenario_count,
             report_md_path, report_html_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                summary.run_id,
                task.task_id,
                task.task,
                model_name,
                summary.status,
                summary.total_score,
                summary.scenario_count,
                summary.report_markdown_path,
                summary.report_html_path,
                now,
            ),
        )
        scores = [
            row[0]
            for row in connection.execute(
                "SELECT total_score FROM eval_runs WHERE task_id = ? AND model_name = ?",
                (task.task_id, model_name),
            ).fetchall()
        ]
        connection.execute(
            """
            INSERT OR REPLACE INTO eval_run_groups
            (group_id, task_id, task_name, model_name, latest_run_id, run_count,
             best_score, avg_score, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                group_id,
                task.task_id,
                task.task,
                model_name,
                summary.run_id,
                len(scores),
                max(scores),
                sum(scores) / len(scores),
                now,
            ),
        )


def list_runs(db_path: str | Path, limit: int = 50) -> list[dict]:
    init_archive(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT * FROM eval_runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_groups(db_path: str | Path) -> list[dict]:
    init_archive(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT * FROM eval_run_groups ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def group_history(db_path: str | Path, task_id: str, model_name: str) -> list[dict]:
    init_archive(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT * FROM eval_runs
            WHERE task_id = ? AND model_name = ?
            ORDER BY created_at DESC
            """,
            (task_id, model_name),
        ).fetchall()
    return [dict(row) for row in rows]


def group_key(task_id: str, model_name: str) -> str:
    return f"{task_id}::{model_name}"
