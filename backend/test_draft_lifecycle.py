import pytest
from pathlib import Path
from backend.custom_course_generator import CourseSerializer, GeneratedCourseMetadata
from backend.lesson_models import CourseDefinition, Curriculum, ModuleDefinition, ModuleReference, ConceptDefinition, LessonDefinition, SubLessonDefinition, ExerciseDefinition

def test_draft_lifecycle(tmp_path: Path):
    serializer = CourseSerializer(tmp_path)
    cid = "custom-test-123"

    mod_ref = ModuleReference(id=f"{cid}-mod-1", path=f"modules/{cid}-mod-1.json")
    course_def = CourseDefinition(id=cid, title="Draft Course", language=cid, modules=[mod_ref])
    curr = Curriculum(course=course_def, modules=[], concepts={}, lessons=())
    meta = GeneratedCourseMetadata(
        course_id=cid,
        source_type="transcript",
        source_hash="hash123",
        title="Draft Course",
        language=cid,
        generated_at=1000.0,
        status="draft",
    )

    draft_dir = serializer.write_draft(curr, meta)
    assert draft_dir.exists()
    assert (draft_dir / "_metadata.json").exists()

    active_metas = serializer.list_active()
    assert all(m.course_id != cid for m in active_metas)

    # Confirm draft -> active
    active_dir = serializer.confirm_draft(cid)
    assert active_dir.exists()
    assert not draft_dir.exists()

    active_metas_after = serializer.list_active()
    assert any(m.course_id == cid for m in active_metas_after)
