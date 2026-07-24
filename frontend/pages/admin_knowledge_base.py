import os

import requests
import streamlit as st

BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")

MATERIAL_TYPES = ["textbook_page", "worksheet", "sample_paper", "notes", "question_paper"]
QUESTION_TYPES = [
    "Multiple Choice Questions",
    "Fill in the Blanks",
    "True/False",
    "Short Answer",
    "Long Answer",
    "Numerical Problems",
]
DIFFICULTY_LEVELS = ["easy", "medium", "hard"]
OCR_SUCCEEDED_STATUSES = {"ocr_done", "embedding_processing", "embedded", "embedding_failed"}


def fetch_subjects() -> list[dict]:
    response = requests.get(f"{BACKEND_URL}/subjects", timeout=5)
    response.raise_for_status()
    return response.json()


def fetch_chapters(subject_id: int) -> list[dict]:
    response = requests.get(f"{BACKEND_URL}/subjects/{subject_id}/chapters", timeout=5)
    response.raise_for_status()
    return response.json()


def fetch_documents(chapter_id: int) -> list[dict]:
    response = requests.get(f"{BACKEND_URL}/chapters/{chapter_id}/documents", timeout=5)
    response.raise_for_status()
    return response.json()


def upload_document(chapter_id: int, material_type: str, filename: str, content: bytes) -> requests.Response:
    return requests.post(
        f"{BACKEND_URL}/chapters/{chapter_id}/documents",
        data={"material_type": material_type},
        files={"file": (filename, content)},
        timeout=30,
    )


def delete_document(document_id: int) -> requests.Response:
    return requests.delete(f"{BACKEND_URL}/documents/{document_id}", timeout=5)


def fetch_document_text(document_id: int) -> requests.Response:
    return requests.get(f"{BACKEND_URL}/documents/{document_id}/text", timeout=5)


def retry_ocr(document_id: int) -> requests.Response:
    return requests.post(f"{BACKEND_URL}/documents/{document_id}/ocr/retry", timeout=30)


def fetch_document_chunks(document_id: int) -> requests.Response:
    return requests.get(f"{BACKEND_URL}/documents/{document_id}/chunks", timeout=5)


def retry_embedding(document_id: int) -> requests.Response:
    return requests.post(f"{BACKEND_URL}/documents/{document_id}/embeddings/retry", timeout=30)


def fetch_document_metadata(document_id: int) -> requests.Response:
    return requests.get(f"{BACKEND_URL}/documents/{document_id}/metadata", timeout=5)


def update_document_metadata(document_id: int, payload: dict) -> requests.Response:
    return requests.put(f"{BACKEND_URL}/documents/{document_id}/metadata", json=payload, timeout=5)


def error_detail(response: requests.Response, fallback: str) -> str:
    try:
        return response.json().get("detail", fallback)
    except ValueError:
        return fallback


def format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


st.set_page_config(page_title="Knowledge Base - EduGenAI", layout="wide")
st.title("Knowledge Base")

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

try:
    documents = fetch_documents(selected_chapter_id)
except requests.RequestException:
    st.error("Backend unreachable")
    st.stop()

st.subheader("Upload Material")
with st.form("upload_document_form", clear_on_submit=True):
    uploaded_file = st.file_uploader("File", type=["jpg", "jpeg", "png", "pdf"])
    material_type = st.selectbox("Material type", options=MATERIAL_TYPES)
    submitted = st.form_submit_button("Upload")
    if submitted:
        if uploaded_file is None:
            st.error("Choose a file first")
        else:
            response = upload_document(
                selected_chapter_id, material_type, uploaded_file.name, uploaded_file.getvalue()
            )
            if response.status_code == 201:
                st.success(f"Uploaded '{uploaded_file.name}'")
                st.rerun()
            else:
                st.error(error_detail(response, "Failed to upload file"))

st.subheader("Documents")
if st.button("Refresh"):
    st.rerun()

if not documents:
    st.info(f"No material uploaded yet for {chapter_names[selected_chapter_id]} — upload your first file above")
else:
    for document in documents:
        document_id = document["id"]
        confirm_key = f"confirm_delete_document_{document_id}"

        col1, col2, col3, col4, col5 = st.columns([3, 1.5, 1, 1, 1])
        col1.write(document["original_filename"])
        col2.write(document["material_type"])
        col3.write(document["file_type"])
        col4.write(format_size(document["file_size_bytes"]))
        if col5.button("Delete", key=f"delete_document_{document_id}"):
            st.session_state[confirm_key] = True
            st.rerun()

        st.caption(f"Status: {document['status']}")

        if document["status"] in OCR_SUCCEEDED_STATUSES:
            with st.expander("View Text"):
                text_response = fetch_document_text(document_id)
                if text_response.status_code == 200:
                    st.text(text_response.json()["text"])
                else:
                    st.error(error_detail(text_response, "Failed to load extracted text"))
        elif document["status"] == "ocr_failed":
            st.error(document.get("ocr_error") or "OCR failed")
            if st.button("Retry OCR", key=f"retry_ocr_{document_id}"):
                response = retry_ocr(document_id)
                if response.status_code == 202:
                    st.rerun()
                else:
                    st.error(error_detail(response, "Failed to retry OCR"))

        if document["status"] == "embedded":
            with st.expander("View Chunks"):
                chunks_response = fetch_document_chunks(document_id)
                if chunks_response.status_code == 200:
                    chunks = chunks_response.json()
                    st.caption(f"{len(chunks)} chunk(s)")
                    for chunk in chunks:
                        st.text(f"[{chunk['chunk_index']}] {chunk['text'][:100]}")
                else:
                    st.error(error_detail(chunks_response, "Failed to load chunks"))
        elif document["status"] == "embedding_failed":
            st.error(document.get("embedding_error") or "Embedding failed")
            if st.button("Retry Embedding", key=f"retry_embedding_{document_id}"):
                response = retry_embedding(document_id)
                if response.status_code == 202:
                    st.rerun()
                else:
                    st.error(error_detail(response, "Failed to retry embedding"))

        with st.expander("Edit Metadata"):
            metadata_response = fetch_document_metadata(document_id)
            if metadata_response.status_code != 200:
                st.error(error_detail(metadata_response, "Failed to load metadata"))
            else:
                metadata = metadata_response.json()
                st.caption(f"Uploaded on {document['created_at']}")
                with st.form(f"metadata_form_{document_id}"):
                    board = st.text_input("Board", value=metadata.get("board") or "")
                    class_level = st.text_input("Class", value=metadata.get("class_level") or "")
                    source = st.text_input("Source", value=metadata.get("source") or "")
                    keywords = st.text_area("Keywords", value=metadata.get("keywords") or "")
                    learning_objectives = st.text_area(
                        "Learning Objectives", value=metadata.get("learning_objectives") or ""
                    )
                    existing_question_types = [
                        qt.strip()
                        for qt in (metadata.get("question_types") or "").split(",")
                        if qt.strip()
                    ]
                    question_types = st.multiselect(
                        "Question Types", options=QUESTION_TYPES, default=existing_question_types
                    )
                    difficulty_options = [""] + DIFFICULTY_LEVELS
                    difficulty_index = (
                        difficulty_options.index(metadata["difficulty"])
                        if metadata.get("difficulty") in DIFFICULTY_LEVELS
                        else 0
                    )
                    difficulty = st.selectbox(
                        "Difficulty", options=difficulty_options, index=difficulty_index
                    )
                    if st.form_submit_button("Save Metadata"):
                        save_response = update_document_metadata(
                            document_id,
                            {
                                "board": board,
                                "class_level": class_level,
                                "source": source,
                                "keywords": keywords,
                                "learning_objectives": learning_objectives,
                                "question_types": ", ".join(question_types),
                                "difficulty": difficulty or None,
                            },
                        )
                        if save_response.status_code == 200:
                            st.success("Metadata saved")
                            st.rerun()
                        else:
                            st.error(error_detail(save_response, "Failed to save metadata"))

        if st.session_state.get(confirm_key):
            st.warning(f"Delete '{document['original_filename']}'? This cannot be undone.")
            confirm_col, cancel_col = st.columns(2)
            if confirm_col.button("Confirm Delete", key=f"confirm_yes_document_{document_id}"):
                response = delete_document(document_id)
                st.session_state[confirm_key] = False
                if response.status_code == 204:
                    st.rerun()
                else:
                    st.error(error_detail(response, "Failed to delete document"))
            if cancel_col.button("Cancel Delete", key=f"cancel_delete_document_{document_id}"):
                st.session_state[confirm_key] = False
                st.rerun()

        st.divider()
