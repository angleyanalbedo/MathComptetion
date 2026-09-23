"""Serialization for the official multicore-plan interface."""

from __future__ import annotations

import json
from pathlib import Path


def official_plan(node_to_subgraph: dict[int, int], core_schedules: list[list[int]]) -> dict:
    return {
        "node_to_subgraph": {str(op_id): node_to_subgraph[op_id] for op_id in sorted(node_to_subgraph)},
        "core_schedules": core_schedules,
    }


def write_plan(plan: dict, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
