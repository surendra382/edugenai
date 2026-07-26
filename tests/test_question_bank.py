import io
import json

import pytest
from fakes import StubLLMProvider, StubVisionExtractor
from PIL import Image

from backend.app.services import llm as llm_module
from backend.app.services import question_bank_parser
from backend.app.services import vision_extractor as vision_extractor_module


def _make_pdf_bytes(page_count: int = 2) -> bytes:
    pages = [Image.new("RGB", (100, 100), color="white") for _ in range(page_count)]
    buffer = io.BytesIO()
    pages[0].save(buffer, format="PDF", save_all=True, append_images=pages[1:])
    return buffer.getvalue()

# --- question_bank_parser.parse ---


def _item(**overrides) -> dict:
    base = {
        "question_type": "mcq",
        "stem": "2+2=?",
        "concept": "addition",
        "options": ["3", "4", "5", "6"],
        "answer": "4",
        "difficulty": "easy",
    }
    base.update(overrides)
    return base


def test_parse_accepts_valid_array():
    raw = json.dumps([_item(), _item(question_type="short_answer", stem="Define a variable.", options=None)])
    items, errors = question_bank_parser.parse(raw)
    assert len(items) == 2
    assert errors == []
    assert items[0]["options"] == ["3", "4", "5", "6"]
    assert items[1]["options"] is None


def test_parse_rejects_top_level_non_json():
    with pytest.raises(ValueError):
        question_bank_parser.parse("not json")


def test_parse_rejects_top_level_non_list():
    with pytest.raises(ValueError):
        question_bank_parser.parse(json.dumps({"not": "a list"}))


def test_parse_drops_invalid_items_but_keeps_valid_ones():
    raw = json.dumps([_item(), {"question_type": "essay", "stem": "bad type"}])
    items, errors = question_bank_parser.parse(raw)
    assert len(items) == 1
    assert items[0]["stem"] == "2+2=?"
    assert len(errors) == 1
    assert "item 1" in errors[0]


def test_parse_rejects_mcq_with_fewer_than_two_options():
    raw = json.dumps([_item(options=["only one"])])
    items, errors = question_bank_parser.parse(raw)
    assert items == []
    assert len(errors) == 1


def test_parse_tolerates_missing_answer():
    raw = json.dumps([_item(answer=None)])
    items, errors = question_bank_parser.parse(raw)
    assert len(items) == 1
    assert items[0]["answer"] is None
    assert errors == []


def test_parse_cleans_latex_math_notation():
    raw = json.dumps([_item(stem="Simplify \\sqrt{16}.", options=None, question_type="short_answer")])
    items, _ = question_bank_parser.parse(raw)
    assert items[0]["stem"] == "Simplify √16."


def test_parse_recovers_from_latex_style_backslash_escape():
    raw = '[{"question_type": "short_answer", "stem": "Simplify \\sqrt{16}.", "difficulty": "easy"}]'
    items, _ = question_bank_parser.parse(raw)
    assert items[0]["stem"] == "Simplify √16."


def test_parse_strips_code_fences():
    raw = "```json\n" + json.dumps([_item(options=None, question_type="short_answer")]) + "\n```"
    items, _ = question_bank_parser.parse(raw)
    assert len(items) == 1


# --- import/list/delete API ---


def _create_chapter(client) -> dict:
    subject = client.post("/subjects", json={"name": "Mathematics"}).json()
    return client.post(f"/subjects/{subject['id']}/chapters", json={"name": "Algebra"}).json()


def _import(client, chapter_id: int, filename: str = "page.png") -> dict:
    return client.post(
        f"/chapters/{chapter_id}/question-bank/import",
        data={"class_grade": "8", "source": "olympiad"},
        files={"images": (filename, b"fake-image-bytes", "image/png")},
    ).json()


def test_import_creates_rows_from_stub_extractor(client, monkeypatch):
    chapter = _create_chapter(client)
    monkeypatch.setattr(
        vision_extractor_module,
        "vision_extractor",
        StubVisionExtractor(response=json.dumps([_item(), _item(stem="3+3=?")])),
    )

    response = client.post(
        f"/chapters/{chapter['id']}/question-bank/import",
        data={"class_grade": "8", "source": "olympiad"},
        files={"images": ("page.png", b"fake-image-bytes", "image/png")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["created"] == 2
    assert body["errors"] == []
    assert {item["stem"] for item in body["items"]} == {"2+2=?", "3+3=?"}

    listed = client.get(f"/chapters/{chapter['id']}/question-bank").json()
    assert len(listed) == 2


def test_import_partial_item_failure_keeps_valid_items(client, monkeypatch):
    chapter = _create_chapter(client)
    monkeypatch.setattr(
        vision_extractor_module,
        "vision_extractor",
        StubVisionExtractor(
            response=json.dumps([_item(), {"question_type": "essay", "stem": "bad"}])
        ),
    )

    response = _import(client, chapter["id"])
    assert response["created"] == 1
    assert len(response["errors"]) == 1
    assert "1 item(s) skipped" in response["errors"][0]["error"]


def test_import_total_failure_image_reports_error_and_creates_nothing(client, monkeypatch):
    chapter = _create_chapter(client)
    monkeypatch.setattr(
        vision_extractor_module, "vision_extractor", StubVisionExtractor(response="not valid json")
    )

    response = _import(client, chapter["id"])
    assert response["created"] == 0
    assert len(response["errors"]) == 1
    assert response["errors"][0]["filename"] == "page.png"


def test_import_pdf_extracts_one_call_per_page(client, monkeypatch):
    chapter = _create_chapter(client)
    monkeypatch.setattr(
        vision_extractor_module,
        "vision_extractor",
        StubVisionExtractor(response=json.dumps([_item()])),
    )

    response = client.post(
        f"/chapters/{chapter['id']}/question-bank/import",
        data={"class_grade": "8", "source": "olympiad"},
        files={"images": ("paper.pdf", _make_pdf_bytes(page_count=2), "application/pdf")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["created"] == 2
    assert body["errors"] == []

    listed = client.get(f"/chapters/{chapter['id']}/question-bank").json()
    assert len(listed) == 2


def test_import_unreadable_pdf_reports_error_and_creates_nothing(client):
    chapter = _create_chapter(client)

    response = client.post(
        f"/chapters/{chapter['id']}/question-bank/import",
        data={"class_grade": "8", "source": "olympiad"},
        files={"images": ("paper.pdf", b"not a real pdf", "application/pdf")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["created"] == 0
    assert len(body["errors"]) == 1
    assert body["errors"][0]["filename"] == "paper.pdf"


def test_import_to_nonexistent_chapter_returns_404(client):
    response = client.post(
        "/chapters/999/question-bank/import",
        data={"class_grade": "8", "source": "olympiad"},
        files={"images": ("page.png", b"fake-image-bytes", "image/png")},
    )
    assert response.status_code == 404


def test_list_filters_by_difficulty(client, monkeypatch):
    chapter = _create_chapter(client)
    monkeypatch.setattr(
        vision_extractor_module,
        "vision_extractor",
        StubVisionExtractor(response=json.dumps([_item(difficulty="easy"), _item(difficulty="hard")])),
    )
    _import(client, chapter["id"])

    response = client.get(f"/chapters/{chapter['id']}/question-bank", params={"difficulty": "hard"})
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["difficulty"] == "hard"


def test_delete_removes_row(client, monkeypatch):
    chapter = _create_chapter(client)
    monkeypatch.setattr(
        vision_extractor_module, "vision_extractor", StubVisionExtractor(response=json.dumps([_item()]))
    )
    imported = _import(client, chapter["id"])
    item_id = imported["items"][0]["id"]

    response = client.delete(f"/question-bank/{item_id}")
    assert response.status_code == 204

    listed = client.get(f"/chapters/{chapter['id']}/question-bank").json()
    assert listed == []


def test_delete_missing_item_returns_404(client):
    response = client.delete("/question-bank/999")
    assert response.status_code == 404


# --- generation pipeline exemplar lookup ---


def test_generation_uses_question_bank_exemplars(client, monkeypatch):
    chapter = _create_chapter(client)
    monkeypatch.setattr(
        vision_extractor_module,
        "vision_extractor",
        StubVisionExtractor(
            response=json.dumps(
                [_item(stem="What is the square root of 16?", difficulty="easy")]
            )
        ),
    )
    _import(client, chapter["id"])

    generated_response = json.dumps(
        [{"type": "mcq", "text": "New question", "options": ["A", "B", "C", "D"]}]
    )
    monkeypatch.setattr(llm_module, "llm_provider", StubLLMProvider(response=generated_response))

    response = client.post(
        f"/chapters/{chapter['id']}/question-sets",
        json={"difficulty": "easy", "question_types": ["mcq"], "num_questions": 1},
    )
    assert response.status_code == 202
    question_set_id = response.json()["id"]
    assert client.get(f"/question-sets/{question_set_id}").json()["status"] == "completed"
