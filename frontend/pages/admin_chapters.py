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


def create_chapter(subject_id: int, name: str) -> requests.Response:
    return requests.post(
        f"{BACKEND_URL}/subjects/{subject_id}/chapters", json={"name": name}, timeout=5
    )


def update_chapter(chapter_id: int, name: str) -> requests.Response:
    return requests.put(f"{BACKEND_URL}/chapters/{chapter_id}", json={"name": name}, timeout=5)


def delete_chapter(chapter_id: int) -> requests.Response:
    return requests.delete(f"{BACKEND_URL}/chapters/{chapter_id}", timeout=5)


def reorder_chapters(subject_id: int, ordered_ids: list[int]) -> requests.Response:
    return requests.patch(
        f"{BACKEND_URL}/subjects/{subject_id}/chapters/reorder",
        json={"ordered_ids": ordered_ids},
        timeout=5,
    )


def error_detail(response: requests.Response, fallback: str) -> str:
    try:
        return response.json().get("detail", fallback)
    except ValueError:
        return fallback


st.set_page_config(page_title="Chapters - EduGenAI", layout="wide")
st.title("Chapters")

try:
    subjects = fetch_subjects()
except requests.RequestException:
    st.error("Backend unreachable")
    st.stop()

if not subjects:
    st.info("No subjects yet — add one on the Subjects page first")
    st.stop()

subject_names = {subject["id"]: subject["name"] for subject in subjects}
selected_id = st.selectbox(
    "Subject",
    options=list(subject_names.keys()),
    format_func=lambda sid: subject_names[sid],
)

try:
    chapters = fetch_chapters(selected_id)
except requests.RequestException:
    st.error("Backend unreachable")
    st.stop()

st.subheader("Add Chapter")
with st.form("add_chapter_form", clear_on_submit=True):
    new_name = st.text_input("Chapter name")
    submitted = st.form_submit_button("Add Chapter")
    if submitted:
        if not new_name.strip():
            st.error("Name is required")
        else:
            response = create_chapter(selected_id, new_name)
            if response.status_code == 201:
                st.success(f"Added '{new_name}'")
                st.rerun()
            else:
                st.error(error_detail(response, "Failed to add chapter"))

st.subheader("Chapters")

if not chapters:
    st.info(f"No chapters yet for {subject_names[selected_id]} — add the first one above")
else:
    ordered_ids = [chapter["id"] for chapter in chapters]

    for position, chapter in enumerate(chapters):
        chapter_id = chapter["id"]
        edit_key = f"editing_chapter_{chapter_id}"
        confirm_key = f"confirm_delete_chapter_{chapter_id}"

        col1, col2, col3, col4, col5 = st.columns([4, 1, 1, 1, 1])

        if st.session_state.get(edit_key):
            new_value = col1.text_input(
                "Name",
                value=chapter["name"],
                key=f"edit_input_chapter_{chapter_id}",
                label_visibility="collapsed",
            )
            if col2.button("Save", key=f"save_chapter_{chapter_id}"):
                response = update_chapter(chapter_id, new_value or "")
                if response.status_code == 200:
                    st.session_state[edit_key] = False
                    st.rerun()
                else:
                    st.error(error_detail(response, "Failed to update chapter"))
            if col3.button("Cancel", key=f"cancel_chapter_{chapter_id}"):
                st.session_state[edit_key] = False
                st.rerun()
        else:
            col1.write(chapter["name"])
            if col2.button("Edit", key=f"edit_chapter_{chapter_id}"):
                st.session_state[edit_key] = True
                st.rerun()
            if col3.button("Delete", key=f"delete_chapter_{chapter_id}"):
                st.session_state[confirm_key] = True
                st.rerun()
            if col4.button("Up", key=f"up_chapter_{chapter_id}", disabled=position == 0):
                new_order = ordered_ids.copy()
                new_order[position - 1], new_order[position] = new_order[position], new_order[position - 1]
                response = reorder_chapters(selected_id, new_order)
                if response.status_code == 200:
                    st.rerun()
                else:
                    st.error(error_detail(response, "Failed to reorder chapters"))
            if col5.button("Down", key=f"down_chapter_{chapter_id}", disabled=position == len(chapters) - 1):
                new_order = ordered_ids.copy()
                new_order[position + 1], new_order[position] = new_order[position], new_order[position + 1]
                response = reorder_chapters(selected_id, new_order)
                if response.status_code == 200:
                    st.rerun()
                else:
                    st.error(error_detail(response, "Failed to reorder chapters"))

        if st.session_state.get(confirm_key):
            st.warning(f"Delete '{chapter['name']}'? This cannot be undone.")
            confirm_col, cancel_col = st.columns(2)
            if confirm_col.button("Confirm Delete", key=f"confirm_yes_chapter_{chapter_id}"):
                response = delete_chapter(chapter_id)
                st.session_state[confirm_key] = False
                if response.status_code == 204:
                    st.rerun()
                else:
                    st.error(error_detail(response, "Failed to delete chapter"))
            if cancel_col.button("Cancel Delete", key=f"cancel_delete_chapter_{chapter_id}"):
                st.session_state[confirm_key] = False
                st.rerun()
