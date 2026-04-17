# services/agent_config_service.py

import json
import shutil
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from uuid import UUID
from filelock import FileLock
from pydantic import ValidationError

from core.config import settings
from utils.exceptions import NotFoundException, BadRequestException, ServerException, ValidationException
from utils.schemas import agent_config_schemas as schemas

logger = logging.getLogger(__name__)

# Default config for the first run
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

VALID_SECTIONS = ["system_context", "global_defaults", "llm_config"]
UPDATE_SCHEMAS = {
    "system_context": schemas.SystemContextUpdate,
    "global_defaults": schemas.GlobalDefaultsUpdate,
    "llm_config": schemas.LLMConfigUpdate,
}


def deep_merge(source: dict, destination: dict) -> dict:
    """Recursively merge source dict into destination dict."""
    for key, value in source.items():
        if isinstance(value, dict):
            node = destination.setdefault(key, {})
            deep_merge(value, node)
        else:
            destination[key] = value
    return destination


class AgentConfigService:
    """Service for managing AI Agent configuration file."""

    def __init__(self):
        self.file_path = settings.AGENT_CONFIG_FILE_FULL_PATH
        self.backup_dir = settings.AGENT_CONFIG_BACKUP_DIR
        self.backup_enabled = settings.AGENT_CONFIG_BACKUP_ENABLED
        self.backup_count = settings.AGENT_CONFIG_BACKUP_COUNT
        self.lock_path = self.file_path.with_suffix('.lock')
        self._ensure_file_and_dirs()

    def _ensure_file_and_dirs(self):
        """Ensure config file and directories exist."""
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            if self.backup_enabled:
                self.backup_dir.mkdir(parents=True, exist_ok=True)

            if not self.file_path.exists():
                logger.info(f"Config file not found. Creating default at {self.file_path}")
                default_data = {
                    **DEFAULT_CONFIG,
                    "metadata": {
                        "last_updated": None,
                        "updated_by": None,
                    }
                }
                self._save_data(default_data, backup=False)
        except OSError as e:
            logger.error(f"Failed to create directories or file: {e}")
            raise ServerException("Could not initialize configuration file.")

    def _load_data(self) -> Dict[str, Any]:
        """Load data from JSON file with a lock."""
        with FileLock(self.lock_path):
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError) as e:
                logger.error(f"Error loading config file: {e}. Re-initializing.")
                self._ensure_file_and_dirs()
                return self._load_data()

    def _save_data(self, data: Dict[str, Any], backup: bool = True) -> Optional[str]:
        """Save data to JSON file with a lock and optional backup."""
        backup_filename = None
        if backup and self.backup_enabled:
            backup_filename = self._create_backup()

        with FileLock(self.lock_path):
            try:
                with open(self.file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False, default=str)
                logger.info("Agent config saved successfully.")
            except Exception as e:
                logger.error(f"Failed to save agent config: {e}")
                raise ServerException("Failed to write to configuration file.")
        
        return backup_filename

    def _create_backup(self) -> str:
        """Create a backup of the current config file."""
        if not self.file_path.exists():
            return ""
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"agent_config_backup_{timestamp}.json"
        backup_path = self.backup_dir / backup_name
        
        try:
            shutil.copy2(self.file_path, backup_path)
            logger.info(f"Backup created: {backup_path}")
            self._cleanup_old_backups()
            return backup_name
        except Exception as e:
            logger.warning(f"Failed to create backup: {e}")
            return ""

    def _cleanup_old_backups(self):
        """Remove old backups, keeping the configured amount."""
        try:
            backups = sorted(
                self.backup_dir.glob("agent_config_backup_*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True
            )
            if len(backups) > self.backup_count:
                for old_backup in backups[self.backup_count:]:
                    old_backup.unlink()
                    logger.info(f"Removed old backup: {old_backup.name}")
        except Exception as e:
            logger.warning(f"Failed to clean up old backups: {e}")

    # --- Public Methods ---

    def get_full_config(self) -> Dict[str, Any]:
        """Return the entire configuration."""
        return self._load_data()

    def get_section(self, section_name: str) -> Dict[str, Any]:
        """Return a specific section of the configuration."""
        if section_name not in VALID_SECTIONS:
            raise NotFoundException(f"Section '{section_name}' not found. Valid sections are: {', '.join(VALID_SECTIONS)}")
        
        config = self._load_data()
        section_content = config.get(section_name)
        
        if section_content is None:
            raise NotFoundException(f"Section '{section_name}' is not configured.")
            
        return section_content

    def update_full_config(self, config_data: Dict, updated_by: UUID) -> Optional[str]:
        """Validate and replace the entire configuration."""
        try:
            validated_config = schemas.AgentConfig(**config_data).model_dump(mode="json")
            full_data = {
                **validated_config,
                "metadata": {
                    "last_updated": datetime.now(timezone.utc),
                    "updated_by": updated_by,
                }
            }
            return self._save_data(full_data)
        except ValidationError as e:
            raise ValidationException(errors=e.errors())

    def update_section(self, section_name: str, update_data: Dict, updated_by: UUID) -> Optional[str]:
        """Update a specific section of the configuration."""
        if section_name not in VALID_SECTIONS:
            raise NotFoundException(f"Section '{section_name}' not found. Valid sections are: {', '.join(VALID_SECTIONS)}")

        # Validate incoming data against the specific update schema
        update_schema = UPDATE_SCHEMAS[section_name]
        try:
            validated_update = update_schema(**update_data).model_dump(exclude_unset=True)
        except ValidationError as e:
            raise ValidationException(errors=e.errors())

        if not validated_update:
            raise BadRequestException("No valid data provided for update.")

        current_config = self._load_data()
        
        # Deep merge the validated update into the current section
        current_section = current_config.get(section_name, {})
        # If the current section is None (e.g. global_defaults), initialize it as a dict
        if current_section is None:
            current_section = {}
            
        merged_section = deep_merge(validated_update, current_section)
        current_config[section_name] = merged_section

        # Validate the entire config after merging to ensure consistency
        try:
            schemas.AgentConfig(**current_config).model_dump()
        except ValidationError as e:
            logger.error(f"Post-merge validation failed: {e}")
            raise BadRequestException(f"Update for section '{section_name}' creates an invalid overall configuration.")

        # Update metadata and save
        current_config["metadata"]["last_updated"] = datetime.now(timezone.utc)
        current_config["metadata"]["updated_by"] = updated_by
        
        return self._save_data(current_config)

    def list_backups(self) -> List[Dict[str, Any]]:
        """List all available backups."""
        if not self.backup_dir.exists():
            return []

        backup_files = sorted(
            self.backup_dir.glob("agent_config_backup_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        
        return [
            {
                "filename": p.name,
                "created_at": datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc),
                "size_kb": round(p.stat().st_size / 1024, 2)
            } for p in backup_files
        ]

    def get_backup_content(self, filename: str) -> Dict[str, Any]:
        """Get the content of a specific backup file."""
        backup_path = self.backup_dir / filename
        if not backup_path.exists() or not backup_path.is_file():
            raise NotFoundException(f"Backup '{filename}' not found.")
        
        with open(backup_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def restore_from_backup(self, filename: str, updated_by: UUID) -> Tuple[str, str]:
        """Restore config from a backup file."""
        backup_content = self.get_backup_content(filename)
        
        # Check if backup is valid
        try:
            validated_backup = schemas.AgentConfig(**backup_content).model_dump(mode="json")
        except ValidationError as e:
            raise BadRequestException(f"Backup file '{filename}' has an invalid structure: {e}")

        # Create backup of current state before restoring
        current_backup_name = self._create_backup()

        # Update metadata and save
        restored_data = {
            **validated_backup,
            "metadata": {
                "last_updated": datetime.now(timezone.utc),
                "updated_by": updated_by,
                "restored_from": filename
            }
        }
        self._save_data(restored_data, backup=False)

        return filename, current_backup_name