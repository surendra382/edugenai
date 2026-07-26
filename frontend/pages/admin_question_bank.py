import os

import requests
import streamlit as st

BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")

QUESTION_TYPES = ["mcq", "true_false", "short_answer", "numerical", "fill_blank"]
DIFFICULTY_LEVELS = ["easy", "medium", "hard"]


def fetch_subjects() -> list[dict]:
    response = requests.get(f"{BACKEND_URL}/subjects", timeout=5)
    response.raise_for_status()
    return response.json()


def fetch_chapters(subject_id: int) -> list[dict]:
    response = requests.get(f"{BACKEND_URL}/subjects/{subject_id}/chapters", timeout=5)
    response.raise_for_status()
    return response.json()


def fetch_question_bank_items(
    chapter_id: int, difficulty: str | None, question_type: str | None
) -> requests.Response:
    params = {}
    if difficulty:
        params["difficulty"] = difficulty
    if question_type:
        params["type"] = question_type
    return requests.get(
        f"{BACKEND_URL}/chapters/{chapter_id}/question-bank", params=params, timeout=5
    )


def import_question_bank(
    chapter_id: int, class_grade: str, source: str, files: list
) -> requests.Response:
    return requests.post(
        f"{BACKEND_URL}/chapters/{chapter_id}/question-bank/import",
        data={"class_grade": class_grade, "source": source},
        files=[("images", (file.name, file.getvalue())) for file in files],
        # A multi-page PDF can mean dozens of Gemini calls; the backend runs
        # them concurrently (bounded) but a large scanned chapter can still
        # take several minutes end to end.
        timeout=900,
    )


def delete_question_bank_item(item_id: int) -> requests.Response:
    return requests.delete(f"{BACKEND_URL}/question-bank/{item_id}", timeout=5)


def error_detail(response: requests.Response, fallback: str) -> str:
    try:
        return response.json().get("detail", fallback)
    except ValueError:
        return fallback


st.set_page_config(page_title="Question Bank - EduGenAI", layout="wide")
st.title("Question Bank")

try:
    subjects = fetch_subjects()
except requests.RequestException:
    st.error("Backend unreachable")
    st.stop()

if not subjects:
    st.info("No subjects yet — add one on the Subjects page first")
    st.stop()

subject_names = {subject["id"]: subject["name"] for subject in subjects}
selected_subject_id = st.selectbox(
    "Subject",
    options=list(subject_names.keys()),
    format_func=lambda sid: subject_names[sid],
)

try:
    chapters = fetch_chapters(selected_subject_id)
except requests.RequestException:
    st.error("Backend unreachable")
    st.stop()

if not chapters:
    st.info("No chapters yet for this subject — add one on the Chapters page first")
    st.stop()

chapter_names = {chapter["id"]: chapter["name"] for chapter in chapters}
selected_chapter_id = st.selectbox(
    "Chapter",
    options=list(chapter_names.keys()),
    format_func=lambda cid: chapter_names[cid],
)

st.subheader("Import Questions")
with st.form("import_question_bank_form", clear_on_submit=True):
    uploaded_files = st.file_uploader(
        "Question paper images or PDFs",
        type=["jpg", "jpeg", "png", "pdf"],
        accept_multiple_files=True,
    )
    class_grade = st.text_input("Class")
    source = st.text_input("Source", placeholder="sainik / olympiad / cbse_textbook / ...")
    submitted = st.form_submit_button("Import")
    if submitted:
        if not uploaded_files:
            st.session_state["question_bank_import_result"] = {"error": "Choose at least one image first"}
        elif not class_grade.strip():
            st.session_state["question_bank_import_result"] = {"error": "Class is required"}
        elif not source.strip():
            st.session_state["question_bank_import_result"] = {"error": "Source is required"}
        else:
            response = import_question_bank(
                selected_chapter_id, class_grade.strip(), source.strip(), uploaded_files
            )
            if response.status_code == 201:
                st.session_state["question_bank_import_result"] = {"success": response.json()}
            else:
                st.session_state["question_bank_import_result"] = {
                    "error": error_detail(response, "Failed to import questions")
                }

# Submitting the form above already triggers a rerun on its own, which would
# discard any local `response`/`result` variable before it could be shown —
# stashing the outcome in session_state and rendering it here (once, then
# clearing it) is what makes success/warning/error messages actually survive
# long enough to be read, instead of flashing and disappearing.
import_result = st.session_state.pop("question_bank_import_result", None)
if import_result is not None:
    if "error" in import_result:
        st.error(import_result["error"])
    else:
        result = import_result["success"]
        st.success(f"Imported {result['created']} question(s)")
        for entry in result["errors"]:
            st.warning(f"{entry['filename']}: {entry['error']}")

st.subheader("Review")
filter_col1, filter_col2, filter_col3 = st.columns([1, 1, 1])
difficulty_filter = filter_col1.selectbox("Filter by difficulty", options=["All"] + DIFFICULTY_LEVELS)
type_filter = filter_col2.selectbox("Filter by type", options=["All"] + QUESTION_TYPES)
if filter_col3.button("Refresh"):
    st.rerun()

try:
    items_response = fetch_question_bank_items(
        selected_chapter_id,
        None if difficulty_filter == "All" else difficulty_filter,
        None if type_filter == "All" else type_filter,
    )
    items_response.raise_for_status()
    items = items_response.json()
except requests.RequestException:
    st.error("Backend unreachable")
    st.stop()

if not items:
    st.info(f"No questions imported yet for {chapter_names[selected_chapter_id]}")
else:
    for item in items:
        item_id = item["id"]
        confirm_key = f"confirm_delete_question_bank_item_{item_id}"

        col1, col2, col3, col4, col5 = st.columns([4, 1, 1.5, 1, 1])
        stem = item["stem"]
        col1.write(stem if len(stem) <= 100 else f"{stem[:100]}…")
        col2.write(item["question_type"])
        col3.write(item.get("concept") or "—")
        col4.write(item["difficulty"])
        if col5.button("Delete", key=f"delete_question_bank_item_{item_id}"):
            st.session_state[confirm_key] = True
            st.rerun()

        st.caption(f"Source: {item['source']} · Class: {item['class_grade']}")

        if st.session_state.get(confirm_key):
            st.warning("Delete this question? This cannot be undone.")
            confirm_col, cancel_col = st.columns(2)
            if confirm_col.button("Confirm Delete", key=f"confirm_yes_question_bank_item_{item_id}"):
                response = delete_question_bank_item(item_id)
                st.session_state[confirm_key] = False
                if response.status_code == 204:
                    st.rerun()
                else:
                    st.error(error_detail(response, "Failed to delete question"))
            if cancel_col.button("Cancel Delete", key=f"cancel_delete_question_bank_item_{item_id}"):
                st.session_state[confirm_key] = False
                st.rerun()

        st.divider()
