# apis/__init__.py

from fastapi import APIRouter
from apis.v1 import auth, users, roles, tickets, actions, agent_config # ✅ Add agent_config

api_router = APIRouter()

# Include all route modules
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(roles.router, prefix="/roles", tags=["Roles"])
api_router.include_router(tickets.router, prefix="/tickets", tags=["Tickets"])
api_router.include_router(actions.router, prefix="/actions", tags=["Actions"])
# ✅ Add the new router
api_router.include_router(agent_config.router, prefix="/agent-config", tags=["Agent Configuration"])

__all__ = ["api_router"]