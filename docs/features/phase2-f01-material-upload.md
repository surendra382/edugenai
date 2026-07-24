# Feature: Material Upload & Storage

**Phase:** 2 — Knowledge Base
**ID:** phase2-f01
**Status:** Done
**Depends on:** phase1-f03

---

## 1. Goal

Admin can upload files (textbook page images, PDFs, worksheets, sample
papers, notes) against a specific Chapter, see them listed with basic
status, and delete them. Files persist on disk with a DB-tracked row per
document — the raw material F02 (OCR) and later features build on.

## 2. Scope

### In Scope
- `Document` table: one row per uploaded file, scoped to a Chapter
- Storage convention: `knowledge_base/{subject_id}/{chapter_id}/{material_type}/{document_id}_{original_filename}`
  (per SRS §8's repository structure, keyed by stable IDs rather than
  names so renaming a Subject/Chapter never breaks existing file paths)
- `Settings` extended with `knowledge_base_dir` (default `./knowledge_base`)
  and `max_upload_size_mb` (default `20`)
- Full upload/list/get/delete API scoped under a chapter
- Validation: allowed file types only (`.jpg`, `.jpeg`, `.png` for images;
  `.pdf` for documents), size limit enforced, `material_type` required
  from a fixed set (`textbook_page`, `worksheet`, `sample_paper`, `notes`,
  `question_paper`)
- Admin UI: subject/chapter picker (reuses F03's cascading-select pattern),
  upload form, document table with Delete

### Out of Scope
- OCR / text extraction (phase2-f02)
- Metadata beyond `material_type` (phase2-f03)
- Embeddings / vector DB (phase2-f04)
- Retrieval (phase2-f05)
- Replacing/re-uploading a file in place — delete and re-upload instead

## 3. Data Model

```
Document
  id                 INTEGER PK
  chapter_id         INTEGER FK -> Chapter.id NOT NULL
  material_type      TEXT NOT NULL   -- textbook_page | worksheet | sample_paper | notes | question_paper
  file_type          TEXT NOT NULL   -- image | pdf
  original_filename  TEXT NOT NULL
  storage_path       TEXT UNIQUE NOT NULL
  file_size_bytes    INTEGER NOT NULL
  status             TEXT NOT NULL DEFAULT 'uploaded'   -- extended by phase2-f02 / phase2-f04
  created_at         DATETIME
  updated_at         DATETIME
```

`status` starts with a single value (`uploaded`) in this feature. It's the
same column phase2-f02 (OCR) and phase2-f04 (embeddings) extend with their
own states — introduced now because the UI needs *some* status to display,
not because this feature implements those transitions.

## 4. API Contract

| Method | Path | Body | Response | Notes |
|--------|------|------|----------|-------|
| POST | `/chapters/{chapter_id}/documents` | multipart: `file`, `material_type` | `201` Document | 404 if chapter missing; 415 if file extension not allowed; 413 if file exceeds `max_upload_size_mb` |
| GET | `/chapters/{chapter_id}/documents` | — | `200` Document[] | sorted by `created_at` desc; 404 if chapter missing |
| GET | `/documents/{id}` | — | `200` Document | 404 if missing |
| DELETE | `/documents/{id}` | — | `204` | removes DB row and the on-disk file; 404 if missing |

## 5. UI Behavior

- `frontend/pages/admin_knowledge_base.py`
- Subject picker → Chapter picker at top (same cascading pattern as
  `admin_chapters.py`)
- Upload form: file picker + `material_type` dropdown + "Upload" button
- Table of documents for the selected chapter: filename, material type,
  file type, size, status, uploaded date, Delete button with confirmation
- Rejected upload (bad type / too large) shows the API's error message
  rather than failing silently
- Empty state: "No material uploaded yet for `<Chapter>` — upload your
  first file above"

## 6. Test Strategy

### Unit Tests
- Upload validation rejects a disallowed file extension
- Upload validation rejects a file over `max_upload_size_mb`

### Integration Tests
- Upload a valid image → 201, appears in the chapter's GET list, file
  exists on disk at the expected path
- Upload a valid PDF → 201
- Upload under a nonexistent chapter → 404
- Upload a disallowed file type → 415
- Upload an oversized file → 413
- Delete a document → 204, gone from GET list, file removed from disk
- Delete a nonexistent document → 404
- Get document by id → 200; nonexistent id → 404

### Manual Verification
- [x] Upload an image and a PDF via the UI, see both appear in the table
- [x] Try uploading an unsupported file type, see the error surfaced
- [x] Delete an uploaded file, confirm it's gone from the table and from disk
- [x] Switch chapters, confirm the document list scopes correctly per chapter

## 7. Acceptance Criteria

- [x] All integration tests above pass
- [x] Upload / list / delete usable end-to-end from the Streamlit UI
