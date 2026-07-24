from backend.app.services.chunking import chunk_text


def test_chunk_text_splits_into_expected_boundaries():
    text = "a" * 1000
    chunks = chunk_text(text, chunk_size=500, overlap=50)

    assert len(chunks) == 3
    assert chunks[0] == text[0:500]
    assert chunks[1] == text[450:950]
    assert chunks[2] == text[900:1000]


def test_chunk_text_empty_returns_no_chunks():
    assert chunk_text("") == []


def test_chunk_text_shorter_than_chunk_size_returns_single_chunk():
    text = "short text"
    assert chunk_text(text, chunk_size=500, overlap=50) == [text]
