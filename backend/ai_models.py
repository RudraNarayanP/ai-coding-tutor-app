from typing import Any
from pydantic import BaseModel, Field

from .lesson_models import TestResult


class TutorRequest(BaseModel):
    lesson_id: str = Field(min_length=1, max_length=80)
    lesson_title: str = Field(min_length=1, max_length=120)
    unit_title: str = Field(default="", max_length=120)
    concept_title: str = Field(default="", max_length=120)
    prerequisites: list[str] = Field(default_factory=list, max_length=20)
    instructions: str = Field(min_length=1, max_length=2000)
    code: str = Field(max_length=64 * 1024)
    test_results: list[TestResult] = Field(max_length=20)
    previous_hints: list[str] = Field(default_factory=list, max_length=8)
    hint_level: int = Field(ge=1, le=4)
    session_id: str = Field(default="default", min_length=1, max_length=80)
    solution_requested: bool = False
    source_summary: str = Field(default="", max_length=5000)
    generated_course_id: str | None = Field(default=None, max_length=120)
    user_id: str = Field(default="default_user", max_length=80)
    adaptation_hint: str = Field(default="", max_length=2000)


class TutorResponse(BaseModel):
    hint_level: int
    message: str
    is_solution: bool = False
    available: bool = True
    provider: str | None = None
    model: str | None = None
    used_fallback: bool = False
    error: str | None = None


class ProviderStatus(BaseModel):
    provider: str
    name: str
    available: bool
    model: str
    is_current: bool = False
    reason: str | None = None
    error: str | None = None
    configured: bool = True


ProviderHealth = ProviderStatus


class ProvidersOverview(BaseModel):
    current_provider: str
    fallback_provider: str | None = None
    providers: list[ProviderStatus]


class OllamaHealth(BaseModel):
    available: bool
    model: str
    base_url: str
    error: str | None = None
