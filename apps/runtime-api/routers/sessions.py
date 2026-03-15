"""
Sessions API - Session management
"""
from fastapi import APIRouter
from models import MOCK_SESSIONS

router = APIRouter(tags=["sessions"])


@router.get("/sessions")
async def get_sessions():
    """Get all sessions"""
    return {
        "sessions": MOCK_SESSIONS,
        "total": len(MOCK_SESSIONS),
    }


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get specific session"""
    for session in MOCK_SESSIONS:
        if session["id"] == session_id:
            return session
    return {"error": "Session not found"}, 404
