import streamlit as st
import requests
from requests.exceptions import ConnectionError, Timeout

API_BASE = "http://127.0.0.1:8000"
ASK_API = f"{API_BASE}/ask"
COMPARE_API = f"{API_BASE}/compare"

# -------------------------------
# PAGE CONFIG
# -------------------------------
st.set_page_config(
    page_title="Spotline Knowledge Assistant",
    page_icon="📘",
    layout="wide",
)

st.title("Spotline Internal Assistant")

# -------------------------------
# TABS
# -------------------------------
tab_chat, tab_validation = st.tabs(
    ["💬 Knowledge Assistant", "📄 Document Validation"]
)

# =====================================================================
# TAB 1: CHATBOT (RAG PIPELINE)
# =====================================================================
with tab_chat:
    st.caption(
        "Ask questions based on internal SOPs, PR review checklists, "
        "validation rules, UI locators, and company profile."
    )

    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Render chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])

            if message["role"] == "assistant":
                sources = message.get("sources", [])
                if sources:
                    with st.expander("Sources"):
                        for s in sources:
                            st.markdown(f"- **{s}**")

    prompt = st.chat_input("Ask a question…")

    if prompt:
        user_query = prompt.strip()
        if user_query:
            st.session_state.messages.append(
                {"role": "user", "content": user_query}
            )

            with st.spinner("Searching internal knowledge…"):
                try:
                    res = requests.post(
                        ASK_API,
                        json={"query": user_query},
                        timeout=30,
                    )
                    data = res.json()
                except (ConnectionError, Timeout):
                    data = {
                        "answer": "Backend is not reachable.",
                        "sources": [],
                    }

            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": data.get("answer", "No answer returned."),
                    "sources": data.get("sources", []),
                }
            )

            st.rerun()

# =====================================================================
# TAB 2: DOCUMENT VALIDATION (PDF ↔ PDF)
# =====================================================================
with tab_validation:
    st.caption(
        "Upload a client PDF and the V-Assure output PDF to validate "
        "structural and textual differences."
    )

    col1, col2 = st.columns(2)

    with col1:
        input_pdf = st.file_uploader(
            "Client Input PDF",
            type=["pdf"],
            help="Upload the original client document (PDF)",
        )

    with col2:
        output_pdf = st.file_uploader(
            "V-Assure Output PDF",
            type=["pdf"],
            help="Upload the V-Assure generated output (PDF)",
        )

    if st.button("Run Validation", type="primary"):
        if not input_pdf or not output_pdf:
            st.warning("Please upload both PDF files.")
        else:
            with st.spinner("Comparing documents…"):
                try:
                    res = requests.post(
                        COMPARE_API,
                        files={
                            "input_pdf": input_pdf,
                            "output_pdf": output_pdf,
                        },
                        timeout=60,
                    )
                except (ConnectionError, Timeout):
                    st.error("Backend is not reachable.")
                    res = None

            if res and res.status_code == 200:
                payload = res.json()
                diffs = payload.get("differences", [])

                if not diffs:
                    st.success("No differences found.")
                else:
                    st.subheader("Detected Differences")
                    for idx, d in enumerate(diffs, start=1):
                        with st.expander(f"Difference {idx}"):
                            st.json(d)
            else:
                st.error("Document comparison failed.")
