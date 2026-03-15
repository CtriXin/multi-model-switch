"""
MMS Runtime API
FastAPI server for web app integration
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from routers import bootstrap, models, sessions, chat, discuss


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    print("🚀 MMS Runtime API starting...")
    yield
    # Shutdown
    print("🛑 MMS Runtime API shutting down...")


app = FastAPI(
    title="MMS Runtime API",
    description="Multi-Model Switch Runtime API for Web App",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:5188", "http://127.0.0.1:5188",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(bootstrap.router, prefix="/api")
app.include_router(models.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(discuss.router, prefix="/api")


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "0.1.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
