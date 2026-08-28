import json
from pathlib import Path

from pydantic import ValidationError

from .lesson_models import CourseDefinition, Curriculum, LessonDefinition, ModuleDefinition


class CurriculumLoadError(ValueError):
    pass


class CurriculumLoader:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _read_json(self, path: Path) -> dict:
        try:
            with path.open(encoding="utf-8") as curriculum_file:
                data = json.load(curriculum_file)
        except FileNotFoundError as exc:
            raise CurriculumLoadError(f"Curriculum file not found: {path}") from exc
        except json.JSONDecodeError as exc:
            raise CurriculumLoadError(
                f"Invalid JSON in {path}: line {exc.lineno}, column {exc.colno}"
            ) from exc
        if not isinstance(data, dict):
            raise CurriculumLoadError(f"Curriculum file must contain an object: {path}")
        return data

    def load(self) -> Curriculum:
        course_path = self.root / "course.json"
        try:
            course = CourseDefinition.model_validate(self._read_json(course_path))
        except ValidationError as exc:
            raise CurriculumLoadError(f"Invalid course schema in {course_path}: {exc}") from exc

        modules: list[ModuleDefinition] = []
        module_ids: set[str] = set()
        for reference in course.modules:
            if reference.id in module_ids:
                raise CurriculumLoadError(f"Duplicate module reference: {reference.id}")
            module_ids.add(reference.id)
            module_path = self.root / reference.path
            try:
                module = ModuleDefinition.model_validate(self._read_json(module_path))
            except ValidationError as exc:
                raise CurriculumLoadError(
                    f"Invalid module schema in {module_path}: {exc}"
                ) from exc
            if module.id != reference.id:
                raise CurriculumLoadError(
                    f"Module reference {reference.id} points to module {module.id}"
                )
            modules.append(module)

        concepts = {}
        for module in modules:
            for concept in module.concepts:
                if concept.id in concepts:
                    raise CurriculumLoadError(f"Duplicate concept id: {concept.id}")
                concepts[concept.id] = concept

        lessons: list[LessonDefinition] = []
        lesson_ids: set[str] = set()
        orders: set[int] = set()
        for module in sorted(modules, key=lambda item: item.order):
            for lesson in module.lessons:
                if lesson.id in lesson_ids:
                    raise CurriculumLoadError(f"Duplicate lesson id: {lesson.id}")
                if lesson.order in orders:
                    raise CurriculumLoadError(f"Duplicate lesson order: {lesson.order}")
                lesson_ids.add(lesson.id)
                orders.add(lesson.order)

                unknown_concepts = (
                    set(lesson.concepts + lesson.prerequisites) - concepts.keys()
                )
                if unknown_concepts:
                    raise CurriculumLoadError(
                        f"Lesson {lesson.id} references unknown concepts: "
                        f"{sorted(unknown_concepts)}"
                    )

                # Validate individual test specs
                for test in lesson.tests:
                    has_stdout = test.expected_stdout is not None
                    has_unittest = test.unittest_code is not None
                    if not has_stdout and not has_unittest:
                        raise CurriculumLoadError(
                            f"Lesson {lesson.id}, test '{test.name}': "
                            "must have either expected_stdout or unittest_code"
                        )
                    if has_stdout and has_unittest:
                        raise CurriculumLoadError(
                            f"Lesson {lesson.id}, test '{test.name}': "
                            "cannot have both expected_stdout and unittest_code"
                        )

                test_names = {test.name for test in lesson.tests}
                required_names = set(lesson.completion_requirements.required_test_names)
                unknown_tests = required_names - test_names
                if unknown_tests:
                    raise CurriculumLoadError(
                        f"Lesson {lesson.id} references unknown required tests: "
                        f"{sorted(unknown_tests)}"
                    )
                lessons.append(lesson)

        self._validate_concept_graph(concepts)
        lessons.sort(key=lambda item: item.order)
        return Curriculum(
            course=course, modules=modules, concepts=concepts, lessons=tuple(lessons)
        )

    @staticmethod
    def _validate_concept_graph(concepts: dict) -> None:
        for concept in concepts.values():
            unknown = set(concept.prerequisites) - concepts.keys()
            if unknown:
                raise CurriculumLoadError(
                    f"Concept {concept.id} references unknown prerequisites: "
                    f"{sorted(unknown)}"
                )

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(concept_id: str, path: list[str]) -> None:
            if concept_id in visiting:
                cycle_start = path.index(concept_id)
                cycle = path[cycle_start:] + [concept_id]
                raise CurriculumLoadError(
                    f"Circular concept prerequisite: {' -> '.join(cycle)}"
                )
            if concept_id in visited:
                return
            visiting.add(concept_id)
            for prerequisite in concepts[concept_id].prerequisites:
                visit(prerequisite, path + [concept_id])
            visiting.remove(concept_id)
            visited.add(concept_id)

        for concept_id in concepts:
            visit(concept_id, [])


def load_default_curriculum() -> Curriculum:
    return CurriculumLoader(
        Path(__file__).resolve().parent.parent / "curriculum" / "python"
    ).load()
