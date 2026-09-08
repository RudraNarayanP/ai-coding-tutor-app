import pytest
from unittest.mock import AsyncMock
from backend.custom_course_generator import CurriculumSequencer, ConceptGraph, ConceptNode

@pytest.mark.asyncio
async def test_curriculum_sequencer_mock():
    mock_provider = AsyncMock()
    mock_provider.generate_structured.return_value = """
    {
      "sequencing_rationale": "Concepts are ordered logically from basics to iteration.",
      "units": [
        {
          "title": "Unit 1: Fundamentals",
          "concept_ids": ["variables", "loops"],
          "pedagogical_rationale": "Covers core building blocks.",
          "lesson_slots": [
            {"type": "learn", "concept_ids": ["variables"], "learning_objectives": ["Define variables"], "difficulty": "beginner", "duration_minutes": 5, "test_out_eligible": false},
            {"type": "checkpoint", "concept_ids": ["variables", "loops"], "learning_objectives": ["Section test"], "difficulty": "intermediate", "duration_minutes": 10, "test_out_eligible": true}
          ]
        }
      ]
    }
    """

    sequencer = CurriculumSequencer(mock_provider)
    graph = ConceptGraph(
        nodes=[
            ConceptNode("variables", "Variables", "desc", [1], "foundational", ["python"], ["Define variables"]),
            ConceptNode("loops", "Loops", "desc", [1], "core", ["python"], ["Write for loops"]),
        ],
        edges=[("variables", "loops")],
        detected_domain="programming",
        detected_difficulty="beginner",
        source_summary="Summary",
    )

    blueprint = await sequencer.sequence(graph)
    assert len(blueprint.units) == 1
    assert blueprint.units[0].title == "Unit 1: Fundamentals"
    assert len(blueprint.units[0].lesson_slots) == 2
