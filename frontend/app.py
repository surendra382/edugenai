import os

import requests
import streamlit as st

BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8000")

st.set_page_config(page_title="EduGenAI", layout="wide")
st.title("EduGenAI")

try:
    response = requests.get(f"{BACKEND_URL}/health", timeout=2)
    if response.status_code == 200 and response.json().get("status") == "ok":
        st.success("Backend connected")
    else:
        st.error("Backend unreachable")
except requests.RequestException:
    st.error("Backend unreachable")

st.subheader("Admin")
st.page_link("pages/admin_subjects.py", label="Subjects")
st.page_link("pages/admin_chapters.py", label="Chapters")
st.page_link("pages/admin_question_bank.py", label="Question Bank")
st.page_link("pages/admin_question_generator.py", label="Generate Practice Paper")

st.subheader("Student")
st.page_link("pages/student_generate.py", label="Generate My Practice Paper")
st.page_link("pages/student_history.py", label="Practice Paper History")
