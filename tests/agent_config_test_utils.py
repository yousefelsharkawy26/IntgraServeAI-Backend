import json
from pathlib import Path
from typing import Any


def load_agent_config(value: Any) -> Any:
    """Load test fixture data before passing it to the database-driven engine."""
    if isinstance(value, dict):
        return value
    return json.loads(Path(value).read_text(encoding="utf-8"))
