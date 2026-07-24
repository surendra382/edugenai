# Feature: Chapter Management

**Phase:** 1 — Foundation
**ID:** phase1-f03
**Status:** Done
**Depends on:** phase1-f01, phase1-f02

---

## 1. Goal

Admin can create, view, edit, delete, and reorder Chapters within a Subject
(e.g. Mathematics → Rational Numbers, Algebra, Linear Equations) through the
admin UI. Chapters are the unit everything downstream (knowledge base,
question generation) attaches to.

## 2. Scope

### In Scope
- `Chapter` table: `id`, `subject_id` (FK), `name`, `order`, `created_at`,
  `updated_at`
- Full CRUD API scoped under a subject
- Reorder endpoint (drag-and-drop or up/down buttons in UI)
- Admin UI: select a subject → see/manage its chapters
- Validation: name required and unique *within* its subject (two different
  subjects may each have a "Chapter 1")

### Out of Scope
- File/material upload against a chapter (Phase 2)
- Cross-subject chapter moves (a chapter always belongs to the subject it
  was created under)

## 3. Data Model

```
Chapter
  id            INTEGER PK
  subject_id    INTEGER FK -> Subject.id NOT NULL
  name          TEXT NOT NULL
  order         INTEGER NOT NULL        -- 0-based position within subject
  created_at    DATETIME
  updated_at    DATETIME

  UNIQUE(subject_id, name)
```

## 4. API Contract

| Method | Path | Body | Response | Notes |
|--------|------|------|----------|-------|
| POST | `/subjects/{subject_id}/chapters` | `{name}` | `201` Chapter | appended at end; 404 if subject missing; 409 if name dupes within subject |
| GET | `/subjects/{subject_id}/chapters` | — | `200` Chapter[] | ordered by `order` |
| GET | `/chapters/{id}` | — | `200` Chapter | 404 if missing |
| PUT | `/chapters/{id}` | `{name}` | `200` Chapter | 404/409 as above |
| DELETE | `/chapters/{id}` | — | `204` | blocked (409) if knowledge base content exists, once Phase 2 lands; unconditional for now |
| PATCH | `/subjects/{subject_id}/chapters/reorder` | `{ordered_ids: [...]}` | `200` Chapter[] | full reorder in one call, 400 if id set mismatches |

## 5. UI Behavior

- `frontend/pages/admin_chapters.py`
- Subject picker at top (reuses F02's subject list)
- Selecting a subject loads its chapters in order, with Edit/Delete/Up/Down
  controls per row
- "Add Chapter" form scoped to the selected subject
- Empty state: "No chapters yet for <Subject> — add the first one above"

## 6. Test Strategy

### Unit Tests
- Chapter schema validation rejects empty/whitespace-only name
- New chapter defaults to `order = max(existing order) + 1`

### Integration Tests
- Create chapter under a subject → 201, appears in that subject's GET list
- Create chapter under nonexistent subject → 404
- Create duplicate name within same subject → 409
- Same chapter name under a *different* subject → 201 (allowed)
- Update chapter name → 200, reflected in GET
- Delete chapter → 204, gone from list, remaining chapters keep valid order
- Reorder: submit new order → GET reflects new order
- Reorder with an id not belonging to that subject → 400
- Deleting a Subject (F02) that still has chapters → 409, verifies F02/F03
  integration point

### Manual Verification
- [x] Add 3 chapters to a subject, confirm order shown matches creation order
- [x] Reorder via UI (up/down), confirm order persists after refresh
- [x] Add same chapter name to two different subjects — both succeed
- [x] Delete a chapter, confirm remaining ones still display correctly ordered
- [x] Confirm deleting the parent subject is blocked while chapters remain

## 7. Acceptance Criteria

- [x] All integration tests above pass, including the F02 cross-feature delete-block test
- [x] Full CRUD + reorder usable end-to-end from the Streamlit UI
