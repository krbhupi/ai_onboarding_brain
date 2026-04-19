"""FastAPI application entry point."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import get_settings
from config.logging import logger
from src.core.database import init_db, close_db

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    logger.info("Starting HR Automation application...")
    await init_db()
    logger.info("Database initialized")
    yield
    logger.info("Shutting down HR Automation application...")
    await close_db()
    logger.info("Database connections closed")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="AI-driven HR onboarding automation system",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION
    }


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "HR Automation API",
        "docs": "/docs",
        "health": "/health"
    }


# Include routers
from src.controller import candidate, documents, jobs, email, auth
app.include_router(candidate.router, prefix="/api/candidates", tags=["candidates"])
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(email.router, prefix="/api/email", tags=["email"])
app.include_router(auth.router, prefix="/auth", tags=["authentication"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )