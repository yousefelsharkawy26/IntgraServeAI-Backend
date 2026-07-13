# apis/v1/__init__.py

from fastapi import APIRouter
from apis.v1 import auth, users, roles, tickets, actions, agent_config, llm_configs

__all__ = ["auth", "users", "roles", "tickets", "actions", "agent_config", "llm_configs"]