# apis/__init__.py
from fastapi import APIRouter
from apis.v1 import auth, users, roles, tickets

api_router = APIRouter()

# Include all route modules
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(roles.router, prefix="/roles", tags=["Roles"])
api_router.include_router(tickets.router, prefix="/tickets", tags=["Tickets"])

__all__ = ["api_router"]