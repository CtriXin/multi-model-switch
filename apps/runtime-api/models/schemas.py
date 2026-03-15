"""
Pydantic schemas for API
"""
from typing import List, Optional, Literal
from pydantic import BaseModel
from datetime import datetime


# ============================================================================
# Model Schemas
# ============================================================================

class ModelMeta(BaseModel):
    id: str
    name: str
    provider: str
    category: str
    tier: int
    priceInput: float
    priceOutput: float
    tags: List[str]
    contextWindow: int


class Preset(BaseModel):
    id: str
    name: str
    models: List[str]
    builtin: bool
    icon: Optional[str] = None


# ============================================================================
# Provider & Account Schemas
# ============================================================================

class ProviderConfig(BaseModel):
    id: str
    name: str
    enabled: bool
    hasOAuth: bool
    hasApiKey: bool
    baseUrl: Optional[str] = None


class AccountInfo(BaseModel):
    id: str
    provider: str
    name: str
    email: Optional[str] = None
    avatar: Optional[str] = None
    isActive: bool


# ============================================================================
# Session Schemas
# ============================================================================

class Session(BaseModel):
    id: str
    mode: Literal["chat", "discuss"]
    title: str
    models: List[str]
    createdAt: str
    updatedAt: str
    messageCount: int


# ============================================================================
# Chat Schemas
# ============================================================================

class Brief(BaseModel):
    approach: str
    reasoning: str
    risks: List[str]
    keyDecisions: List[str]
    nextStep: str


class ChatRequest(BaseModel):
    models: List[str]
    prompt: str
    sessionId: Optional[str] = None
    images: Optional[List[str]] = None


class ChatResponse(BaseModel):
    model: str
    content: str
    displayText: str
    brief: Optional[Brief] = None
    elapsed: float
    status: str
    error: Optional[str] = None
    timestamp: str


# ============================================================================
# Discuss Schemas
# ============================================================================

class DiscussRequest(BaseModel):
    models: List[str]
    prompt: str
    cross: bool = True
    sessionId: Optional[str] = None


class Phase1Summary(BaseModel):
    model: str
    ok: bool
    brief: Optional[Brief] = None
    content: Optional[str] = None
    error: Optional[str] = None
    elapsed: float


class Phase2Review(BaseModel):
    reviewer: str
    target: str
    ok: bool
    agreement: Optional[str] = None
    challenge: Optional[str] = None
    betterOption: Optional[str] = None
    error: Optional[str] = None
    skipped: bool = False


class Phase3Synthesis(BaseModel):
    synthesizer: str
    content: str
    elapsed: float


# ============================================================================
# Bootstrap Schema
# ============================================================================

class BootstrapConfig(BaseModel):
    version: str
    features: List[str]
    providers: List[ProviderConfig]
    accounts: List[AccountInfo]
    presets: List[Preset]
    limits: dict
