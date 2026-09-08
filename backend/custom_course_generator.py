import json
import re
import uuid
from typing import Any
from pydantic import BaseModel, Field

from .lesson_models import (
    ConceptDefinition,
    CourseDefinition,
    Curriculum,
    ExerciseDefinition,
    LessonDefinition,
    ModuleDefinition,
    ModuleReference,
    SubLessonDefinition,
)

class CourseGenerationRequest(BaseModel):
    material_type: str = Field(pattern=r"^(youtube_url|transcript|file_upload)$")
    content: str = Field(default="")
    title: str = Field(default="", max_length=120)
    filename: str | None = None

def slugify(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[-\s]+", "-", s)[:50] or "custom-step"

def build_custom_curriculum_from_text(
    title: str,
    content: str,
    material_type: str
) -> Curriculum:
    course_id = f"custom-{uuid.uuid4().hex[:8]}"
    course_title = title.strip() or f"Custom: {material_type.replace('_', ' ').title()}"

    lines = [line.strip() for line in content.split("\n") if line.strip()]
    summary_text = " ".join(lines[:5]) if lines else "Custom uploaded material."

    concepts = [
        ConceptDefinition(id=f"{course_id}-concept-1", title="Core Material Foundations", prerequisites=[]),
        ConceptDefinition(id=f"{course_id}-concept-2", title="Practical Application", prerequisites=[f"{course_id}-concept-1"]),
        ConceptDefinition(id=f"{course_id}-concept-3", title="Mastery & Evaluation", prerequisites=[f"{course_id}-concept-2"]),
    ]
    concepts_dict = {c.id: c for c in concepts}

    lessons: list[LessonDefinition] = []

    # 1. Learn Step
    lessons.append(
        LessonDefinition(
            id=f"{course_id}-step-1",
            title=f"1. Foundations of {course_title}",
            description=f"Introduction and core concepts based on provided material: {summary_text[:120]}...",
            order=1,
            difficulty="beginner",
            duration_minutes=5,
            type="learn",
            section_id="section-1",
            section_title="Section 1: Foundations",
            starter_code=f"# Write notes or python logic for {course_title}\nprint('Learning: {course_title}')\n",
            concepts=[c.id for c in concepts[:1]],
            learning_objectives=["Understand core principles", "Review key terminology"],
            sublessons=[
                SubLessonDefinition(
                    id=f"{course_id}-sub-1",
                    title="Key Concepts Overview",
                    description="Overview of extracted material",
                    order=1,
                    exercises=[
                        ExerciseDefinition(
                            id=f"{course_id}-ex-1",
                            title="Concept Review",
                            type="multiple_choice",
                            question=f"What is the main topic covered in this section?",
                            options=[course_title, "Unrelated Topic A", "Unrelated Topic B"],
                            correct_answer=course_title,
                            xp_reward=10,
                        )
                    ],
                )
            ],
            xp_reward=15,
        )
    )

    # 2. Practice Step
    lessons.append(
        LessonDefinition(
            id=f"{course_id}-step-2",
            title=f"2. Practice: {course_title} Applications",
            description="Apply your knowledge to solve real problems derived from the material.",
            order=2,
            difficulty="beginner",
            duration_minutes=10,
            type="practice",
            section_id="section-1",
            section_title="Section 1: Foundations",
            starter_code=f"# Practice exercise\ndef process_content():\n    return 'success'\n",
            concepts=[c.id for c in concepts[1:2]],
            learning_objectives=["Practice practical code patterns", "Implement basic algorithms"],
            xp_reward=20,
        )
    )

    # 3. Review Step
    lessons.append(
        LessonDefinition(
            id=f"{course_id}-step-3",
            title=f"3. Review & Refinement",
            description="Consolidate your understanding and review key code patterns.",
            order=3,
            difficulty="intermediate",
            duration_minutes=8,
            type="review",
            section_id="section-1",
            section_title="Section 1: Foundations",
            starter_code="# Review solution\nresult = True\n",
            concepts=[c.id for c in concepts[1:2]],
            xp_reward=20,
        )
    )

    # 4. Challenge Step
    lessons.append(
        LessonDefinition(
            id=f"{course_id}-step-4",
            title=f"4. Challenge: {course_title} Mastery",
            description="Solve an end-to-end challenge problem incorporating all material concepts.",
            order=4,
            difficulty="intermediate",
            duration_minutes=15,
            type="challenge",
            section_id="section-2",
            section_title="Section 2: Advanced Mastery",
            starter_code="# Challenge: Solve full requirement\n",
            concepts=[c.id for c in concepts[2:]],
            xp_reward=30,
        )
    )

    # 5. Checkpoint Step
    lessons.append(
        LessonDefinition(
            id=f"{course_id}-step-5",
            title=f"5. Checkpoint: {course_title} Certification",
            description="Final checkpoint test-out evaluation for this custom course.",
            order=5,
            difficulty="advanced",
            duration_minutes=15,
            type="checkpoint",
            section_id="section-2",
            section_title="Section 2: Advanced Mastery",
            test_out_eligible=True,
            starter_code="# Checkpoint assessment code\n",
            concepts=[c.id for c in concepts],
            xp_reward=50,
        )
    )

    module = ModuleDefinition(
        id=f"{course_id}-mod-1",
        title=f"Unit 1: {course_title}",
        order=1,
        concepts=concepts,
        lessons=lessons,
    )

    course_def = CourseDefinition(
        id=course_id,
        title=course_title,
        language="python",
        modules=[ModuleReference(id=module.id, path=f"modules/{module.id}.json")],
    )

    return Curriculum(
        course=course_def,
        modules=[module],
        concepts=concepts_dict,
        lessons=tuple(lessons),
    )
