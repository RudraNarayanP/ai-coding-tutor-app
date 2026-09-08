import pytest
from unittest.mock import AsyncMock
from backend.custom_course_generator import ConceptGraphBuilder, ConceptGraph, ConceptNode
from backend.source_ingestion import SourceDocument

@pytest.mark.asyncio
async def test_concept_graph_builder_mock():
    mock_provider = AsyncMock()
    mock_provider.generate_structured.return_value = """
    {
      "detected_domain": "programming",
      "detected_difficulty": "beginner",
      "source_summary": "Intro to Python variables and loops.",
      "nodes": [
        {
          "id": "variables",
          "label": "Variables",
          "description": "Storing data",
          "source_segments": [1],
          "difficulty": "foundational",
          "domain_tags": ["python"],
          "learning_objectives": ["Define variables"]
        },
        {
          "id": "loops",
          "label": "Loops",
          "description": "Iteration",
          "source_segments": [1],
          "difficulty": "core",
          "domain_tags": ["python"],
          "learning_objectives": ["Write for loops"]
        }
      ],
      "edges": [["variables", "loops"]]
    }
    """

    builder = ConceptGraphBuilder(mock_provider)
    doc = SourceDocument("transcript", "", "hash123", "Python Course", plain_text="Variables and loops in Python.")
    graph = await builder.build(doc)

    assert graph.detected_domain == "programming"
    assert len(graph.nodes) == 2
    assert graph.nodes[0].id == "variables"
    assert graph.edges == [("variables", "loops")]
