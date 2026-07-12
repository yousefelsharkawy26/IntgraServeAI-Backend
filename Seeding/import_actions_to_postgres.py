"""One-time importer for the legacy Action Registry export.

Usage after running Alembic:
    python Seeding/import_actions_to_postgres.py
    python Seeding/import_actions_to_postgres.py /path/to/legacy-export.json

Without an argument, the utility imports the frozen export bundled in
``Seeding.legacy_action_data``. The import is atomic and idempotent by action ID. Nested configuration objects
are assigned directly to JSONB columns without renaming or reshaping.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.database import AsyncSessionLocal  # noqa: E402
from repositories.action_repository import ActionRepository  # noqa: E402
from Seeding.legacy_action_data import LEGACY_ACTIONS  # noqa: E402

PERSISTED_FIELDS = {
    "name",
    "description",
    "type",
    "active",
    "requires_confirmation",
    "requires_human_input",
    "execution_config",
    "parameters",
    "response_config",
}
REQUIRED_FIELDS = {"name", "description", "type"}


def extract_actions(document: Any) -> dict[str, dict[str, Any]]:
    if isinstance(document, dict) and isinstance(document.get("actions"), dict):
        return document["actions"]
    if isinstance(document, dict):
        return document
    if isinstance(document, list):
        result = {}
        for item in document:
            if not isinstance(item, dict) or "id" not in item:
                raise ValueError("Every action in a list export must contain an id")
            result[item["id"]] = {key: value for key, value in item.items() if key != "id"}
        return result
    raise ValueError("The source must contain an action object or action list")


def persistence_values(action_id: str, action: dict[str, Any]) -> dict[str, Any]:
    missing = REQUIRED_FIELDS - action.keys()
    unknown = action.keys() - PERSISTED_FIELDS
    if missing:
        raise ValueError(f"{action_id}: missing fields: {sorted(missing)}")
    if unknown:
        # Refuse silent information loss if a future export has new fixed fields.
        raise ValueError(f"{action_id}: unmapped fields: {sorted(unknown)}")
    return {
        "name": action["name"],
        "description": action["description"],
        "type": action["type"],
        "active": action.get("active", True),
        "requires_confirmation": action.get("requires_confirmation", False),
        "requires_human_input": action.get("requires_human_input", False),
        "execution_config": action.get("execution_config"),
        "parameters": action.get("parameters"),
        "response_config": action.get("response_config"),
    }


async def import_actions(source: Path | None = None) -> int:
    document = json.loads(source.read_text(encoding="utf-8")) if source else LEGACY_ACTIONS
    actions = extract_actions(document)
    async with AsyncSessionLocal() as session:
        repository = ActionRepository(session)
        try:
            for action_id, action in actions.items():
                if not isinstance(action, dict):
                    raise ValueError(f"{action_id}: action must be an object")
                await repository.upsert(action_id, persistence_values(action_id, action))
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    return len(actions)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a legacy Action Registry export into PostgreSQL")
    parser.add_argument("source", nargs="?", type=Path, help="Optional path to a legacy JSON export")
    args = parser.parse_args()
    count = asyncio.run(import_actions(args.source))
    print(f"Imported {count} actions into PostgreSQL")


if __name__ == "__main__":
    main()
