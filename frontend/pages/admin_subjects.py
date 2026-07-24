import os

import requests
import streamlit as st

BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")


def fetch_subjects() -> list[dict]:
    response = requests.get(f"{BACKEND_URL}/subjects", timeout=5)
    response.raise_for_status()
    return response.json()


def create_subject(name: str) -> requests.Response:
    return requests.post(f"{BACKEND_URL}/subjects", json={"name": name}, timeout=5)


def update_subject(subject_id: int, name: str) -> requests.Response:
    return requests.put(f"{BACKEND_URL}/subjects/{subject_id}", json={"name": name}, timeout=5)


def delete_subject(subject_id: int) -> requests.Response:
    return requests.delete(f"{BACKEND_URL}/subjects/{subject_id}", timeout=5)


def error_detail(response: requests.Response, fallback: str) -> str:
    try:
        return response.json().get("detail", fallback)
    except ValueError:
        return fallback


st.set_page_config(page_title="Subjects - EduGenAI", layout="wide")
st.title("Subjects")

try:
    subjects = fetch_subjects()
except requests.RequestException:
    st.error("Backend unreachable")
    st.stop()

st.subheader("Add Subject")
with st.form("add_subject_form", clear_on_submit=True):
    new_name = st.text_input("Subject name")
    submitted = st.form_submit_button("Add Subject")
    if submitted:
        if not new_name.strip():
            st.error("Name is required")
        else:
            response = create_subject(new_name)
            if response.status_code == 201:
                st.success(f"Added '{new_name}'")
                st.rerun()
            else:
                st.error(error_detail(response, "Failed to add subject"))

st.subheader("Subjects")

if not subjects:
    st.info("No subjects yet — add your first one above")
else:
    for subject in subjects:
        subject_id = subject["id"]
        edit_key = f"editing_{subject_id}"
        confirm_key = f"confirm_delete_{subject_id}"

        col1, col2, col3 = st.columns([4, 1, 1])

        if st.session_state.get(edit_key):
            new_value = col1.text_input(
                "Name",
                value=subject["name"],
                key=f"edit_input_{subject_id}",
                label_visibility="collapsed",
            )
            if col2.button("Save", key=f"save_{subject_id}"):
                response = update_subject(subject_id, new_value or "")
                if response.status_code == 200:
                    st.session_state[edit_key] = False
                    st.rerun()
                else:
                    st.error(error_detail(response, "Failed to update subject"))
            if col3.button("Cancel", key=f"cancel_{subject_id}"):
                st.session_state[edit_key] = False
                st.rerun()
        else:
            col1.write(subject["name"])
            if col2.button("Edit", key=f"edit_{subject_id}"):
                st.session_state[edit_key] = True
                st.rerun()
            if col3.button("Delete", key=f"delete_{subject_id}"):
                st.session_state[confirm_key] = True
                st.rerun()

        if st.session_state.get(confirm_key):
            st.warning(f"Delete '{subject['name']}'? This cannot be undone.")
            confirm_col, cancel_col = st.columns(2)
            if confirm_col.button("Confirm Delete", key=f"confirm_yes_{subject_id}"):
                response = delete_subject(subject_id)
                st.session_state[confirm_key] = False
                if response.status_code == 204:
                    st.rerun()
                else:
                    st.error(error_detail(response, "Failed to delete subject"))
            if cancel_col.button("Cancel Delete", key=f"cancel_delete_{subject_id}"):
                st.session_state[confirm_key] = False
                st.rerun()
