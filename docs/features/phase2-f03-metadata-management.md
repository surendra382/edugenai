# Feature: Metadata Management

**Phase:** 2 — Knowledge Base
**ID:** phase2-f03
**Status:** Done
**Depends on:** phase2-f01

---

## 1. Goal

Every uploaded document has a metadata record (board, class, keywords,
learning objectives, question types, difficulty, source) that's
auto-created on upload and editable by the admin — per SRS §9.

## 2. Scope

### In Scope
- `DocumentMetadata` table, one row per `Document`, auto-created (empty)
  when a document is uploaded
- Editable fields: `board`, `class_level`, `keywords`,
  `learning_objectives`, `question_types`, `difficulty`, `source`
- Read-only derived field: upload date (from `Document.created_at`,
  not duplicated onto `DocumentMetadata`)
- Admin UI: an "Edit Metadata" section per document row in
  `admin_knowledge_base.py`

### Out of Scope
- AI-assisted keyword/learning-objective extraction from OCR text (future
  enhancement — natural fit once phase2-f02's extracted text exists, but
  not required for v1 manual entry)
- `Board` / `Class` as first-class relational entities. Nothing in Phase 1
  models a Board or Class, and the SRS vision explicitly scopes v1 to "a
  single Class 8 student." Modeling these properly belongs with the SRS's
  Future Enhancement "Multi-Board Support." For now `board` and
  `class_level` are free-text fields the admin fills in.
- Bulk metadata editing across multiple documents

## 3. Data Model

```
DocumentMetadata
  id                   INTEGER PK
  document_id          INTEGER FK -> Document.id UNIQUE NOT NULL
  board                TEXT NULL
  class_level          TEXT NULL
  keywords             TEXT NULL     -- comma-separated
  learning_objectives  TEXT NULL
  question_types       TEXT NULL     -- comma-separated, from the fixed set in SRS Module 7
  difficulty           TEXT NULL     -- easy | medium | hard
  source               TEXT NULL
  created_at           DATETIME
  updated_at           DATETIME
```

One-to-one with `Document`. The phase2-f01 upload flow is extended to
insert a blank `DocumentMetadata` row alongside the `Document` row.

## 4. API Contract

| Method | Path | Body | Response | Notes |
|--------|------|------|----------|-------|
| GET | `/documents/{id}/metadata` | — | `200` DocumentMetadata | 404 if document missing |
| PUT | `/documents/{id}/metadata` | `{board?, class_level?, keywords?, learning_objectives?, question_types?, difficulty?, source?}` | `200` DocumentMetadata | 404 if document missing; 422 if `difficulty` not in `easy`/`medium`/`hard` |

## 5. UI Behavior

- Within `admin_knowledge_base.py`, each document row gets an "Edit
  Metadata" expander: text inputs for board/class/source, a textarea for
  keywords and learning objectives, a multiselect for question types
  (from the fixed list), a select for difficulty
- Read-only "Uploaded on `<date>`" line sourced from the Document
- Save button `PUT`s the metadata; success/error surfaced inline

## 6. Test Strategy

### Unit Tests
- Metadata schema rejects a `difficulty` value outside
  `easy`/`medium`/`hard`

### Integration Tests
- Uploading a document (phase2-f01 endpoint) auto-creates an empty
  `DocumentMetadata` row, retrievable via `GET`
- Update metadata fields → 200, reflected in a subsequent `GET`
- Update metadata for a nonexistent document → 404
- Update with an invalid `difficulty` → 422

### Manual Verification
- [x] Upload a document, confirm its metadata form loads empty without error
- [x] Fill in and save metadata, confirm it persists after a page refresh
- [x] Confirm the displayed upload date matches the document's actual
      upload time

## 7. Acceptance Criteria

- [x] All integration tests above pass
- [x] Metadata viewable and editable end-to-end from the Streamlit UI
