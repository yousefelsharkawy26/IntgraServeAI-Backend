# apis/v1/__init__.py

from fastapi import APIRouter
from apis.v1 import auth, users, roles, tickets, actions, agent_config # ✅ Add agent_config

# ✅ Add agent_config to the list
__all__ = ["auth", "users", "roles", "tickets", "actions", "agent_config"]