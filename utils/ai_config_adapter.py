# utils/ai_config_adapter.py

import json
from pathlib import Path
from typing import List, Dict, Any


class AIConfigAdapter:
    """
    Adapts the backend's actions.json (dict-of-dicts with metadata wrapper)
    to the AI Engine's expected flat list format.
    """

    @staticmethod
    def load_actions_for_engine(actions_file_path: str) -> List[Dict[str, Any]]:
        path = Path(actions_file_path)
        if not path.exists():
            return []

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        actions_dict = data.get("actions", {})
        actions_list = []

        for action_id, action in actions_dict.items():
            action_copy = dict(action)
            action_copy["_backend_id"] = action_id
            actions_list.append(action_copy)

        return actions_list

    @staticmethod
    def load_agent_config_for_engine(config_file_path: str) -> Dict[str, Any]:
        path = Path(config_file_path)
        if not path.exists():
            return {}

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)