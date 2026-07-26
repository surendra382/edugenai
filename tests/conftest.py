import pytest
from fastapi.testclient import TestClient
from fakes import StubLLMProvider, StubVisionExtractor
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.config import settings
from backend.app.db.session import Base, get_db
from backend.app.main import app
from backend.app.services import llm as llm_module
from backend.app.services import vision_extractor as vision_extractor_module


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(settings, "knowledge_base_dir", str(tmp_path / "knowledge_base"))
    monkeypatch.setattr(settings, "log_dir", str(tmp_path / "logs"))
    monkeypatch.setattr(llm_module, "llm_provider", StubLLMProvider())
    monkeypatch.setattr(vision_extractor_module, "vision_extractor", StubVisionExtractor())

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
