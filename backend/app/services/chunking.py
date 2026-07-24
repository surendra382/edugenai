def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    if not text:
        return []

    chunks = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + chunk_size, length)
        chunks.append(text[start:end])
        if end == length:
            break
        start = end - overlap
    return chunks
