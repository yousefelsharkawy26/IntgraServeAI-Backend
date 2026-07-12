# utils/ai_config_adapter.py

import json
from pathlib import Path
from typing import List, Dict, Any


class AIConfigAdapter:
    """
    Loads the remaining file-based agent configuration. Action persistence is
    handled exclusively by the ActionRepository.
    """

    @staticmethod
    def load_agent_config_for_engine(config_file_path: str) -> Dict[str, Any]:
        path = Path(config_file_path)
        if not path.exists():
            return {}

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)