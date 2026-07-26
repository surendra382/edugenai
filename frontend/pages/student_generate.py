import os

import requests
import streamlit as st

BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")

DIFFICULTY_LEVELS = ["easy", "medium", "hard"]
QUESTION_TYPE_LABELS = {
    "mcq": "Multiple Choice",
    "fill_blank": "Fill in the Blanks",
    "true_false": "True/False",
    "short_answer": "Short Answer",
    "long_answer": "Long Answer",
    "numerical": "Numerical Problem",
}
MAX_TOTAL_QUESTIONS = 60


def fetch_subjects() -> list[dict]:
    response = requests.get(f"{BACKEND_URL}/subjects", timeout=5)
    response.raise_for_status()
    return response.json()


def fetch_chapters(subject_id: int) -> list[dict]:
    response = requests.get(f"{BACKEND_URL}/subjects/{subject_id}/chapters", timeout=5)
    response.raise_for_status()
    return response.json()


def fetch_question_bank_sources(chapter_id: int) -> list[str]:
    response = requests.get(f"{BACKEND_URL}/chapters/{chapter_id}/question-bank/sources", timeout=5)
    response.raise_for_status()
    return response.json()


def create_question_set(subject_id: int, payload: dict) -> requests.Response:
    return requests.post(
        f"{BACKEND_URL}/subjects/{subject_id}/question-sets", json=payload, timeout=10
    )


def fetch_question_sets_for_subject(subject_id: int) -> requests.Response:
    return requests.get(
        f"{BACKEND_URL}/question-sets", params={"subject_id": subject_id}, timeout=5
    )


def fetch_question_set(question_set_id: int) -> requests.Response:
    return requests.get(f"{BACKEND_URL}/question-sets/{question_set_id}", timeout=5)


def fetch_questions(question_set_id: int) -> requests.Response:
    return requests.get(f"{BACKEND_URL}/question-sets/{question_set_id}/questions", timeout=5)


def retry_question_set(question_set_id: int) -> requests.Response:
    return requests.post(f"{BACKEND_URL}/question-sets/{question_set_id}/retry", timeout=10)


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


st.set_page_config(page_title="Generate Practice Paper - EduGenAI", layout="wide")
st.title("Generate My Practice Paper")

try:
    subjects = fetch_subjects()
except requests.RequestException:
    st.error("Backend unreachable")
    st.stop()

if not subjects:
    st.info("No subjects available yet — check back once your teacher has added some")
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
    st.info("No chapters available yet for this subject")
    st.stop()

chapter_names = {chapter["id"]: chapter["name"] for chapter in chapters}
selected_chapter_ids = st.multiselect(
    "Chapters",
    options=list(chapter_names.keys()),
    format_func=lambda cid: chapter_names[cid],
)

if st.session_state.get("student_generate_subject_id") != selected_subject_id:
    st.session_state["student_generate_subject_id"] = selected_subject_id
    st.session_state["active_question_set_id"] = None

st.subheader("Generate")
if not selected_chapter_ids:
    st.info("Select one or more chapters to generate a practice paper")
else:
    with st.form("student_generate_question_set_form"):
        chapter_counts: dict[int, int] = {}
        for chapter_id in selected_chapter_ids:
            chapter_counts[chapter_id] = int(
                st.number_input(
                    f"Questions from {chapter_names[chapter_id]}",
                    min_value=1,
                    max_value=30,
                    value=5,
                    key=f"chapter_count_{chapter_id}",
                )
            )
        total_questions = sum(chapter_counts.values())
        st.caption(f"Total questions: {total_questions}")
        if total_questions > MAX_TOTAL_QUESTIONS:
            st.warning(f"Total questions across chapters cannot exceed {MAX_TOTAL_QUESTIONS}")

        difficulty = st.selectbox("Difficulty", options=DIFFICULTY_LEVELS)

        available_sources: set[str] = set()
        for chapter_id in selected_chapter_ids:
            try:
                available_sources.update(fetch_question_bank_sources(chapter_id))
            except requests.RequestException:
                pass
        purpose = st.selectbox("Purpose", options=["Any"] + sorted(available_sources))

        question_types = st.multiselect(
            "Question Types",
            options=list(QUESTION_TYPE_LABELS.keys()),
            format_func=lambda qt: QUESTION_TYPE_LABELS[qt],
        )
        include_answer_key = st.checkbox("Include answer key")
        submitted = st.form_submit_button("Generate")

        if submitted:
            if not question_types:
                st.error("Select at least one question type")
            elif total_questions > MAX_TOTAL_QUESTIONS:
                st.error(f"Total questions across chapters cannot exceed {MAX_TOTAL_QUESTIONS}")
            else:
                response = create_question_set(
                    selected_subject_id,
                    {
                        "chapters": [
                            {"chapter_id": chapter_id, "num_questions": count}
                            for chapter_id, count in chapter_counts.items()
                        ],
                        "difficulty": difficulty,
                        "source": None if purpose == "Any" else purpose,
                        "question_types": question_types,
                        "include_answer_key": include_answer_key,
                    },
                )
                if response.status_code == 202:
                    st.session_state["active_question_set_id"] = response.json()["id"]
                    st.rerun()
                else:
                    st.error(error_detail(response, "Failed to start generation"))

st.subheader("My Past Papers")
history_response = fetch_question_sets_for_subject(selected_subject_id)
if history_response.status_code != 200:
    st.error(error_detail(history_response, "Failed to load history"))
else:
    history = history_response.json()
    if not history:
        st.info("No practice papers generated yet for this subject")
    else:
        for question_set in history:
            chapters_label = question_set["chapter_name"] or f"{len(question_set['chapters'])} chapters"
            purpose_label = question_set.get("source") or "Any"
            col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 1])
            col1.write(chapters_label)
            col2.write(f"{question_set['difficulty']} · {purpose_label}")
            col3.write(", ".join(question_set["question_types"]))
            col4.write(f"Status: {question_set['status']}")
            if col5.button("View", key=f"view_question_set_{question_set['id']}"):
                st.session_state["active_question_set_id"] = question_set["id"]
                st.rerun()

active_question_set_id = st.session_state.get("active_question_set_id")
if active_question_set_id:
    st.subheader("Result")
    question_set_response = fetch_question_set(active_question_set_id)
    if question_set_response.status_code != 200:
        st.error(error_detail(question_set_response, "Failed to load question set"))
    else:
        question_set = question_set_response.json()
        status = question_set["status"]

        if status == "generating":
            st.info("Generating… this can take a little while.")
            if st.button("Refresh"):
                st.rerun()
        elif status == "failed":
            st.error(question_set.get("generation_error") or "Generation failed")
            if st.button("Retry"):
                retry_response = retry_question_set(active_question_set_id)
                if retry_response.status_code == 202:
                    st.rerun()
                else:
                    st.error(error_detail(retry_response, "Failed to retry generation"))
        elif status == "completed":
            questions_response = fetch_questions(active_question_set_id)
            if questions_response.status_code != 200:
                st.error(error_detail(questions_response, "Failed to load questions"))
            else:
                purpose_label = question_set.get("source") or "Any"
                st.caption(f"Difficulty: {question_set['difficulty']} · Purpose: {purpose_label}")
                questions = questions_response.json()
                chapters_breakdown = question_set["chapters"]
                is_multi_chapter = len(chapters_breakdown) > 1

                questions_by_chapter: dict[int, list[dict]] = {}
                for question in questions:
                    questions_by_chapter.setdefault(question["chapter_id"], []).append(question)

                for chapter_info in chapters_breakdown:
                    chapter_questions = questions_by_chapter.get(chapter_info["chapter_id"], [])
                    if is_multi_chapter:
                        st.markdown(
                            f"#### {chapter_info['chapter_name']} "
                            f"({len(chapter_questions)} questions)"
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

                if question_set["include_answer_key"]:
                    with st.expander("Answer Key"):
                        for chapter_info in chapters_breakdown:
                            chapter_questions = questions_by_chapter.get(
                                chapter_info["chapter_id"], []
                            )
                            if is_multi_chapter:
                                st.markdown(f"**{chapter_info['chapter_name']}**")
                            for question in chapter_questions:
                                st.write(f"Q{question['question_index'] + 1}: {question['answer']}")

                include_answers_in_pdf = True
                if question_set["include_answer_key"]:
                    include_answers_in_pdf = st.checkbox(
                        "Include answers in PDF", value=True, key="student_pdf_include_answers"
                    )
                pdf_response = fetch_question_set_pdf(active_question_set_id, include_answers_in_pdf)
                if pdf_response.status_code == 200:
                    st.download_button(
                        "Download PDF",
                        data=pdf_response.content,
                        file_name=f"question_set_{active_question_set_id}.pdf",
                        mime="application/pdf",
                    )
                else:
                    st.error(error_detail(pdf_response, "Failed to generate PDF"))
