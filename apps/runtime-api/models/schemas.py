"""
Pydantic schemas for API
"""
from typing import List, Optional
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
    mode: str
    title: str
    models: List[str]
    createdAt: str
    updatedAt: str
    messageCount: int


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
