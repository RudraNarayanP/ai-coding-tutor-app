"""Tests for the keyless YouTube reader-proxy fetch/parse pipeline (offline)."""
from backend.youtube_fetch import (
    build_source_text,
    extract_chapters,
    _extract_description,
    _extract_title,
)

# Representative reader-proxy markdown (shape mirrors r.jina.ai output for a
# chaptered tutorial video).
SAMPLE_MD = """Title: Let's reproduce GPT-2 (124M) - YouTube

URL Source: https://www.youtube.com/watch?v=l8pRSuU81PU

# Let's reproduce GPT-2 (124M)

We reproduce the GPT-2 (124M) from scratch. This video covers the whole process: first we build the GPT-2 network, then we optimize training to be fast, then we set up the training run following the paper.

Chapters: [00:00:00](https://www.youtube.com/watch?v=l8pRSuU81PU) intro: reproduce GPT-2 [00:13:47](https://www.youtube.com/watch?v=l8pRSuU81PU&t=827s) SECTION 1: implementing the GPT-2 nn.Module [00:31:00](https://www.youtube.com/watch?v=l8pRSuU81PU&t=1860s) implementing the forward pass to get logits [00:52:53](https://www.youtube.com/watch?v=l8pRSuU81PU&t=3173s) cross entropy loss [01:02:00](https://www.youtube.com/watch?v=l8pRSuU81PU&t=3720s) data loader lite [02:00:18](https://www.youtube.com/watch?v=l8pRSuU81PU&t=7218s) flash attention

[1:56:20 Let's build GPT: from scratch Andrej Karpathy 7.8M views • 3 years ago Live Playlist ()](https://www.youtube.com/watch?v=kCc8FmEb1nY)
"""


def test_extract_title():
    assert _extract_title(SAMPLE_MD) == "Let's reproduce GPT-2 (124M)"


def test_extract_description_prefers_prose_not_links_or_chapters():
    desc = _extract_description(SAMPLE_MD)
    assert "reproduce the GPT-2 (124M) from scratch" in desc
    assert "watch?v=" not in desc
    assert not desc.lower().startswith("chapters")


FOLLOW_ALONG_MD = """Title: I completed the AI challenge (advanced) - YouTube

# I completed the AI challenge (advanced)

## Comments 37

huh this is a unique video concept that i've just now seen. a video where we are learning together and you clarifying your thought process throughout the lecture and making it clear for us who is also trying to understand. that's really cool. please do more of this with other advanced ML/NN topics extra extra extra extra extra extra extra padding so this comment is the longest line on the page by far and used to be mistaken for the description.

## Description

I completed the AI challenge (advanced)

If you're serious about AI, join my community. Original video: [The spelled-out intro to neural networks](https://www.youtube.com/watch?v=VMj-3S1tku0) GitHub: [https://github.com/karpathy/micrograd](https://github.com/karpathy/micrograd) In this video I follow the lecture on how to build Micrograd, how to train Neural Networks and implementing Backpropagation.

## Transcript
NaN
"""


def test_extract_description_uses_creator_block_not_comments():
    desc = _extract_description(FOLLOW_ALONG_MD)
    assert "build Micrograd" in desc
    assert "Backpropagation" in desc
    assert "github.com/karpathy/micrograd" in desc
    assert "unique video concept" not in desc


def test_extract_chapters_ordered_and_filtered():
    chapters = extract_chapters(SAMPLE_MD)
    titles = [t for _ts, t in chapters]
    # Ordered, real chapters extracted.
    assert "SECTION 1: implementing the GPT-2 nn.Module" in titles
    assert "cross entropy loss" in titles
    assert "flash attention" in titles
    # Recommendation-sidebar rows (with "views •") are filtered out.
    assert not any("views •" in t for t in titles)


def test_build_source_text_includes_chapters():
    chapters = extract_chapters(SAMPLE_MD)
    text = build_source_text("Let's reproduce GPT-2 (124M)", "desc", chapters)
    assert "Chapters:" in text
    assert "cross entropy loss" in text
