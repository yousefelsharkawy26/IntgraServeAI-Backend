# services/agent_config_service.py

import json
import shutil
import logging
import copy
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from uuid import UUID
from filelock import FileLock
from pydantic import ValidationError

from core.config import settings
from utils.exceptions import NotFoundException, BadRequestException, ServerException
from utils.schemas import agent_config_schemas as schemas
from services.ai_gateway_service import AIGatewayService

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
  "system_context": {
    "title": "IntgraServe AI Agent",
    "description": "AI-powered customer support assistant.",
    "version": "1.0.0",
    "tone": "Professional, helpful, and empathetic."
  },
  "global_defaults": None,
  "llm_config": {
    "location": "local",
    "provider": "ollama",
    "model_name": "llama3",
    "rate_limit_delay_seconds": 0,
    "temperature": 0.7,
    "max_tokens": 2048,
    "local_loading_params": {
      "base_url": "http://localhost:11434/v1",
      "gguf_file": "llama3.gguf",
      "context_window": 8192,
      "gpu_layers": 35,
      "quantization": "int4"
    },
    "system_prompt_template": "You are a helpful AI assistant."
  }
}

def deep_merge(source: dict, destination: dict) -> dict:
    """Recursively merges source dict into a deep copy of destination dict."""
    new_dest = copy.deepcopy(destination)
    for key, value in source.items():
        if isinstance(value, dict) and key in new_dest and isinstance(new_dest.get(key), dict):
            new_dest[key] = deep_merge(value, new_dest[key])
        else:
            new_dest[key] = value
    return new_dest

class AgentConfigService:
    def __init__(self):
        self.file_path = settings.AGENT_CONFIG_FILE_FULL_PATH
        self.backup_dir = settings.AGENT_CONFIG_BACKUP_DIR
        self.backup_enabled = settings.AGENT_CONFIG_BACKUP_ENABLED
        self.backup_count = settings.AGENT_CONFIG_BACKUP_COUNT
        self.lock_path = self.file_path.with_suffix('.lock')
        self._cache: Optional[Dict[str, Any]] = None
        self._ensure_file_and_dirs()

    def _ensure_file_and_dirs(self):
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            if self.backup_enabled:
                self.backup_dir.mkdir(parents=True, exist_ok=True)
            if not self.file_path.exists():
                logger.info(f"Config file not found. Creating default at {self.file_path}")
                self._save_data({"metadata": {}, **DEFAULT_CONFIG}, backup=False)
        except OSError as e:
            raise ServerException(f"Could not initialize configuration file: {e}")

    def _load_data(self) -> Dict[str, Any]:
        if self._cache is not None:
            return copy.deepcopy(self._cache)
        with FileLock(self.lock_path):
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    self._cache = json.load(f)
                return copy.deepcopy(self._cache)
            except (json.JSONDecodeError, FileNotFoundError) as e:
                self._ensure_file_and_dirs()
                return self._load_data()

    def _save_data(self, data: Dict[str, Any], backup: bool = True) -> Optional[str]:
        backup_filename = None
        if backup and self.backup_enabled:
            backup_filename = self._create_backup()
        with FileLock(self.lock_path):
            try:
                with open(self.file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False, default=str)
                self._cache = copy.deepcopy(data)
            except Exception as e:
                raise ServerException(f"Failed to write to configuration file: {e}")
        return backup_filename

    def _create_backup(self) -> str:
        if not self.file_path.exists(): return ""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"agent_config_backup_{ts}.json"
        try:
            shutil.copy2(self.file_path, backup_path)
            self._cleanup_old_backups()
            return backup_path.name
        except Exception as e:
            logger.warning(f"Failed to create backup: {e}")
            return ""

    def _cleanup_old_backups(self):
        try:
            backups = sorted(self.backup_dir.glob("agent_config_backup_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            for old in backups[self.backup_count:]: old.unlink()
        except Exception as e:
            logger.warning(f"Failed to clean up old backups: {e}")

    def get_full_config(self) -> Dict[str, Any]:
        return self._load_data()

    def get_section(self, section_name: str) -> Dict[str, Any]:
        config = self._load_data()
        if section_name not in config:
            raise NotFoundException(f"Section '{section_name}' not found.")
        return config.get(section_name)

    def update_full_config(self, config_data: Dict, updated_by: UUID) -> Optional[str]:
        try:
            validated_data = schemas.AgentConfig.model_validate(config_data).model_dump()
            full_data = {**validated_data, "metadata": {"last_updated": datetime.now(timezone.utc), "updated_by": updated_by}}
            result = self._save_data(full_data)

            AIGatewayService.reload_engine()

            return result
        except (ValueError, ValidationError) as e:
            raise BadRequestException(str(e))

    def update_section(self, section_name: str, update_data: Dict, updated_by: UUID) -> Optional[str]:
        current_config = self._load_data()

        current_section = current_config.get(section_name, {})
        if not isinstance(current_section, dict):
            current_section = {}

        merged_section = deep_merge(source=update_data, destination=current_section)
        current_config[section_name] = merged_section

        try:
            schemas.AgentConfig.model_validate(current_config)
        except (ValueError, ValidationError) as e:
            raise BadRequestException(f"Update for section '{section_name}' creates an invalid overall configuration: {e}")

        current_config.setdefault("metadata", {})["last_updated"] = datetime.now(timezone.utc)
        current_config["metadata"]["updated_by"] = updated_by

        AIGatewayService.reload_engine()

        return self._save_data(current_config)

    def list_backups(self) -> List[Dict[str, Any]]:
        if not self.backup_dir.exists(): return []
        files = sorted(self.backup_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        return [{"filename": p.name, "created_at": datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc), "size_kb": round(p.stat().st_size / 1024, 2)} for p in files]

    def get_backup_content(self, filename: str) -> Dict[str, Any]:
        path = self.backup_dir / filename
        if not path.is_file(): raise NotFoundException(f"Backup '{filename}' not found.")
        with open(path, 'r', encoding='utf-8') as f: return json.load(f)

    def restore_from_backup(self, filename: str, updated_by: UUID) -> Tuple[str, str]:
        content = self.get_backup_content(filename)
        try:
            validated = schemas.AgentConfig.model_validate(content)
        except (ValueError, ValidationError) as e:
            raise BadRequestException(f"Backup '{filename}' has invalid structure: {e}")

        current_backup = self._create_backup()
        content.setdefault("metadata", {})["last_updated"] = datetime.now(timezone.utc)
        content["metadata"]["updated_by"] = updated_by
        content["metadata"]["restored_from"] = filename
        self._save_data(content, backup=False)

        AIGatewayService.reload_engine()

        return filename, current_backup

    def delete_backup(self, filename: str) -> None:
        path = self.backup_dir / filename
        if not path.is_file(): raise NotFoundException(f"Backup '{filename}' not found.")
        path.unlink()

    def delete_all_backups(self) -> int:
        if not self.backup_dir.exists(): return 0
        files = list(self.backup_dir.glob("*.json"))
        for file in files: file.unlink()
        return len(files)
