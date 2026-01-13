import streamlit as st
import requests
from requests.exceptions import ConnectionError, Timeout

API_BASE = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="Spotline Knowledge Assistant",
    page_icon="📘",
    layout="wide",
)

# -------------------------------
# MODE SELECTOR
# -------------------------------
mode = st.sidebar.radio(
    "Select Mode",
    ["🧠 Knowledge Assistant", "📄 PDF Validation"],
)

st.title("Spotline Internal Platform")

# =====================================================
# MODE 1: KNOWLEDGE ASSISTANT (RAG)
# =====================================================
if mode == "🧠 Knowledge Assistant":

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if msg["role"] == "assistant" and msg.get("sources"):
                with st.expander("Sources"):
                    for s in msg["sources"]:
                        st.markdown(f"- **{s}**")

    prompt = st.chat_input("Ask a question...")
    if prompt:
        st.session_state.messages.append(
            {"role": "user", "content": prompt}
        )

        with st.spinner("Searching internal knowledge..."):
            try:
                res = requests.post(
                    f"{API_BASE}/ask",
                    json={"query": prompt},
                    timeout=30,
                )
                data = res.json()
            except Exception as e:
                data = {
                    "answer": f"Error: {e}",
                    "sources": [],
                }

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": data.get("answer", ""),
                "sources": data.get("sources", []),
            }
        )
        st.rerun()

# =====================================================
# MODE 2: PDF ↔ PDF VALIDATION
# =====================================================
else:
    st.subheader("PDF Validation (Client vs V-Assure Output)")

    client_pdf = st.file_uploader(
        "Upload Client Test Script (PDF)",
        type=["pdf"],
    )
    output_pdf = st.file_uploader(
        "Upload V-Assure Output (PDF)",
        type=["pdf"],
    )

    if st.button("Compare PDFs"):
        if not client_pdf or not output_pdf:
            st.warning("Please upload both PDFs.")
        else:
            with st.spinner("Comparing documents..."):
                try:
                    res = requests.post(
                        f"{API_BASE}/compare",
                        files={
                            "client_pdf": client_pdf,
                            "output_pdf": output_pdf,
                        },
                        timeout=120,
                    )

                    if res.status_code != 200:
                        st.error("Comparison failed.")
                    else:
                        diffs = res.json().get("differences", [])

                        if not diffs:
                            st.success("No differences found. Validation passed.")
                        else:
                            st.error("Differences detected:")
                            for d in diffs:
                                st.code(d)

                except Timeout:
                    st.error("Comparison timed out.")
                except ConnectionError:
                    st.error("Backend not running.")