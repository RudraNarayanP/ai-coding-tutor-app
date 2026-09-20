from typing import Any, Optional
from pydantic import BaseModel, Field


class CompanionQuestion(BaseModel):
    question: str
    options: list[str]
    correct_answer: str
    explanation: Optional[str] = None


class PublicCompanionQuestion(BaseModel):
    """Companion question without the answer key.

    ``/api/materials`` is fetched when the library is opened, long before the
    learner answers, and grading happens server-side in ``complete_material``
    — so the client never needs ``correct_answer``.
    """

    question: str
    options: list[str]


class Material(BaseModel):
    id: str
    title: str
    description: str
    language: str
    category: str
    difficulty: str = "beginner"
    resource_type: str
    url: str
    official_or_community: str = "official"
    estimated_minutes: int = 5
    concept_tags: list[str] = Field(default_factory=list)
    recommended_stage: str = "learn"
    xp_reward: int = 15
    completion_type: str = "companion_question"
    source_domain: str = ""
    license_or_usage_notes: str = ""
    is_external: bool = True
    is_interactive: bool = False
    is_project: bool = False
    is_reference: bool = False
    is_visualizer: bool = False
    is_challenge: bool = False
    companion_question: Optional[CompanionQuestion] = None


class PublicMaterial(Material):
    companion_question: Optional[PublicCompanionQuestion] = None


def to_public(material: Material) -> PublicMaterial:
    """Project a material for the browser, dropping the companion answer key."""
    return PublicMaterial.model_validate(material.model_dump())


class MaterialCompletionRequest(BaseModel):
    user_answer: Optional[str] = None


class MaterialCompletionResponse(BaseModel):
    material_id: str
    passed: bool
    feedback: str
    xp_awarded: int
    total_xp: int
