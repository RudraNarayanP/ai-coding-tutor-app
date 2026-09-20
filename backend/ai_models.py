from typing import Any
from pydantic import BaseModel, Field, field_validator

from .lesson_models import TestResult


class TutorRequest(BaseModel):
    lesson_id: str = Field(min_length=1, max_length=80)
    lesson_title: str = Field(min_length=1, max_length=120)
    unit_title: str = Field(default="", max_length=120)
    concept_title: str = Field(default="", max_length=120)
    prerequisites: list[str] = Field(default_factory=list, max_length=20)
    instructions: str = Field(min_length=1, max_length=2000)
    learning_objective: str = Field(default="", max_length=500)
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

    @field_validator("hint_level", mode="before")
    @classmethod
    def _clamp_hint_level(cls, value: Any) -> int:
        """Hint escalation saturates instead of rejecting the request.

        A learner who keeps tapping "Request a hint" must always get one; a
        validation error there would punish exactly the engaged behaviour the
        flow design wants to reward.
        """
        try:
            level = int(value)
        except (TypeError, ValueError):
            return 1
        return max(1, min(4, level))


class TutorResponse(BaseModel):
    hint_level: int
    message: str
    is_solution: bool = False
    available: bool = True
    provider: str | None = None
    model: str | None = None
    error: str | None = None
    # "ai" | "ai_repaired" | "offline" | "unavailable" — how this text was made.
    source: str = "ai"
    contract_version: str = ""


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
    providers: list[ProviderStatus]


class OllamaHealth(BaseModel):
    available: bool
    model: str
    base_url: str
    error: str | None = None
