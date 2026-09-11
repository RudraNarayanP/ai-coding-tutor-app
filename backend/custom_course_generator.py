import logging
import json
import os
import re
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .ai_provider import AIProvider, AIProviderError, get_ai_provider
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
from .source_ingestion import SourceDocument, SourceIngestionService, VideoSegment, IngestionError


class GenerationError(ValueError):
    """User-facing course generation error."""
    pass


# ─── DATA MODELS ───────────────────────────────────────────────────────────────

class CourseGenerationRequest(BaseModel):
    material_type: str = Field(pattern=r"^(youtube_url|youtube_playlist|transcript|file_upload)$")
    content: str = Field(default="", max_length=50_000)
    title: str = Field(default="", max_length=120)
    filename: str | None = None
    difficulty: str | None = Field(default=None, pattern=r"^(beginner|intermediate|advanced)$")
    practice_intensity: str | None = Field(default=None, pattern=r"^(light|balanced|heavy)$")
    force_duplicate: bool = False


@dataclass
class StageStatus:
    name: str
    label: str
    state: Literal["pending", "active", "done", "error"] = "pending"
    started_at: float | None = None
    completed_at: float | None = None


@dataclass
class ConceptNode:
    id: str                          # slug, e.g. "gradient-descent"
    label: str                       # human-readable, e.g. "Gradient Descent"
    description: str                 # 1-2 sentences
    source_segments: list[int]       # VideoSegment position numbers
    difficulty: str                  # "foundational" | "core" | "advanced"
    domain_tags: list[str]
    learning_objectives: list[str]


@dataclass
class ConceptGraph:
    nodes: list[ConceptNode]
    edges: list[tuple[str, str]]     # (prerequisite_id, dependent_id)
    detected_domain: str
    detected_difficulty: str         # "beginner" | "intermediate" | "advanced"
    source_summary: str


@dataclass
class LessonSlot:
    type: str                        # "learn" | "practice" | "review" | "challenge" | "checkpoint"
    concept_ids: list[str]
    learning_objectives: list[str]
    difficulty: str
    duration_minutes: int
    test_out_eligible: bool
    suggested_exercise_types: list[str]


@dataclass
class UnitBlueprint:
    title: str
    concept_ids: list[str]
    lesson_slots: list[LessonSlot]
    pedagogical_rationale: str


@dataclass
class CurriculumBlueprint:
    units: list[UnitBlueprint]
    total_lessons: int
    domain: str
    sequencing_rationale: str


@dataclass
class ValidationResult:
    valid: bool
    violations: list[str]
    retry_hint: str


class GeneratedCourseMetadata(BaseModel):
    course_id: str
    source_type: str
    source_url: str = ""
    source_hash: str
    title: str
    description: str = ""
    language: str                     # domain or language key
    generated_at: float
    status: str                       # "draft" | "active" | "error"
    difficulty: str = "beginner"
    practice_intensity: str = "balanced"
    unit_count: int = 0
    lesson_count: int = 0
    topics: list[str] = Field(default_factory=list)
    source_summary: str = ""
    sequencing_rationale: str = ""
    domain: str = "general"
    access_level: str = "full"
    access_notes: list[str] = Field(default_factory=list)


class GeneratedCoursePreview(BaseModel):
    course_id: str
    title: str
    source_name: str
    source_url: str
    unit_count: int
    lesson_count: int
    exercise_count: int
    checkpoint_count: int
    topics: list[str]
    difficulty: str
    domain: str
    language: str
    estimated_minutes: int
    sequencing_rationale: str
    access_notes: list[str] = Field(default_factory=list)


@dataclass
class GenerationJob:
    job_id: str
    request: CourseGenerationRequest
    status: Literal["queued", "generating", "draft", "active", "error"] = "queued"
    stages: list[StageStatus] = field(default_factory=list)
    course_id: str | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    preview: GeneratedCoursePreview | None = None
    draft_path: Path | None = None


class RegenerateLessonRequest(BaseModel):
    lesson_id: str
    pedagogical_style: str = Field(
        default="conceptual",
        pattern=r"^(conceptual|mathematical|practical|visual|socratic)$"
    )


class RegenerateUnitRequest(BaseModel):
    unit_id: str
    pedagogical_style: str = Field(
        default="conceptual",
        pattern=r"^(conceptual|mathematical|practical|visual|socratic)$"
    )


def slugify(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[-\s]+", "-", s)[:50] or "custom-step"


# ─── INPUT VALIDATOR ───────────────────────────────────────────────────────────

class InputValidator:
    ALLOWED_URL_HOSTS = {"www.youtube.com", "youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"}
    MAX_TRANSCRIPT_CHARS = 50_000

    @classmethod
    def validate(cls, req: CourseGenerationRequest) -> None:
        if req.material_type in ("youtube_url", "youtube_playlist"):
            if not req.content.strip():
                raise ValueError("YouTube URL cannot be empty.")
            try:
                from urllib.parse import urlparse
                parsed = urlparse(req.content.strip())
                if parsed.netloc not in cls.ALLOWED_URL_HOSTS:
                    raise ValueError(f"URL domain '{parsed.netloc}' is not allowed. Only YouTube URLs are supported.")
            except Exception as exc:
                if isinstance(exc, ValueError):
                    raise exc
                raise ValueError("Invalid URL format.")
        elif req.material_type in ("transcript", "file_upload"):
            if not req.content.strip() and not req.title.strip():
                raise ValueError("Pasted transcript or notes content cannot be empty.")
            if len(req.content) > cls.MAX_TRANSCRIPT_CHARS:
                raise ValueError(f"Content exceeds maximum length of {cls.MAX_TRANSCRIPT_CHARS} characters.")


# ─── LEARNING DOMAIN CLASSIFIER ───────────────────────────────────────────────

class LearningDomain:
    PROGRAMMING       = "programming"
    MATHEMATICS       = "mathematics"
    LANGUAGE_LEARNING = "language_learning"
    SYSTEMS           = "systems"
    DATA_SCIENCE      = "data_science"
    SCIENCE           = "science"
    THEORY            = "theory"
    GENERAL           = "general"


DOMAIN_EXERCISE_POOLS: dict[str, list[str]] = {
    LearningDomain.PROGRAMMING: [
        "code_completion", "debugging", "output_prediction", "fill_blank",
        "mcq", "identify_mistake", "trace_execution", "tiny_coding",
    ],
    LearningDomain.MATHEMATICS: [
        "calculation", "proof_step_ordering", "fill_blank", "mcq",
        "identify_mistake", "worked_example_completion", "true_false",
    ],
    LearningDomain.LANGUAGE_LEARNING: [
        "recognition", "recall", "sentence_construction", "matching",
        "ordering", "fill_blank", "select_multiple", "true_false",
    ],
    LearningDomain.SYSTEMS: [
        "trace_execution", "scheduling_simulation", "mcq", "ordering",
        "debugging", "code_completion", "short_answer", "scenario_question",
    ],
    LearningDomain.DATA_SCIENCE: [
        "output_prediction", "code_completion", "mcq", "fill_blank",
        "interpretation", "identify_mistake", "calculation",
    ],
    LearningDomain.SCIENCE: [
        "prediction", "classification", "interpretation", "mcq",
        "ordering", "true_false", "short_answer", "fill_blank",
    ],
    LearningDomain.THEORY: [
        "proof_step_ordering", "mcq", "true_false", "fill_blank",
        "counterexample", "short_answer", "identify_mistake",
    ],
    LearningDomain.GENERAL: [
        "mcq", "true_false", "fill_blank", "matching",
        "ordering", "select_multiple", "short_answer", "scenario_question",
    ],
}


class LearningDomainClassifier:
    def classify(self, graph: ConceptGraph) -> str:
        d = (graph.detected_domain or "").lower().strip()
        if d in DOMAIN_EXERCISE_POOLS:
            return d

        # Keyword matching fallback
        all_text = " ".join([n.label + " " + n.description + " " + " ".join(n.domain_tags) for n in graph.nodes]).lower()
        if any(w in all_text for w in ["python", "code", "function", "variable", "class", "javascript", "c++", "algorithm"]):
            return LearningDomain.PROGRAMMING
        elif any(w in all_text for w in ["calculus", "derivative", "equation", "proof", "math", "matrix", "algebra"]):
            return LearningDomain.MATHEMATICS
        elif any(w in all_text for w in ["grammar", "vocabulary", "verb", "language", "spanish", "french", "sentence"]):
            return LearningDomain.LANGUAGE_LEARNING
        elif any(w in all_text for w in ["kernel", "memory", "network", "tcp", "operating system", "cpu", "process"]):
            return LearningDomain.SYSTEMS
        elif any(w in all_text for w in ["pandas", "dataframe", "regression", "model", "neural network", "dataset"]):
            return LearningDomain.DATA_SCIENCE
        elif any(w in all_text for w in ["physics", "chemistry", "biology", "molecule", "atom", "gene"]):
            return LearningDomain.SCIENCE
        elif any(w in all_text for w in ["automata", "turing", "logic", "boolean", "graph theory", "complexity"]):
            return LearningDomain.THEORY
        return LearningDomain.GENERAL

    def select_exercise_types(
        self,
        domain: str,
        lesson_type: str,
        learning_objectives: list[str],
        n: int = 3,
    ) -> list[str]:
        pool = DOMAIN_EXERCISE_POOLS.get(domain, DOMAIN_EXERCISE_POOLS[LearningDomain.GENERAL])
        objs = " ".join(learning_objectives).lower()

        selected: list[str] = []
        if lesson_type == "checkpoint":
            if domain == LearningDomain.PROGRAMMING:
                selected.append("tiny_coding")
            elif domain == LearningDomain.MATHEMATICS:
                selected.append("calculation")
            else:
                selected.append("short_answer")
        elif lesson_type == "learn":
            selected.append("mcq")
            if "fill_blank" in pool:
                selected.append("fill_blank")
        elif lesson_type == "practice":
            if "implement" in objs and "code_completion" in pool:
                selected.append("code_completion")
            elif "calculate" in objs and "calculation" in pool:
                selected.append("calculation")
            elif "identify" in objs and "identify_mistake" in pool:
                selected.append("identify_mistake")

        for ex in pool:
            if len(selected) >= n:
                break
            if ex not in selected:
                selected.append(ex)

        return selected[:n]


# ─── CONCEPT GRAPH BUILDER ────────────────────────────────────────────────────

class ConceptGraphBuilder:
    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider

    async def build(self, doc: SourceDocument) -> ConceptGraph:
        prompt = self._build_prompt(doc)
        system = (
            "You are an expert curriculum architect. Analyze the provided educational source material. "
            "Extract concepts and build a DAG prerequisite concept graph. "
            "Return JSON matching schema:\n"
            "{\n"
            '  "detected_domain": "programming|mathematics|language_learning|systems|data_science|science|theory|general",\n'
            '  "detected_difficulty": "beginner|intermediate|advanced",\n'
            '  "source_summary": "2-3 sentence summary",\n'
            '  "nodes": [\n'
            '    {"id": "concept-slug", "label": "Title", "description": "...", "source_segments": [1], "difficulty": "foundational|core|advanced", "domain_tags": ["..."], "learning_objectives": ["..."]}\n'
            '  ],\n'
            '  "edges": [["prereq-id", "dependent-id"]]\n'
            "}"
        )

        try:
            raw = await self.provider.generate_structured(system=system, user=prompt, max_tokens=3000)
            cg = self._parse_response(raw)
            if not cg.nodes:
                raise GenerationError("No valid concept nodes extracted from source material.")
            return cg
        except Exception as exc:
            logger.warning(f"ConceptGraphBuilder error: {exc}")
            if isinstance(exc, GenerationError):
                raise exc
            raise GenerationError(f"Failed to extract structured concepts from source material: {exc}")

    def _build_prompt(self, doc: SourceDocument) -> str:
        parts = [f"Title: {doc.title}", f"Access Level: {doc.access_level}"]
        if doc.segments:
            parts.append("Video Segments:")
            for s in doc.segments[:15]:
                trunc_t = s.transcript[:1500] if s.transcript else "Transcript unavailable"
                parts.append(f"Position {s.position}: {s.title}\nDescription: {s.description_snippet[:200]}\nTranscript: {trunc_t}")
        else:
            parts.append(f"Source Text:\n{doc.plain_text[:12000]}")
        return "\n\n".join(parts)

    def _parse_response(self, raw: str) -> ConceptGraph:
        json_str = raw
        if "```json" in raw:
            json_str = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            json_str = raw.split("```")[1].split("```")[0].strip()

        data = json.loads(json_str)
        nodes = []
        for n in data.get("nodes", []):
            nodes.append(
                ConceptNode(
                    id=slugify(n.get("id", "concept")),
                    label=n.get("label", "Concept"),
                    description=n.get("description", "Concept description"),
                    source_segments=n.get("source_segments", [1]),
                    difficulty=n.get("difficulty", "core"),
                    domain_tags=n.get("domain_tags", []),
                    learning_objectives=n.get("learning_objectives", ["Understand the concept"]),
                )
            )

        edges = [tuple(e) for e in data.get("edges", []) if len(e) == 2]
        return ConceptGraph(
            nodes=nodes,
            edges=edges,
            detected_domain=data.get("detected_domain", "general"),
            detected_difficulty=data.get("detected_difficulty", "beginner"),
            source_summary=data.get("source_summary", "Extracted source material concepts."),
        )

    def _fallback_graph(self, doc: SourceDocument) -> ConceptGraph:
        c1 = ConceptNode(
            id="core-foundations",
            label=f"Foundations of {doc.title[:40]}",
            description="Core principles and fundamental terminology.",
            source_segments=[1],
            difficulty="foundational",
            domain_tags=["foundations"],
            learning_objectives=["Understand core concepts"],
        )
        c2 = ConceptNode(
            id="practical-application",
            label="Practical Application & Implementation",
            description="Applying foundational principles to practical scenarios.",
            source_segments=[1],
            difficulty="core",
            domain_tags=["application"],
            learning_objectives=["Apply learned concepts to practice"],
        )
        c3 = ConceptNode(
            id="mastery-and-synthesis",
            label="Advanced Mastery & Synthesis",
            description="End-to-end evaluation and complex problem solving.",
            source_segments=[1],
            difficulty="advanced",
            domain_tags=["mastery"],
            learning_objectives=["Master advanced techniques"],
        )
        return ConceptGraph(
            nodes=[c1, c2, c3],
            edges=[("core-foundations", "practical-application"), ("practical-application", "mastery-and-synthesis")],
            detected_domain="general",
            detected_difficulty="beginner",
            source_summary=f"Course concepts for {doc.title}.",
        )


# ─── CURRICULUM SEQUENCER ─────────────────────────────────────────────────────

class CurriculumSequencer:
    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider
        self.classifier = LearningDomainClassifier()

    async def sequence(self, graph: ConceptGraph, retry_hint: str = "") -> CurriculumBlueprint:
        prompt = self._build_prompt(graph, retry_hint)
        system = (
            "You are a master learning experience designer. Group concepts into units and sequence them into a mastery path. "
            "Output valid JSON matching schema:\n"
            "{\n"
            '  "sequencing_rationale": "...",\n'
            '  "units": [\n'
            '    {\n'
            '      "title": "Unit 1: ...",\n'
            '      "concept_ids": ["c1", "c2"],\n'
            '      "pedagogical_rationale": "...",\n'
            '      "lesson_slots": [\n'
            '        {"type": "learn|practice|review|checkpoint", "concept_ids": ["c1"], "learning_objectives": ["..."], "difficulty": "beginner", "duration_minutes": 5, "test_out_eligible": false}\n'
            '      ]\n'
            '    }\n'
            '  ]\n'
            "}"
        )

        try:
            raw = await self.provider.generate_structured(system=system, user=prompt, max_tokens=3500)
            return self._parse_response(raw, graph)
        except Exception:
            return self._fallback_blueprint(graph)

    def _build_prompt(self, graph: ConceptGraph, retry_hint: str) -> str:
        nodes_info = "\n".join([f"- {n.id}: {n.label} ({n.difficulty})" for n in graph.nodes])
        edges_info = "\n".join([f"- {e[0]} -> {e[1]}" for e in graph.edges])
        prompt = f"Concepts:\n{nodes_info}\n\nPrerequisite Edges:\n{edges_info}\nDomain: {graph.detected_domain}\n"
        if retry_hint:
            prompt += f"\nRETRY INSTRUCTION: Previous attempt had violations: {retry_hint}. Fix these constraints."
        return prompt

    def _parse_response(self, raw: str, graph: ConceptGraph) -> CurriculumBlueprint:
        json_str = raw
        if "```json" in raw:
            json_str = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            json_str = raw.split("```")[1].split("```")[0].strip()

        data = json.loads(json_str)
        domain = self.classifier.classify(graph)

        units = []
        total_lessons = 0
        for u in data.get("units", []):
            u_concepts = u.get("concept_ids", [])
            slots = []
            for s in u.get("lesson_slots", []):
                s_type = s.get("type", "learn")
                s_concepts = s.get("concept_ids", u_concepts)
                s_objs = s.get("learning_objectives", ["Master lesson topic"])
                s_exercise_types = self.classifier.select_exercise_types(
                    domain=domain,
                    lesson_type=s_type,
                    learning_objectives=s_objs,
                )
                slots.append(
                    LessonSlot(
                        type=s_type,
                        concept_ids=s_concepts,
                        learning_objectives=s_objs,
                        difficulty=s.get("difficulty", "beginner"),
                        duration_minutes=s.get("duration_minutes", 5),
                        test_out_eligible=s_type == "checkpoint",
                        suggested_exercise_types=s_exercise_types,
                    )
                )
                total_lessons += 1

            units.append(
                UnitBlueprint(
                    title=u.get("title", f"Unit {len(units)+1}"),
                    concept_ids=u_concepts,
                    lesson_slots=slots,
                    pedagogical_rationale=u.get("pedagogical_rationale", "Sequenced for mastery."),
                )
            )

        return CurriculumBlueprint(
            units=units,
            total_lessons=total_lessons,
            domain=domain,
            sequencing_rationale=data.get("sequencing_rationale", "Structured in progressive difficulty order."),
        )

    def _fallback_blueprint(self, graph: ConceptGraph) -> CurriculumBlueprint:
        domain = self.classifier.classify(graph)
        all_ids = [n.id for n in graph.nodes]
        slots = [
            LessonSlot("learn", all_ids[:1], ["Learn core principles"], "beginner", 5, False, self.classifier.select_exercise_types(domain, "learn", [])),
            LessonSlot("practice", all_ids[1:2] or all_ids[:1], ["Practice application"], "beginner", 8, False, self.classifier.select_exercise_types(domain, "practice", [])),
            LessonSlot("review", all_ids[1:2] or all_ids[:1], ["Review key concepts"], "intermediate", 6, False, self.classifier.select_exercise_types(domain, "review", [])),
            LessonSlot("checkpoint", all_ids, ["Evaluate mastery"], "intermediate", 10, True, self.classifier.select_exercise_types(domain, "checkpoint", [])),
        ]
        u1 = UnitBlueprint(
            title=f"Unit 1: Mastery of {graph.source_summary[:30]}",
            concept_ids=all_ids,
            lesson_slots=slots,
            pedagogical_rationale="Fallback structured unit.",
        )
        return CurriculumBlueprint(
            units=[u1],
            total_lessons=len(slots),
            domain=domain,
            sequencing_rationale="Progressive sequence from basics to checkpoint evaluation.",
        )


# ─── STRUCTURE VALIDATOR ───────────────────────────────────────────────────────



# ─── QUALITY GATE ─────────────────────────────────────────────────────────────

class QualityGate:
    """Quality gate validator ensuring generated curricula meet grounding and validity requirements."""

    PLACEHOLDER_SUBSTRINGS = (
        "unrelated concept",
        "option 1",
        "option 2",
        "incorrect choice",
        "placeholder",
        "dummy",
        "sample course",
    )

    @classmethod
    def validate_or_raise(cls, curriculum: Curriculum, doc: SourceDocument) -> None:
        violations = []

        if not curriculum.course.title or len(curriculum.course.title.strip()) < 3:
            violations.append("Course title is missing or too short.")

        if not curriculum.modules:
            violations.append("Course contains no units/modules.")

        total_exercises = 0
        for mod in curriculum.modules:
            if not mod.lessons:
                violations.append(f"Unit '{mod.title}' contains no lessons.")
            for lesson in mod.lessons:
                sublessons = getattr(lesson, "sublessons", [])
                if not sublessons and not getattr(lesson, "mastery_exam", []):
                    violations.append(f"Lesson '{lesson.title}' has no sublessons or exercises.")

                for sub in sublessons:
                    for ex in sub.exercises:
                        total_exercises += 1
                        q_lower = ex.question.lower()
                        if not ex.question.strip():
                            violations.append(f"Exercise in '{lesson.title}' has an empty question.")

                        for ph in cls.PLACEHOLDER_SUBSTRINGS:
                            if ph in q_lower:
                                violations.append(f"Exercise question in '{lesson.title}' contains placeholder phrase: '{ph}'.")
                            for opt in ex.options:
                                if ph in opt.lower():
                                    violations.append(f"Exercise option in '{lesson.title}' contains placeholder phrase: '{ph}'.")

                        if ex.type.lower() in ("mcq", "true_false"):
                            if not ex.options or len(ex.options) < 2:
                                violations.append(f"MCQ exercise in '{lesson.title}' has fewer than 2 options.")
                            if ex.correct_answer and ex.options:
                                corr_clean = str(ex.correct_answer).strip().lower()
                                opts_clean = [str(o).strip().lower() for o in ex.options]
                                if corr_clean not in opts_clean and not corr_clean.isdigit():
                                    violations.append(f"MCQ correct_answer '{ex.correct_answer}' not in options.")

                        if ex.type.lower() in ("tiny_coding", "code_completion", "code", "debugging"):
                            if not ex.starter_code or not ex.starter_code.strip():
                                ex.starter_code = "# Write your code solution below\n"

        if total_exercises == 0:
            violations.append("Generated course contains zero exercises.")

        if violations:
            logger.warning(f"QualityGate rejected curriculum for '{curriculum.course.title}': {violations}")
            raise GenerationError(f"Course quality validation failed: {'; '.join(violations)}")


class StructureValidator:
    MAX_UNITS = 12
    MIN_UNITS = 1
    MAX_LESSONS_PER_UNIT = 10
    MIN_LESSONS_PER_UNIT = 2
    MAX_TOTAL_LESSONS = 80

    def validate(self, blueprint: CurriculumBlueprint, graph: ConceptGraph) -> ValidationResult:
        violations = []
        if len(blueprint.units) < self.MIN_UNITS or len(blueprint.units) > self.MAX_UNITS:
            violations.append(f"Unit count {len(blueprint.units)} out of bounds [{self.MIN_UNITS}, {self.MAX_UNITS}].")

        valid_node_ids = {n.id for n in graph.nodes}
        for idx, unit in enumerate(blueprint.units, start=1):
            if len(unit.lesson_slots) < self.MIN_LESSONS_PER_UNIT or len(unit.lesson_slots) > self.MAX_LESSONS_PER_UNIT:
                violations.append(f"Unit {idx} lesson count {len(unit.lesson_slots)} out of bounds [{self.MIN_LESSONS_PER_UNIT}, {self.MAX_LESSONS_PER_UNIT}].")

            has_learn = any(s.type == "learn" for s in unit.lesson_slots)
            if not has_learn:
                violations.append(f"Unit {idx} has no learn slots.")

        if blueprint.total_lessons > self.MAX_TOTAL_LESSONS:
            violations.append(f"Total lesson count {blueprint.total_lessons} exceeds maximum {self.MAX_TOTAL_LESSONS}.")

        retry_hint = "; ".join(violations) if violations else ""
        return ValidationResult(valid=len(violations) == 0, violations=violations, retry_hint=retry_hint)

    def enforce_schema_invariants(self, blueprint: CurriculumBlueprint) -> CurriculumBlueprint:
        for unit in blueprint.units:
            if not unit.lesson_slots or unit.lesson_slots[-1].type != "checkpoint":
                unit.lesson_slots.append(
                    LessonSlot(
                        type="checkpoint",
                        concept_ids=unit.concept_ids,
                        learning_objectives=["Section mastery evaluation"],
                        difficulty="intermediate",
                        duration_minutes=10,
                        test_out_eligible=True,
                        suggested_exercise_types=["short_answer" if blueprint.domain != "programming" else "tiny_coding"],
                    )
                )
        blueprint.total_lessons = sum(len(u.lesson_slots) for u in blueprint.units)
        return blueprint


# ─── CURRICULUM GENERATOR ─────────────────────────────────────────────────────

PEDAGOGICAL_STYLE_INSTRUCTIONS: dict[str, str] = {
    "conceptual": "Focus on building deep intuition. Use analogies, comparisons, and 'why does this work?' explanations.",
    "mathematical": "Be rigorous and precise. Include formal definitions, step-by-step derivations, and quantitative examples.",
    "practical": "Lead with working examples and real-world applications. Maximize hands-on exercises.",
    "visual": "Describe concepts in terms of visual models, diagrams, and spatial reasoning.",
    "socratic": "Teach through questions. Guide the learner to discover concepts by answering progressive questions.",
}

DIFFICULTY_PROMPT_REQUIREMENTS: dict[str, str] = {
    "beginner": (
        "TARGET AUDIENCE: High-school student or introductory learner.\n"
        "COMPLEXITY: Clear definitions, direct recall, single-concept focus, and straightforward explanations.\n"
        "QUESTION STYLE: Direct and intuitive with unambiguous correct answers and clear distractors."
    ),
    "intermediate": (
        "TARGET AUDIENCE: Undergraduate student or practical practitioner.\n"
        "COMPLEXITY: Multi-step reasoning, concept application, practical scenario analysis, connecting 2-3 concepts.\n"
        "QUESTION STYLE: Analytical questions requiring interpretation of code/text/formulas, non-trivial plausible distractors."
    ),
    "advanced": (
        "TARGET AUDIENCE: Advanced undergraduate or graduate student.\n"
        "COMPLEXITY: Advanced synthesis, edge-case evaluation, deep theoretical mechanism analysis.\n"
        "QUESTION STYLE: Sophisticated multi-part reasoning, analyzing subtle failure modes, detailed domain terminology."
    ),
    "expert": (
        "TARGET AUDIENCE: PhD-level researcher or senior domain expert.\n"
        "COMPLEXITY: Research-grade precision, cutting-edge theoretical frameworks, novel problem solving, interdisciplinary trade-offs.\n"
        "QUESTION STYLE: High-level technical analysis, exact scientific nomenclature, 120+ character comprehensive options with subtle expert-level distinctions."
    ),
}


class CurriculumGenerator:
    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider

    async def generate_unit(
        self,
        unit_blueprint: UnitBlueprint,
        graph: ConceptGraph,
        doc: SourceDocument,
        course_id: str,
        unit_index: int,
        pedagogical_style: str = "conceptual",
    ) -> ModuleDefinition:
        unit_id = f"{course_id}-mod-{unit_index}"
        concepts = [
            ConceptDefinition(id=f"{course_id}-concept-{cid}", title=cid.replace("-", " ").title(), prerequisites=[])
            for cid in unit_blueprint.concept_ids
        ]

        # Assemble rich source context directly from video transcripts/segments or plain text
        source_context_snippets = []
        if doc.segments:
            for s in doc.segments:
                t_snip = s.transcript[:2000] if s.transcript else s.description_snippet[:500]
                if t_snip:
                    source_context_snippets.append(f"Segment [{s.position}] {s.title}:\n{t_snip}")
        if not source_context_snippets and doc.plain_text:
            source_context_snippets.append(doc.plain_text[:8000])

        source_context = "\n\n".join(source_context_snippets)[:10000] or graph.source_summary

        style_instruction = PEDAGOGICAL_STYLE_INSTRUCTIONS.get(pedagogical_style, "")

        system_prompt = (
            "You are a world-class curriculum author and assessment designer. "
            "Generate rich, domain-aware lesson content and exercises derived directly from the provided source context.\n"
            "CRITICAL INSTRUCTIONS FOR QUESTIONS & OPTIONS:\n"
            "- Questions MUST test specific facts, mechanics, code patterns, equations, or concepts mentioned in the source material.\n"
            "- Options MUST be realistic, plausible choices related to the topic. NEVER output placeholder text like 'Incorrect choice A' or 'Option 1'.\n"
            "- Provide accurate correct answers and detailed explanations.\n"
            "Respond ONLY with a valid JSON array of objects representing the lessons in this unit.\n"
            "Do NOT wrap the response in markdown codeblock markers unless necessary, and ensure valid JSON syntax."
        )

        slots_info = []
        for l_idx, slot in enumerate(unit_blueprint.lesson_slots, start=1):
            lesson_id = f"{course_id}-m{unit_index}-l{l_idx}"
            diff_req = DIFFICULTY_PROMPT_REQUIREMENTS.get(slot.difficulty, DIFFICULTY_PROMPT_REQUIREMENTS["beginner"])
            slots_info.append(
                f"Lesson ID: {lesson_id}\n"
                f"Type: {slot.type}\n"
                f"Difficulty: {slot.difficulty}\n"
                f"Concepts: {slot.concept_ids}\n"
                f"Learning Objectives: {slot.learning_objectives}\n"
                f"Exercise Types: {slot.suggested_exercise_types}\n"
                f"Difficulty Scaling Rules:\n{diff_req}\n"
            )

        user_prompt = (
            f"Course ID: {course_id}\n"
            f"Unit Title: {unit_blueprint.title}\n"
            f"Domain: {graph.detected_domain}\n"
            f"Pedagogical Style: {pedagogical_style} - {style_instruction}\n\n"
            f"--- SOURCE CONTEXT ---\n{source_context}\n\n"
            f"--- LESSON SLOTS TO GENERATE ---\n"
            + "\n".join(slots_info)
            + "\n\n"
            "OUTPUT JSON SCHEMA:\n"
            "[\n"
            "  {\n"
            '    "id": "lesson_id",\n'
            '    "title": "Lesson Title",\n'
            '    "description": "Comprehensive description tied to source content",\n'
            '    "starter_code": "code snippet or note",\n'
            '    "exercises": [\n'
            "      {\n"
            '        "id": "ex_id",\n'
            '        "title": "Exercise Title",\n'
            '        "type": "mcq|fill_blank|tiny_coding|code_completion|short_answer",\n'
            '        "question": "Clear, context-grounded question citing facts/concepts from source material",\n'
            '        "options": ["Correct option", "Plausible distractor A", "Plausible distractor B"],\n'
            '        "correct_answer": "Correct option",\n'
            '        "explanation": "Detailed pedagogical explanation citing why the answer is correct",\n'
            '        "starter_code": "",\n'
            '        "solution_code": ""\n'
            "      }\n"
            "    ]\n"
            "  }\n"
            "]"
        )

        generated_lessons_map: dict[str, dict[str, Any]] = {}
        llm_data = None
        try:
            raw_llm = await self.provider.generate_structured(system=system_prompt, user=user_prompt, max_tokens=3500)
            llm_data = self._parse_generated_lessons(raw_llm)
        except Exception:
            llm_data = None
        if isinstance(llm_data, list):
            for item in llm_data:
                if isinstance(item, dict) and "id" in item:
                    generated_lessons_map[item["id"]] = item

        lessons: list[LessonDefinition] = []
        for l_idx, slot in enumerate(unit_blueprint.lesson_slots, start=1):
            lesson_id = f"{course_id}-m{unit_index}-l{l_idx}"
            llm_lesson_data = generated_lessons_map.get(lesson_id)
            llm_lesson_item = None
            if llm_data and l_idx - 1 < len(llm_data):
                llm_lesson_item = llm_data[l_idx - 1]

            lesson = self._build_lesson_definition(
                lesson_id=lesson_id,
                course_id=course_id,
                unit_id=unit_id,
                unit_title=unit_blueprint.title,
                order=(unit_index - 1) * 10 + l_idx,
                slot=slot,
                domain=graph.detected_domain,
                source_context=source_context,
                llm_data=llm_lesson_data,
                doc_title=doc.title,
                llm_item=llm_lesson_item,
            )
            lessons.append(lesson)

        return ModuleDefinition(
            id=unit_id,
            title=unit_blueprint.title,
            order=unit_index,
            concepts=concepts,
            lessons=lessons,
        )

    def _parse_generated_lessons(self, raw: str) -> list[dict] | None:
        json_str = raw
        if "```json" in raw:
            json_str = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            json_str = raw.split("```")[1].split("```")[0].strip()

        try:
            data = json.loads(json_str)
            if isinstance(data, dict) and "lessons" in data:
                return data["lessons"]
            if isinstance(data, list):
                return data
        except Exception:
            return None
        return None

    def _build_lesson_definition(
        self,
        lesson_id: str,
        course_id: str,
        unit_id: str,
        unit_title: str,
        order: int,
        slot: LessonSlot,
        domain: str,
        source_context: str = "",
        llm_data: dict[str, Any] | None = None,
        doc_title: str = "",
        llm_item: dict | None = None,
    ) -> LessonDefinition:
        c_title = slot.concept_ids[0].replace("-", " ").title() if slot.concept_ids else "Topic"
        topic_name = doc_title or c_title

        lesson_title = f"{order}. {slot.type.title()}: {c_title}"
        lesson_desc = f"Master {c_title} through {slot.type} exercises."
        starter_code = f"# Solution code for {c_title}\nprint('{c_title}')\n"
        exercises: list[ExerciseDefinition] = []

        # Structured per-lesson LLM payload (difficulty-scaled generation)
        if llm_data and isinstance(llm_data, dict):
            if llm_data.get("title"):
                lesson_title = f"{order}. {llm_data['title']}"
            if llm_data.get("description"):
                lesson_desc = llm_data["description"]
            if llm_data.get("starter_code"):
                starter_code = llm_data["starter_code"]

        # Transcript-driven quiz item with plausible distractors
        if llm_item and isinstance(llm_item, dict):
            if llm_item.get("title"):
                lesson_title = f"{order}. {llm_item['title']}"
            if llm_item.get("description"):
                lesson_desc = llm_item["description"]
            if llm_item.get("starter_code"):
                starter_code = llm_item["starter_code"]

            raw_exs = llm_item.get("exercises", [])
            for e_idx, raw_ex in enumerate(raw_exs, start=1):
                if not isinstance(raw_ex, dict):
                    continue
                q_text = raw_ex.get("question", "").strip()
                opts = raw_ex.get("options", [])
                ans = raw_ex.get("correct_answer", "").strip()

                # Ensure options do not contain placeholder strings
                clean_opts = [str(o) for o in opts if "incorrect choice" not in str(o).lower() and "option " not in str(o).lower()]
                if ans and ans not in clean_opts:
                    clean_opts.insert(0, ans)

                if len(clean_opts) < 2:
                    clean_opts = [
                        ans or f"Primary mechanism of {c_title}",
                        f"Secondary fallback configuration in {c_title}",
                        f"Legacy implementation pattern for {c_title}",
                    ]

                ex_type = raw_ex.get("type", "mcq")
                if ex_type not in ("mcq", "fill_blank", "code_completion", "tiny_coding", "true_false", "matching", "ordering"):
                    ex_type = "mcq"

                exercises.append(
                    ExerciseDefinition(
                        id=f"{lesson_id}-ex-{e_idx}",
                        title=raw_ex.get("title") or f"{slot.type.title()} Exercise {e_idx}",
                        type=ex_type,
                        question=q_text or f"According to the lesson on {c_title}, which statement best describes its core function?",
                        options=clean_opts,
                        correct_answer=ans or clean_opts[0],
                        explanation=raw_ex.get("explanation") or f"This directly relates to {c_title} as covered in {topic_name}.",
                        starter_code=raw_ex.get("starter_code") or ("" if ex_type == "mcq" else "# Enter your solution\n"),
                        solution_code=raw_ex.get("solution_code") or ("print('ok')\n" if ex_type in ("tiny_coding", "code_completion") else None),
                        xp_reward=15,
                    )
                )

        # Structured exercises from the difficulty-scaled LLM payload
        if not exercises and llm_data and isinstance(llm_data.get("exercises"), list) and len(llm_data["exercises"]) > 0:
            for ex_idx, raw_ex in enumerate(llm_data["exercises"], start=1):
                if isinstance(raw_ex, dict):
                    ex_type = raw_ex.get("type", "mcq")
                    q_text = raw_ex.get("question") or f"Mastery check for {c_title}"
                    opts = raw_ex.get("options") or []
                    corr = raw_ex.get("correct_answer") or (opts[0] if opts else "Correct answer")
                    expl = raw_ex.get("explanation") or f"Explanation of {c_title}."

                    exercises.append(
                        ExerciseDefinition(
                            id=f"{lesson_id}-ex-{ex_idx}",
                            title=raw_ex.get("title") or f"{slot.type.title()} Exercise {ex_idx}",
                            type=ex_type,
                            question=q_text,
                            options=opts,
                            correct_answer=corr,
                            explanation=expl,
                            starter_code=raw_ex.get("starter_code") or "",
                            solution_code=raw_ex.get("solution_code") or None,
                            xp_reward=15,
                        )
                    )

        # Fallback exercise generation incorporating source context and difficulty scaling
        if not exercises:
            ex_type = "mcq"
            if domain == "programming" and slot.type in ("practice", "checkpoint"):
                ex_type = "tiny_coding"

            # Extract context snippets for realistic question phrasing
            clean_context = source_context.replace("\n", " ").strip() if source_context else ""
            context_snippet = clean_context[:120] if clean_context else f"key principles of {c_title}"

            difficulty = slot.difficulty or "beginner"
            if difficulty == "expert":
                question_text = f"Regarding {c_title} and research findings from source context ('{context_snippet}...'), which precise theoretical mechanism holds?"
                options = [
                    f"Option A: According to the source analysis, {c_title} exhibits high-order theoretical properties under specified operational boundary conditions.",
                    f"Option B: {c_title} unconditionally simplifies to linear approximations regardless of boundary constraints.",
                    f"Option C: The source text indicates that {c_title} operates independently of surrounding systems.",
                ]
                correct_answer = options[0]
                explanation = f"In-depth analysis of {c_title} demonstrates the validity of Option A based on source material principles."
            elif difficulty == "advanced":
                question_text = f"In the context of {c_title} ('{context_snippet}...'), which analysis correctly evaluates key trade-offs?"
                options = [
                    f"Primary mechanism of {c_title} optimizing efficiency and consistency as stated in source material",
                    f"Secondary misconfiguration of {c_title} leading to non-deterministic failure",
                    f"Legacy implementation of {c_title} disregarding system boundary constraints",
                ]
                correct_answer = options[0]
                explanation = f"Evaluating {c_title} in this scenario confirms Option 1 as the correct design choice."
            elif difficulty == "intermediate":
                question_text = f"Based on the course material for {c_title}, which statement best describes its practical application?"
                options = [
                    f"It applies {c_title} directly to resolve key requirements described in the material.",
                    f"It replaces {c_title} with unrelated conceptual frameworks.",
                    f"It neglects {c_title} entirely during system execution.",
                ]
                correct_answer = options[0]
                explanation = f"{c_title} is specifically applied to address core requirements in the source material."
            else: # beginner
                question_text = f"What is the key principle of {c_title} presented in the lesson material?"
                options = [
                    f"The core mechanism and definition of {c_title}",
                    f"An alternative configuration unrelated to {c_title}",
                    f"A deprecated legacy behavior superseded by {c_title}",
                ]
                correct_answer = options[0]
                explanation = f"The lesson material defines {c_title} by its core fundamental principles."

            ex_starter_code = ""
            ex_solution_code = None
            if ex_type == "tiny_coding":
                ex_starter_code = "# Write your solution or note here\n"
                ex_solution_code = f"print('{c_title} ok')\n"

            exercises.append(
                ExerciseDefinition(
                    id=f"{lesson_id}-ex-1",
                    title=f"{slot.type.title()} Exercise 1",
                    type=ex_type,
                    question=question_text,
                    options=options,
                    correct_answer=correct_answer,
                    explanation=explanation,
                    starter_code=ex_starter_code,
                    solution_code=ex_solution_code,
                    xp_reward=15,
                )
            )

        sublessons = [
            SubLessonDefinition(
                id=f"{lesson_id}-sub-1",
                title=(llm_data.get("title") if isinstance(llm_data, dict) else None) or (llm_item.get("title") if isinstance(llm_item, dict) else None) or f"{c_title} Step 1",
                description=(llm_data.get("description") if isinstance(llm_data, dict) else None) or (llm_item.get("description") if isinstance(llm_item, dict) else None) or f"Interactive lesson step covering {c_title}",
                order=1,
                exercises=exercises,
            )
        ]

        return LessonDefinition(
            id=lesson_id,
            title=lesson_title,
            description=lesson_desc,
            order=order,
            difficulty=slot.difficulty,
            duration_minutes=slot.duration_minutes,
            type=slot.type,
            section_id=unit_id,
            section_title=unit_title,
            test_out_eligible=slot.test_out_eligible,
            concepts=[f"{course_id}-concept-{cid}" for cid in slot.concept_ids],
            learning_objectives=slot.learning_objectives,
            starter_code=starter_code,
            sublessons=sublessons,
            xp_reward=20,
        )

    async def regenerate_lesson(
        self,
        lesson_id: str,
        concept_ids: list[str],
        graph: ConceptGraph,
        doc: SourceDocument,
        pedagogical_style: str,
        course_id: str,
    ) -> LessonDefinition:
        style_instr = PEDAGOGICAL_STYLE_INSTRUCTIONS.get(pedagogical_style, "")
        slot = LessonSlot(
            type="practice",
            concept_ids=concept_ids,
            learning_objectives=[f"Regenerated in {pedagogical_style} style: {style_instr[:50]}"],
            difficulty="intermediate",
            duration_minutes=8,
            test_out_eligible=False,
            suggested_exercise_types=["multiple_choice"],
        )
        return self._build_lesson_definition(
            lesson_id=lesson_id,
            course_id=course_id,
            unit_id=f"{course_id}-mod-1",
            unit_title="Unit 1",
            order=1,
            slot=slot,
            domain=graph.detected_domain,
        )

    async def regenerate_unit(
        self,
        unit_blueprint: UnitBlueprint,
        graph: ConceptGraph,
        doc: SourceDocument,
        pedagogical_style: str,
        course_id: str,
        unit_index: int,
    ) -> ModuleDefinition:
        return await self.generate_unit(unit_blueprint, graph, doc, course_id, unit_index)


# ─── COURSE SERIALIZER ─────────────────────────────────────────────────────────

class CourseSerializer:
    def __init__(self, curriculum_root: Path) -> None:
        self.root = curriculum_root

    @property
    def drafts_dir(self) -> Path:
        p = self.root / "generated" / ".drafts"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def active_dir(self) -> Path:
        p = self.root / "generated"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def write_draft(self, curriculum: Curriculum, metadata: GeneratedCourseMetadata) -> Path:
        course_dir = self.drafts_dir / metadata.course_id
        if course_dir.exists():
            shutil.rmtree(course_dir)
        course_dir.mkdir(parents=True, exist_ok=True)
        (course_dir / "modules").mkdir(parents=True, exist_ok=True)

        # Write course.json
        with (course_dir / "course.json").open("w", encoding="utf-8") as f:
            json.dump(curriculum.course.model_dump(), f, indent=2)

        # Write modules
        for mod in curriculum.modules:
            with (course_dir / "modules" / f"{mod.id}.json").open("w", encoding="utf-8") as f:
                json.dump(mod.model_dump(), f, indent=2)

        # Write _metadata.json
        metadata.status = "draft"
        with (course_dir / "_metadata.json").open("w", encoding="utf-8") as f:
            json.dump(metadata.model_dump(), f, indent=2)

        return course_dir

    def confirm_draft(self, course_id: str) -> Path:
        draft_path = self.drafts_dir / course_id
        if not draft_path.exists():
            raise FileNotFoundError(f"Draft course {course_id} not found.")

        target_path = self.active_dir / course_id
        if target_path.exists():
            shutil.rmtree(target_path)

        shutil.move(str(draft_path), str(target_path))

        # Update metadata to active
        meta_file = target_path / "_metadata.json"
        if meta_file.exists():
            with meta_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            data["status"] = "active"
            with meta_file.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

        return target_path

    def delete(self, course_id: str) -> None:
        active_path = self.active_dir / course_id
        if active_path.exists():
            shutil.rmtree(active_path)
        draft_path = self.drafts_dir / course_id
        if draft_path.exists():
            shutil.rmtree(draft_path)

    def list_active(self) -> list[GeneratedCourseMetadata]:
        res = []
        if not self.active_dir.exists():
            return res
        for item in self.active_dir.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                meta_file = item / "_metadata.json"
                if meta_file.exists():
                    try:
                        with meta_file.open("r", encoding="utf-8") as f:
                            res.append(GeneratedCourseMetadata.model_validate_json(f.read()))
                    except Exception:
                        pass
        return res

    def load_metadata(self, course_id: str) -> GeneratedCourseMetadata:
        path = self.active_dir / course_id / "_metadata.json"
        if not path.exists():
            path = self.drafts_dir / course_id / "_metadata.json"
        if not path.exists():
            raise FileNotFoundError(f"Metadata for course {course_id} not found.")
        with path.open("r", encoding="utf-8") as f:
            return GeneratedCourseMetadata.model_validate_json(f.read())


# ─── DUPLICATE DETECTOR ────────────────────────────────────────────────────────

class DuplicateDetector:
    def __init__(self, serializer: CourseSerializer) -> None:
        self.serializer = serializer

    def find_duplicate(self, source_hash: str) -> GeneratedCourseMetadata | None:
        for meta in self.serializer.list_active():
            if meta.source_hash == source_hash:
                return meta
        return None


# ─── GENERATED COURSE STORE ────────────────────────────────────────────────────

class GeneratedCourseStore:
    def __init__(self) -> None:
        self.jobs: dict[str, GenerationJob] = {}
        self.user_counts: dict[str, int] = {}

    def create_job(self, req: CourseGenerationRequest) -> GenerationJob:
        job_id = f"job-{uuid.uuid4().hex[:10]}"
        stages = [
            StageStatus("reading_source", "Reading source"),
            StageStatus("understanding_topics", "Understanding topics"),
            StageStatus("building_prerequisites", "Building prerequisites"),
            StageStatus("designing_units", "Designing units"),
            StageStatus("creating_exercises", "Creating exercises"),
            StageStatus("creating_checkpoints", "Creating checkpoints"),
            StageStatus("finalizing_course", "Finalizing course"),
        ]
        job = GenerationJob(job_id=job_id, request=req, stages=stages)
        self.jobs[job_id] = job
        return job

    def get_job(self, job_id: str) -> GenerationJob | None:
        return self.jobs.get(job_id)

    def check_rate_limit(self, key: str = "default", max_per_day: int = 10) -> bool:
        return self.user_counts.get(key, 0) < max_per_day

    def record_generation(self, key: str = "default") -> None:
        self.user_counts[key] = self.user_counts.get(key, 0) + 1

    def sweep_abandoned_drafts(self, serializer: CourseSerializer) -> int:
        removed = 0
        if not serializer.drafts_dir.exists():
            return 0
        active_job_course_ids = {j.course_id for j in self.jobs.values() if j.course_id}
        for item in serializer.drafts_dir.iterdir():
            if item.is_dir() and item.name not in active_job_course_ids:
                shutil.rmtree(item)
                removed += 1
        return removed


# ─── LEGACY COMPATIBILITY HELPER ──────────────────────────────────────────────

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
                            type="mcq",
                            question=f"What is the main topic covered in this section?",
                            options=[
                                course_title,
                                f"Advanced performance optimization in {course_title}",
                                f"Alternative legacy configurations for {course_title}"
                            ],
                            correct_answer=course_title,
                            xp_reward=10,
                        )
                    ],
                )
            ],
            xp_reward=15,
        )
    )

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

logger = logging.getLogger("patchwork.generator")
