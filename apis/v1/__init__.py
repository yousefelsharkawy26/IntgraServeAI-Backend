# apis/v1/__init__.py
from fastapi import APIRouter
from apis.v1 import auth, users, roles, tickets

__all__ = ["auth", "users", "roles", "tickets"]