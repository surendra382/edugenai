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


def fetch_subjects() -> list[dict]:
    response = requests.get(f"{BACKEND_URL}/subjects", timeout=5)
    response.raise_for_status()
    return response.json()


def fetch_chapters(subject_id: int) -> list[dict]:
    response = requests.get(f"{BACKEND_URL}/subjects/{subject_id}/chapters", timeout=5)
    response.raise_for_status()
    return response.json()


def create_question_set(chapter_id: int, payload: dict) -> requests.Response:
    return requests.post(
        f"{BACKEND_URL}/chapters/{chapter_id}/question-sets", json=payload, timeout=10
    )


def fetch_question_sets(chapter_id: int) -> requests.Response:
    return requests.get(f"{BACKEND_URL}/chapters/{chapter_id}/question-sets", timeout=5)


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
st.title("Generate Practice Paper")

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

if st.session_state.get("question_generator_chapter_id") != selected_chapter_id:
    st.session_state["question_generator_chapter_id"] = selected_chapter_id
    st.session_state["active_question_set_id"] = None

st.subheader("Generate")
with st.form("generate_question_set_form"):
    difficulty = st.selectbox("Difficulty", options=DIFFICULTY_LEVELS)
    question_types = st.multiselect(
        "Question Types",
        options=list(QUESTION_TYPE_LABELS.keys()),
        format_func=lambda qt: QUESTION_TYPE_LABELS[qt],
    )
    num_questions = st.number_input("Number of Questions", min_value=1, max_value=30, value=5)
    include_answer_key = st.checkbox("Include answer key")
    submitted = st.form_submit_button("Generate")

    if submitted:
        if not question_types:
            st.error("Select at least one question type")
        else:
            response = create_question_set(
                selected_chapter_id,
                {
                    "difficulty": difficulty,
                    "question_types": question_types,
                    "num_questions": int(num_questions),
                    "include_answer_key": include_answer_key,
                },
            )
            if response.status_code == 202:
                st.session_state["active_question_set_id"] = response.json()["id"]
                st.rerun()
            else:
                st.error(error_detail(response, "Failed to start generation"))

st.subheader("History")
history_response = fetch_question_sets(selected_chapter_id)
if history_response.status_code != 200:
    st.error(error_detail(history_response, "Failed to load history"))
else:
    history = history_response.json()
    if not history:
        st.info("No practice papers generated yet for this chapter")
    else:
        for question_set in history:
            col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
            col1.write(question_set["difficulty"])
            col2.write(", ".join(question_set["question_types"]))
            col3.write(f"Status: {question_set['status']}")
            if col4.button("View", key=f"view_question_set_{question_set['id']}"):
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
                questions = questions_response.json()
                for question in questions:
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
                        for question in questions:
                            st.write(f"Q{question['question_index'] + 1}: {question['answer']}")

                include_answers_in_pdf = True
                if question_set["include_answer_key"]:
                    include_answers_in_pdf = st.checkbox(
                        "Include answers in PDF", value=True, key="admin_pdf_include_answers"
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
