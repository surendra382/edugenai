# Feature: Subject Management

**Phase:** 1 — Foundation
**ID:** phase1-f02
**Status:** Done
**Depends on:** phase1-f01

---

## 1. Goal

Admin can create, view, edit, and delete Subjects (e.g. Mathematics,
Science) through the Streamlit admin UI, backed by a real API and DB table.
Subjects are the top-level container Chapters (F03) will hang off of.

## 2. Scope

### In Scope
- `Subject` table: `id`, `name` (unique), `created_at`, `updated_at`
- Full CRUD API
- Admin UI page: list subjects, add subject form, inline edit, delete with
  confirmation
- Validation: name required, non-empty, unique (case-insensitive)

### Out of Scope
- Chapters (F03)
- Any file/material upload
- Reordering (subjects are alphabetically listed for now)

## 3. Data Model

```
Subject
  id            INTEGER PK
  name          TEXT UNIQUE NOT NULL
  created_at    DATETIME
  updated_at    DATETIME
```

## 4. API Contract

| Method | Path | Body | Response | Notes |
|--------|------|------|----------|-------|
| POST | `/subjects` | `{name}` | `201` Subject | 409 if name exists |
| GET | `/subjects` | — | `200` Subject[] | sorted by name |
| GET | `/subjects/{id}` | — | `200` Subject | 404 if missing |
| PUT | `/subjects/{id}` | `{name}` | `200` Subject | 404/409 as above |
| DELETE | `/subjects/{id}` | — | `204` | see delete policy below |

**Delete policy:** deleting a Subject with existing Chapters is **blocked**
(`409`) until the admin deletes/moves those chapters first. No silent
cascade — avoids accidental data loss on a knowledge base that took real
effort to build. The `Chapter` table doesn't exist until F03, so the block
check itself is implemented and tested as part of F03 (see that doc's Test
Strategy). Within F02, with no Chapter table to check against, `DELETE`
removes the subject unconditionally.

## 5. UI Behavior

- `frontend/pages/admin_subjects.py`
- Table of existing subjects with Edit/Delete buttons
- "Add Subject" form above/below the table
- Delete shows a confirmation dialog; if blocked (chapters exist), shows the
  API's error message rather than failing silently
- Empty state: "No subjects yet — add your first one above"

## 6. Test Strategy

### Unit Tests
- Subject schema validation rejects empty/whitespace-only name

### Integration Tests
- Create subject → 201, appears in GET list
- Create duplicate name (any case) → 409
- Update subject name → 200, reflected in GET
- Update to a name that collides with another subject → 409
- Delete subject with no chapters → 204, gone from GET list
- Get/Update/Delete on nonexistent id → 404

Note: "delete subject with chapters → 409" is **not** an F02 test — it's
owned by F03 (phase1-f03-chapter-management.md §6), since it requires the
`Chapter` table F03 introduces.

### Manual Verification
- [x] Add a subject via UI, see it appear immediately
- [x] Try adding a duplicate name, see error surfaced in UI
- [x] Edit a subject's name, confirm persisted after page refresh
- [x] Delete an empty subject, confirm it's gone
- [x] (After F03 exists) confirm deleting a subject with chapters is blocked

## 7. Acceptance Criteria

- [x] All integration tests above pass
- [x] Full CRUD usable end-to-end from the Streamlit UI without touching the API directly
