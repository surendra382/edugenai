import os

import requests
import streamlit as st

BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")


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


def search_chapter(chapter_id: int, query: str, limit: int = 10) -> requests.Response:
    return requests.get(
        f"{BACKEND_URL}/chapters/{chapter_id}/search",
        params={"q": query, "limit": limit},
        timeout=10,
    )


def error_detail(response: requests.Response, fallback: str) -> str:
    try:
        return response.json().get("detail", fallback)
    except ValueError:
        return fallback


st.set_page_config(page_title="Preview Documents - EduGenAI", layout="wide")
st.title("Preview Documents")

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
document_filenames = {document["id"]: document["original_filename"] for document in documents}

st.subheader("Search")
with st.form("search_form"):
    query = st.text_input("Query")
    submitted = st.form_submit_button("Search")

if submitted:
    if not query.strip():
        st.error("Enter a query first")
    else:
        response = search_chapter(selected_chapter_id, query)
        if response.status_code != 200:
            st.error(error_detail(response, "Search failed"))
        else:
            results = response.json()
            if not results:
                st.info(
                    "No results — try a different query, or confirm this chapter has "
                    "embedded material"
                )
            else:
                for result in results:
                    filename = document_filenames.get(
                        result["document_id"], f"document #{result['document_id']}"
                    )
                    st.markdown(f"**{filename}** · {result['material_type']} · score {result['score']:.4f}")
                    st.text(result["text"])
                    st.divider()
