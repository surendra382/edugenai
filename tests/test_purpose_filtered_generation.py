import json
import logging

import pytest
from fakes import StubLLMProvider, StubVisionExtractor
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.db.session import Base
from backend.app.models.chapter import Chapter
from backend.app.models.question_bank_item import QuestionBankItem
from backend.app.models.subject import Subject
from backend.app.schemas.question_set import ChapterSelection, QuestionSetCreate, QuestionSetCreateMulti
from backend.app.services import llm as llm_module
from backend.app.services import vision_extractor as vision_extractor_module
from backend.app.services.generation_pipeline import _select_exemplars
from backend.app.services.pdf_export import build_question_paper_pdf
from backend.app.services.prompt_builder import build_prompt

# --- unit: _select_exemplars ---


@pytest.fixture
def db_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'unit.db'}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _make_chapter(db) -> Chapter:
    subject = Subject(name="Mathematics")
    db.add(subject)
    db.flush()
    chapter = Chapter(subject_id=subject.id, name="Algebra", order=0)
    db.add(chapter)
    db.flush()
    return chapter


def _make_item(db, chapter_id: int, *, difficulty: str = "easy", source: str = "sainik") -> QuestionBankItem:
    item = QuestionBankItem(
        chapter_id=chapter_id,
        class_grade="8",
        source=source,
        question_type="mcq",
        stem=f"stem-{difficulty}-{source}",
        difficulty=difficulty,
    )
    db.add(item)
    db.flush()
    return item


def test_select_exemplars_prefers_exact_source_and_difficulty_match(db_session):
    chapter = _make_chapter(db_session)
    exact = [_make_item(db_session, chapter.id, difficulty="easy", source="sainik") for _ in range(2)]
    _make_item(db_session, chapter.id, difficulty="easy", source="olympiad")
    _make_item(db_session, chapter.id, difficulty="hard", source="sainik")
    db_session.flush()

    # limit=2 matches exactly how many exact-tier rows exist, so no
    # lower-priority tier needs to contribute — isolates the "prefer exact"
    # behavior from the separate backfill behavior covered below.
    selected, tiers = _select_exemplars(db_session, chapter.id, "easy", "sainik", limit=2)

    assert {item.id for item in selected} == {item.id for item in exact}
    assert tiers == {"exact": 2}


def test_select_exemplars_backfills_to_difficulty_only_then_chapter_only(db_session):
    chapter = _make_chapter(db_session)
    exact = _make_item(db_session, chapter.id, difficulty="easy", source="sainik")
    difficulty_only = _make_item(db_session, chapter.id, difficulty="easy", source="olympiad")
    chapter_only = _make_item(db_session, chapter.id, difficulty="hard", source="cbse_textbook")
    db_session.flush()

    selected, tiers = _select_exemplars(db_session, chapter.id, "easy", "sainik", limit=8)

    assert {item.id for item in selected} == {exact.id, difficulty_only.id, chapter_only.id}
    assert tiers == {"exact": 1, "difficulty_only": 1, "chapter_only": 1}
    # every id appears exactly once across tiers, never duplicated
    assert len(selected) == len({item.id for item in selected})


def test_select_exemplars_with_no_source_matches_pre_feature_behavior(db_session):
    chapter = _make_chapter(db_session)
    matching_difficulty = [
        _make_item(db_session, chapter.id, difficulty="easy", source="sainik") for _ in range(2)
    ]
    other_difficulty = _make_item(db_session, chapter.id, difficulty="hard", source="olympiad")
    db_session.flush()

    selected, tiers = _select_exemplars(db_session, chapter.id, "easy", None, limit=8)

    assert "exact" not in tiers
    assert {item.id for item in selected} == {item.id for item in matching_difficulty} | {
        other_difficulty.id
    }
    assert tiers == {"difficulty_only": 2, "chapter_only": 1}


def test_select_exemplars_respects_limit_across_tiers(db_session):
    chapter = _make_chapter(db_session)
    for _ in range(3):
        _make_item(db_session, chapter.id, difficulty="easy", source="sainik")
    for _ in range(3):
        _make_item(db_session, chapter.id, difficulty="easy", source="olympiad")

    selected, tiers = _select_exemplars(db_session, chapter.id, "easy", "sainik", limit=4)

    assert len(selected) == 4
    assert tiers["exact"] == 3
    assert tiers["difficulty_only"] == 1


# --- unit: build_prompt ---


def test_build_prompt_includes_purpose_instruction_when_source_set():
    prompt = build_prompt(
        subject_name="Mathematics",
        chapter_name="Algebra",
        difficulty="easy",
        question_types=["mcq"],
        num_questions=1,
        context_chunks=[],
        source="sainik",
    )
    assert 'style of a "sainik" exam' in prompt


def test_build_prompt_omits_purpose_instruction_when_source_none():
    prompt = build_prompt(
        subject_name="Mathematics",
        chapter_name="Algebra",
        difficulty="easy",
        question_types=["mcq"],
        num_questions=1,
        context_chunks=[],
    )
    assert "style of a" not in prompt


# --- unit: build_question_paper_pdf ---


def _pdf_chapters() -> list[dict]:
    return [{"chapter_id": 1, "chapter_name": "Algebra"}]


def _pdf_questions() -> list[dict]:
    return [
        {
            "question_index": 0,
            "chapter_id": 1,
            "question_type": "mcq",
            "text": "2+2=?",
            "options": ["3", "4", "5", "6"],
            "answer": "4",
        }
    ]


def test_pdf_header_includes_purpose_when_set():
    pdf_bytes = build_question_paper_pdf(
        subject_name="Mathematics",
        chapters=_pdf_chapters(),
        difficulty="easy",
        questions=_pdf_questions(),
        include_answers=False,
        source="Sainik",
    )
    assert b"Sainik" in pdf_bytes


def test_pdf_header_unchanged_when_source_none():
    with_none = build_question_paper_pdf(
        subject_name="Mathematics",
        chapters=_pdf_chapters(),
        difficulty="easy",
        questions=_pdf_questions(),
        include_answers=False,
    )
    with_explicit_none = build_question_paper_pdf(
        subject_name="Mathematics",
        chapters=_pdf_chapters(),
        difficulty="easy",
        questions=_pdf_questions(),
        include_answers=False,
        source=None,
    )
    assert with_none == with_explicit_none


# --- unit: schema accepts source omitted / None / string ---


def test_question_set_create_accepts_source_omitted():
    payload = QuestionSetCreate(difficulty="easy", question_types=["mcq"], num_questions=1)
    assert payload.source is None


def test_question_set_create_accepts_source_string():
    payload = QuestionSetCreate(
        difficulty="easy", question_types=["mcq"], num_questions=1, source="olympiad"
    )
    assert payload.source == "olympiad"


def test_question_set_create_multi_accepts_source():
    payload = QuestionSetCreateMulti(
        chapters=[ChapterSelection(chapter_id=1, num_questions=1)],
        difficulty="easy",
        question_types=["mcq"],
        source="cbse_textbook",
    )
    assert payload.source == "cbse_textbook"


# --- integration ---


def _create_chapter(client) -> dict:
    subject = client.post("/subjects", json={"name": "Mathematics"}).json()
    return client.post(f"/subjects/{subject['id']}/chapters", json={"name": "Algebra"}).json()


def _bank_item(difficulty: str = "easy") -> dict:
    # `source` is admin-supplied per import batch (see _import_items), not
    # part of the extracted item — QuestionBankItem.source never comes from
    # this dict.
    return {
        "question_type": "mcq",
        "stem": f"stem-{difficulty}",
        "concept": "concept",
        "options": ["A", "B", "C", "D"],
        "answer": "A",
        "difficulty": difficulty,
    }


def _import_items(client, chapter_id: int, items: list[dict], monkeypatch, *, source: str) -> None:
    monkeypatch.setattr(
        vision_extractor_module, "vision_extractor", StubVisionExtractor(response=json.dumps(items))
    )
    response = client.post(
        f"/chapters/{chapter_id}/question-bank/import",
        data={"class_grade": "8", "source": source},
        files={"images": ("page.png", b"fake-image-bytes", "image/png")},
    )
    assert response.status_code == 201


def _mcq_response(count: int = 1) -> str:
    return json.dumps(
        [{"type": "mcq", "text": f"Question {i}", "options": ["A", "B", "C", "D"]} for i in range(count)]
    )


def test_sources_endpoint_returns_distinct_sorted_values(client, monkeypatch):
    chapter = _create_chapter(client)
    _import_items(client, chapter["id"], [_bank_item()], monkeypatch, source="sainik")
    _import_items(client, chapter["id"], [_bank_item()], monkeypatch, source="olympiad")

    response = client.get(f"/chapters/{chapter['id']}/question-bank/sources")
    assert response.status_code == 200
    assert response.json() == ["olympiad", "sainik"]


def test_sources_endpoint_empty_for_chapter_with_no_imports(client):
    chapter = _create_chapter(client)
    response = client.get(f"/chapters/{chapter['id']}/question-bank/sources")
    assert response.status_code == 200
    assert response.json() == []


def test_sources_endpoint_404_for_missing_chapter(client):
    response = client.get("/chapters/999/question-bank/sources")
    assert response.status_code == 404


def test_generation_with_matching_source_uses_exact_tier(client, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    chapter = _create_chapter(client)
    _import_items(client, chapter["id"], [_bank_item(difficulty="easy")], monkeypatch, source="sainik")

    monkeypatch.setattr(llm_module, "llm_provider", StubLLMProvider(response=_mcq_response(1)))
    response = client.post(
        f"/chapters/{chapter['id']}/question-sets",
        json={
            "difficulty": "easy",
            "source": "sainik",
            "question_types": ["mcq"],
            "num_questions": 1,
        },
    )
    question_set_id = response.json()["id"]
    assert client.get(f"/question-sets/{question_set_id}").json()["status"] == "completed"

    lookup_records = [r for r in caplog.records if getattr(r, "event", None) == "question_bank.lookup"]
    assert len(lookup_records) == 1
    assert lookup_records[0].source_requested == "sainik"
    assert lookup_records[0].tier_breakdown == {"exact": 1}


def test_generation_with_source_but_no_matches_falls_back_and_still_completes(client, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    chapter = _create_chapter(client)
    _import_items(
        client, chapter["id"], [_bank_item(difficulty="easy")], monkeypatch, source="cbse_textbook"
    )

    monkeypatch.setattr(llm_module, "llm_provider", StubLLMProvider(response=_mcq_response(1)))
    response = client.post(
        f"/chapters/{chapter['id']}/question-sets",
        json={
            "difficulty": "easy",
            "source": "sainik",
            "question_types": ["mcq"],
            "num_questions": 1,
        },
    )
    question_set_id = response.json()["id"]
    assert client.get(f"/question-sets/{question_set_id}").json()["status"] == "completed"

    lookup_records = [r for r in caplog.records if getattr(r, "event", None) == "question_bank.lookup"]
    assert lookup_records[0].source_requested == "sainik"
    assert "exact" not in lookup_records[0].tier_breakdown
    assert lookup_records[0].tier_breakdown.get("difficulty_only") == 1


def test_generation_with_source_none_is_unchanged(client, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    chapter = _create_chapter(client)
    monkeypatch.setattr(llm_module, "llm_provider", StubLLMProvider(response=_mcq_response(1)))

    response = client.post(
        f"/chapters/{chapter['id']}/question-sets",
        json={"difficulty": "easy", "question_types": ["mcq"], "num_questions": 1},
    )
    question_set_id = response.json()["id"]
    assert client.get(f"/question-sets/{question_set_id}").json()["status"] == "completed"

    lookup_records = [r for r in caplog.records if getattr(r, "event", None) == "question_bank.lookup"]
    assert lookup_records[0].source_requested is None


def test_pdf_export_includes_purpose_when_set(client, monkeypatch):
    chapter = _create_chapter(client)
    monkeypatch.setattr(llm_module, "llm_provider", StubLLMProvider(response=_mcq_response(1)))

    response = client.post(
        f"/chapters/{chapter['id']}/question-sets",
        json={
            "difficulty": "easy",
            "source": "Olympiad",
            "question_types": ["mcq"],
            "num_questions": 1,
        },
    )
    question_set_id = response.json()["id"]
    assert client.get(f"/question-sets/{question_set_id}").json()["status"] == "completed"

    pdf_response = client.get(f"/question-sets/{question_set_id}/pdf")
    assert pdf_response.status_code == 200
    assert b"Olympiad" in pdf_response.content


def test_question_set_read_round_trips_source(client, monkeypatch):
    chapter = _create_chapter(client)
    monkeypatch.setattr(llm_module, "llm_provider", StubLLMProvider(response=_mcq_response(1)))

    response = client.post(
        f"/chapters/{chapter['id']}/question-sets",
        json={
            "difficulty": "easy",
            "source": "olympiad",
            "question_types": ["mcq"],
            "num_questions": 1,
        },
    )
    assert response.json()["source"] == "olympiad"

    question_set_id = response.json()["id"]
    fetched = client.get(f"/question-sets/{question_set_id}").json()
    assert fetched["source"] == "olympiad"

    history = client.get("/question-sets", params={"subject_id": fetched["subject_id"]}).json()
    assert history[0]["source"] == "olympiad"


def test_question_set_without_source_returns_null(client, monkeypatch):
    chapter = _create_chapter(client)
    monkeypatch.setattr(llm_module, "llm_provider", StubLLMProvider(response=_mcq_response(1)))

    response = client.post(
        f"/chapters/{chapter['id']}/question-sets",
        json={"difficulty": "easy", "question_types": ["mcq"], "num_questions": 1},
    )
    assert response.json()["source"] is None
