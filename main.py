# main.py
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from contextlib import asynccontextmanager
import time
import logging
from core.config import settings
from apis import api_router
from ai_engine.vector_search import EmbeddingProviderError
from utils.exceptions import (
    BaseAPIException,
    AuthenticationException,
    ValidationException,
    InvalidTokenException
)

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    logger.info("🚀 Application starting...")
    
    # Validate embedding providers on startup (deduplicated and lightweight)
    try:
        from ai_engine.action_engine import ActionEngine
        from ai_engine.vector_search import validate_embedding_provider
        from services.ai_gateway_service import AIGatewayService
        
        await AIGatewayService.reload_engine()
        engine = AIGatewayService.get_engine()
        
        # Deduplicate configurations by (provider, base_url, model_name)
        unique_configs = {}
        for action in engine.actions:
            if action.type == "vector_query" and action.execution_config:
                embedding_config = action.execution_config.embedding_config
                if embedding_config:
                    # Create a unique key for this configuration
                    config_key = f"{embedding_config.provider}:{getattr(embedding_config, 'base_url', 'default')}:{embedding_config.model_name}"
                    if config_key not in unique_configs:
                        unique_configs[config_key] = {
                            'config': embedding_config,
                            'actions': []
                        }
                    unique_configs[config_key]['actions'].append(action.name)
        
        validated_count = 0
        warning_count = 0
        
        # Validate each unique configuration only once
        for config_key, config_data in unique_configs.items():
            embedding_config = config_data['config']
            action_names = config_data['actions']
            
            try:
                await validate_embedding_provider(embedding_config)
                logger.info(f"✅ Embedding provider validated: {config_key}")
                logger.info(f"   Used by {len(action_names)} action(s): {', '.join(action_names[:3])}{'...' if len(action_names) > 3 else ''}")
                validated_count += 1
            except EmbeddingProviderError as e:
                logger.warning(f"⚠️  Embedding provider validation failed: {config_key}")
                logger.warning(f"   Error: {e}")
                logger.warning(f"   {len(action_names)} action(s) may fail at runtime: {', '.join(action_names[:3])}{'...' if len(action_names) > 3 else ''}")
                warning_count += 1
        
        if validated_count > 0:
            logger.info(f"✅ Validated {validated_count} unique embedding provider configuration(s)")
        if warning_count > 0:
            logger.warning(f"⚠️  {warning_count} embedding provider configuration(s) failed validation")
            
    except EmbeddingProviderError as e:
        logger.error(f"❌ Failed to validate embedding providers: {e}")
        logger.error("   Vector search actions may fail at runtime.")
    
    logger.info("🚀 Application started successfully")
    
    # Warn if DEBUG is enabled in a non-local environment (stack-trace exposure risk)
    if settings.DEBUG and "localhost" not in settings.BASE_URL.lower():
        logger.warning("⚠️  DEBUG=True is set in a non-local environment (BASE_URL=%s). This exposes stack traces and sensitive details in error responses. Set DEBUG=False for production.", settings.BASE_URL)
    
    yield
    logger.info("🛑 Application shutdown complete")


# Initialize FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-Powered Customer Support System API",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins= ["https://intgra-serve-ai-front.vercel.app", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request timing middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    if settings.DEBUG:
        response.headers["X-Process-Time"] = str(f"{process_time:.4f} sec")
    return response


# ✅ Custom Exception Handlers - بدون detail wrapper

@app.exception_handler(BaseAPIException)
async def base_api_exception_handler(request: Request, exc: BaseAPIException):
    """Handle all custom API exceptions"""
    # exc.detail already contains the correct format from our custom exceptions
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail  # ✅ نرجع الـ detail مباشرة (يحتوي على message أو errors)
    )


@app.exception_handler(AuthenticationException)
async def authentication_exception_handler(request: Request, exc: AuthenticationException):
    """Handle authentication errors"""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail
    )


@app.exception_handler(ValidationException)
async def validation_exception_handler_custom(request: Request, exc: ValidationException):
    """Handle custom validation errors"""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail
    )


@app.exception_handler(InvalidTokenException)
async def invalid_token_exception_handler(request: Request, exc: InvalidTokenException):
    """Handle invalid token errors"""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.detail
    )


# ✅ Pydantic Validation Error Handler
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic validation errors"""
    errors = {}
    for error in exc.errors():
        field = error["loc"][-1] if error["loc"] else "unknown"
        message = error["msg"]
        
        # Custom error messages
        if error["type"] == "value_error.email" or "email" in error["type"]:
            message = "Invalid email format"
        elif "string_too_short" in error["type"] or "min_length" in str(error["type"]):
            ctx = error.get("ctx", {})
            min_length = ctx.get("min_length", 8)
            message = f"Password must be at least {min_length} characters long"
        elif "string_too_long" in error["type"] or "max_length" in str(error["type"]):
            ctx = error.get("ctx", {})
            max_length = ctx.get("max_length", 255)
            message = f"Maximum length is {max_length} characters"
        elif "missing" in error["type"]:
            message = "This field is required"
        
        errors[field] = message
    
    # ✅ Return errors directly without detail wrapper
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"errors": errors}
    )


# ✅ Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle unexpected errors"""
    logger.error(f"Unexpected error: {exc}", exc_info=True)
    
    # ✅ Return message directly without detail wrapper
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "message": "Internal server error" if not settings.DEBUG else str(exc)
        }
    )


# Health check endpoints
@app.get("/", tags=["Health"])
async def root():
    return {
        "success": True,
        "message": f"Welcome to {settings.APP_NAME}",
        "version": settings.APP_VERSION,
        "status": "running"
    }


@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "success": True,
        "status": "healthy",
        "version": settings.APP_VERSION
    }


# Include API routes
app.include_router(api_router, prefix="/api/v1")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info"
    )
