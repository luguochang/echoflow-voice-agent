"""Configuration-related data models."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ConfigData(BaseModel):
    """Configuration payload returned by ConfigManager."""

    section: Optional[str] = None
    content: Dict[str, Any] = Field(default_factory=dict)


class ModuleStatusData(BaseModel):
    """Status payload for an initialized or missing module."""

    status: str
    module_id: Optional[str] = None
    module_type: Optional[str] = None
    initialized: bool = False
    error: Optional[str] = None
