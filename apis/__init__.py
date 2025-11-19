from fastapi import APIRouter
from apis.v1 import users, tickets, chat, system, auth

api_router = APIRouter()

# Include all route modules
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(tickets.router, prefix="/tickets", tags=["Tickets"])
api_router.include_router(chat.router, prefix="/chat", tags=["Chat"])
api_router.include_router(system.router, prefix="/system", tags=["System"])

__all__ = ["api_router"]