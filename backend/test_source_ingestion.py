import pytest
from backend.source_ingestion import SourceIngestionService, IngestionError

@pytest.mark.asyncio
async def test_transcript_ingestion():
    service = SourceIngestionService()
    doc = await service.ingest(
        material_type="transcript",
        content="This is a test transcript for AI course generation.",
        title="Test Course",
    )
    assert doc.source_type == "transcript"
    assert doc.title == "Test Course"
    assert doc.plain_text == "This is a test transcript for AI course generation."
    assert doc.access_level == "text_only"
    assert len(doc.source_hash) == 16


@pytest.mark.asyncio
async def test_file_ingestion():
    service = SourceIngestionService()
    doc = await service.ingest(
        material_type="file_upload",
        content="data:text/plain;base64,SGVsbG8gV29ybGQ=",
        filename="notes.txt",
    )
    assert doc.source_type == "file_upload"
    assert doc.plain_text == "Hello World"


@pytest.mark.asyncio
async def test_invalid_youtube_url():
    service = SourceIngestionService()
    with pytest.raises(IngestionError, match="Invalid YouTube URL"):
        await service.ingest(
            material_type="youtube_url",
            content="https://notyoutube.com/watch?v=123",
        )
