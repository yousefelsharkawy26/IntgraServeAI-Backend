from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
from utils.security import validate_password_strength


class LoginRequest(BaseModel):
    """Login request schema"""
    email: EmailStr = Field(..., description="User email address", max_length=255)
    password: str = Field(
        ...,
        description="User password",
        min_length=8,
        max_length=128
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com",
                "password": "userpassword123"
            }
        }


class TokenResponse(BaseModel):
    """Token response schema - only access token in body"""
    token: str = Field(..., description="JWT access token")
    
    class Config:
        json_schema_extra = {
            "example": {
                "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
            }
        }


class ForgotPasswordRequest(BaseModel):
    """Forgot password request schema"""
    email: EmailStr = Field(..., description="Registered email address", max_length=255)
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com"
            }
        }


class ForgotPasswordResponse(BaseModel):
    """Forgot password response schema"""
    message: str = Field(..., description="Success message")
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "Password reset Link have been sent to your email."
            }
        }


class ResetPasswordRequest(BaseModel):
    """Reset password request schema"""
    new_password: str = Field(
        ...,
        description="New password",
        min_length=8,
        max_length=128
    )
    
    @field_validator('new_password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        is_valid, error_message = validate_password_strength(v)
        if not is_valid:
            raise ValueError(error_message)
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "new_password": "newpassword123"
            }
        }


class ResetPasswordResponse(BaseModel):
    """Reset password response schema"""
    message: str = Field(..., description="Success message")
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "Password has been reset successfully."
            }
        }


class MessageResponse(BaseModel):
    """Generic message response"""
    message: str = Field(..., description="Response message")


class ValidationErrorResponse(BaseModel):
    """Validation error response schema"""
    errors: dict = Field(..., description="Validation errors")
    
    class Config:
        json_schema_extra = {
            "example": {
                "errors": {
                    "email": "Invalid email format",
                    "password": "Password must be at least 8 characters long"
                }
            }
        }