from pathlib import Path

import chromadb
from chromadb.api.models.Collection import Collection

from backend.app.core.config import settings

COLLECTION_NAME = "knowledge_base"


def get_collection() -> Collection:
    client = chromadb.PersistentClient(path=str(Path(settings.knowledge_base_dir) / ".chroma"))
    return client.get_or_create_collection(COLLECTION_NAME)
