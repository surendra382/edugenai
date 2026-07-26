import os

import requests
import streamlit as st

BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")

STATUS_OPTIONS = ["All", "generating", "completed", "failed"]
ALL_LABEL = "All"

QUESTION_TYPE_LABELS = {
    "mcq": "Multiple Choice",
    "fill_blank": "Fill in the Blanks",
    "true_false": "True/False",
    "short_answer": "Short Answer",
    "long_answer": "Long Answer",
    "numerical": "Numerical Problem",
}


def fetch_subjects() -> list[dict]:
    response = requests.get(f"{BACKEND_URL}/subjects", timeout=5)
    response.raise_for_status()
    return response.json()


def fetch_chapters(subject_id: int) -> list[dict]:
    response = requests.get(f"{BACKEND_URL}/subjects/{subject_id}/chapters", timeout=5)
    response.raise_for_status()
    return response.json()


def fetch_history(subject_id: int | None, chapter_id: int | None, status_filter: str | None) -> requests.Response:
    params = {}
    if subject_id is not None:
        params["subject_id"] = subject_id
    if chapter_id is not None:
        params["chapter_id"] = chapter_id
    if status_filter is not None:
        params["status"] = status_filter
    return requests.get(f"{BACKEND_URL}/question-sets", params=params, timeout=5)


def fetch_questions(question_set_id: int) -> requests.Response:
    return requests.get(f"{BACKEND_URL}/question-sets/{question_set_id}/questions", timeout=5)


def fetch_question_set_pdf(question_set_id: int, include_answers: bool) -> requests.Response:
    return requests.get(
        f"{BACKEND_URL}/question-sets/{question_set_id}/pdf",
        params={"include_answers": include_answers},
        timeout=15,
    )


def error_detail(response: requests.Response, fallback: str) -> str:
    try:
        return response.json().get("detail", fallback)
    except ValueError:
        return fallback


st.set_page_config(page_title="Practice Paper History - EduGenAI", layout="wide")
st.title("Practice Paper History")

try:
    subjects = fetch_subjects()
except requests.RequestException:
    st.error("Backend unreachable")
    st.stop()

subject_options = {ALL_LABEL: None} | {subject["name"]: subject["id"] for subject in subjects}
selected_subject_label = st.selectbox("Subject", options=list(subject_options.keys()))
selected_subject_id = subject_options[selected_subject_label]

chapter_options = {ALL_LABEL: None}
if selected_subject_id is not None:
    try:
        chapters = fetch_chapters(selected_subject_id)
    except requests.RequestException:
        st.error("Backend unreachable")
        st.stop()
    chapter_options |= {chapter["name"]: chapter["id"] for chapter in chapters}
selected_chapter_label = st.selectbox("Chapter", options=list(chapter_options.keys()))
selected_chapter_id = chapter_options[selected_chapter_label]

selected_status_label = st.selectbox("Status", options=STATUS_OPTIONS)
selected_status = None if selected_status_label == "All" else selected_status_label

history_response = fetch_history(selected_subject_id, selected_chapter_id, selected_status)
if history_response.status_code != 200:
    st.error(error_detail(history_response, "Failed to load history"))
    st.stop()

history = history_response.json()
st.subheader("Papers")
if not history:
    st.info("No practice papers generated yet")
else:
    for question_set in history:
        chapters_label = question_set["chapter_name"] or f"{len(question_set['chapters'])} chapters"
        purpose_label = question_set.get("source") or "Any"
        col1, col2, col3, col4, col5, col6 = st.columns([2, 2, 1, 2, 2, 1])
        col1.write(question_set["subject_name"])
        col2.write(chapters_label)
        col3.write(f"{question_set['difficulty']} · {purpose_label}")
        col4.write(", ".join(question_set["question_types"]))
        col5.write(f"Status: {question_set['status']}")
        if col6.button("View", key=f"view_history_{question_set['id']}"):
            st.session_state["history_active_question_set"] = question_set

active_question_set = st.session_state.get("history_active_question_set")
if active_question_set:
    active_chapters_label = (
        active_question_set["chapter_name"] or f"{len(active_question_set['chapters'])} chapters"
    )
    st.subheader(f"Result — {active_question_set['subject_name']} / {active_chapters_label}")
    active_purpose_label = active_question_set.get("source") or "Any"
    st.caption(f"Difficulty: {active_question_set['difficulty']} · Purpose: {active_purpose_label}")
    if active_question_set["status"] == "generating":
        st.info("Still generating — check back shortly.")
    elif active_question_set["status"] == "failed":
        st.error(active_question_set.get("generation_error") or "Generation failed")
    elif active_question_set["status"] == "completed":
        questions_response = fetch_questions(active_question_set["id"])
        if questions_response.status_code != 200:
            st.error(error_detail(questions_response, "Failed to load questions"))
        else:
            questions = questions_response.json()
            chapters_breakdown = active_question_set["chapters"]
            is_multi_chapter = len(chapters_breakdown) > 1

            questions_by_chapter: dict[int, list[dict]] = {}
            for question in questions:
                questions_by_chapter.setdefault(question["chapter_id"], []).append(question)

            for chapter_info in chapters_breakdown:
                chapter_questions = questions_by_chapter.get(chapter_info["chapter_id"], [])
                if is_multi_chapter:
                    st.markdown(
                        f"#### {chapter_info['chapter_name']} ({len(chapter_questions)} questions)"
                    )
                for question in chapter_questions:
                    st.markdown(
                        f"**Q{question['question_index'] + 1}.** "
                        f"({QUESTION_TYPE_LABELS.get(question['question_type'], question['question_type'])}) "
                        f"{question['text']}"
                    )
                    if question["options"]:
                        for option in question["options"]:
                            st.write(f"- {option}")

            if active_question_set["include_answer_key"]:
                with st.expander("Answer Key"):
                    for chapter_info in chapters_breakdown:
                        chapter_questions = questions_by_chapter.get(chapter_info["chapter_id"], [])
                        if is_multi_chapter:
                            st.markdown(f"**{chapter_info['chapter_name']}**")
                        for question in chapter_questions:
                            st.write(f"Q{question['question_index'] + 1}: {question['answer']}")

            include_answers_in_pdf = True
            if active_question_set["include_answer_key"]:
                include_answers_in_pdf = st.checkbox(
                    "Include answers in PDF", value=True, key="history_pdf_include_answers"
                )
            pdf_response = fetch_question_set_pdf(active_question_set["id"], include_answers_in_pdf)
            if pdf_response.status_code == 200:
                st.download_button(
                    "Download PDF",
                    data=pdf_response.content,
                    file_name=f"question_set_{active_question_set['id']}.pdf",
                    mime="application/pdf",
                )
            else:
                st.error(error_detail(pdf_response, "Failed to generate PDF"))
