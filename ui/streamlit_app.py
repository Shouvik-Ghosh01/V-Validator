import streamlit as st
import requests
from requests.exceptions import ConnectionError, Timeout

API_BASE = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="Spotline Knowledge Assistant",
    page_icon="📘",
    layout="wide",
)

st.markdown(
    """
    <style>
    .light-blue-box {
        background-color: rgba(33, 150, 243, 0.12); /* soft blue tint */
        color: #27E0F5; /* dark readable blue text */
        border-left: 5px solid #2196f3;
        padding: 0.75rem 1rem;
        border-radius: 8px;
        margin-bottom: 0.6rem;
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
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
                        data = res.json()

                        # Check if we have the new structured format
                        if "has_differences" in data:
                            # ═══════════════════════════════════════════════════════
                            # METADATA SECTION
                            # ═══════════════════════════════════════════════════════
                            st.markdown("---")
                            st.markdown("## 📋 Test Script Information")

                            client_meta = data.get("client_metadata", {})
                            executed_meta = data.get("executed_metadata", {})
                            stats = data.get("statistics", {})

                            # Create two columns for client and executed metadata
                            col1, col2 = st.columns(2)

                            with col1:
                                st.markdown("### 📄 Client Script")
                                if client_meta:
                                    st.markdown(f"**Script ID:** `{client_meta.get('script_id', 'N/A')}`")
                                    st.markdown(f"**Title:** {client_meta.get('title', 'N/A')}")
                                    st.markdown(f"**Description:** {client_meta.get('description', 'N/A')}")
                                    if client_meta.get('run_number'):
                                        st.markdown(f"**Run Number:** {client_meta.get('run_number')}")

                                # Client statistics
                                if stats.get("client"):
                                    client_stats = stats["client"]
                                    st.markdown("**Step Counts:**")
                                    st.metric("Total Steps", client_stats.get("total_steps", 0))

                                    metric_col1, metric_col2 = st.columns(2)
                                    with metric_col1:
                                        st.metric("Setup", client_stats.get("setup_steps", 0))
                                    with metric_col2:
                                        st.metric("Execution", client_stats.get("execution_steps", 0))

                            with col2:
                                st.markdown("### ✅ Executed Script (V-Assure)")
                                if executed_meta:
                                    st.markdown(f"**Script ID:** `{executed_meta.get('script_id', 'N/A')}`")
                                    st.markdown(f"**Title:** {executed_meta.get('title', 'N/A')}")
                                    st.markdown(f"**Description:** {executed_meta.get('description', 'N/A')}")

                                    # Execution timing
                                    if executed_meta.get('start_time'):
                                        st.markdown(f"**Start Time:** {executed_meta.get('start_time')}")
                                    if executed_meta.get('end_time'):
                                        st.markdown(f"**End Time:** {executed_meta.get('end_time')}")
                                    if executed_meta.get('script_run_time'):
                                        st.markdown(f"**⏱️ Run Time:** `{executed_meta.get('script_run_time')}`")

                                # Executed statistics
                                if stats.get("executed"):
                                    exec_stats = stats["executed"]
                                    st.markdown("**Step Counts:**")
                                    st.metric("Total Steps", exec_stats.get("total_steps", 0))

                                    metric_col1, metric_col2 = st.columns(2)
                                    with metric_col1:
                                        st.metric("Pre-Test Setup", exec_stats.get("pre_test_setup_steps", 0))
                                    with metric_col2:
                                        st.metric("Execution", exec_stats.get("execution_steps", 0))

                            # ═══════════════════════════════════════════════════════
                            # COMPARISON RESULTS SECTION
                            # ═══════════════════════════════════════════════════════
                            st.markdown("---")
                            st.markdown("## 🔍 Comparison Results")

                            # New structured format
                            if not data["has_differences"]:
                                st.success("✅ No differences found. Validation passed!")
                            else:
                                summary = data["summary"]
                                st.error(f"❌ Found {summary['total_issues']} issue(s)")

                                # Display summary metrics
                                col1, col2, col3 = st.columns(3)
                                with col1:
                                    st.metric("Total Issues", summary["total_issues"])
                                with col2:
                                    st.metric("Setup Steps", summary["setup_steps_with_issues"])
                                with col3:
                                    st.metric("Execution Steps", summary["execution_steps_with_issues"])

                                st.markdown("---")

                                # SETUP DIFFERENCES SECTION
                                if data["setup_differences"]:
                                    st.markdown("### 🔧 Setup Steps Differences")

                                    for step_num in sorted(data["setup_differences"].keys()):
                                        differences = data["setup_differences"][step_num]

                                        with st.expander(f"📍 Setup Step {step_num} - {len(differences)} issue(s)", expanded=True):
                                            for diff in differences:
                                                if diff["type"] == "missing":
                                                    st.error(f"⚠️ {diff['message']}")

                                                elif diff["type"] == "procedure_mismatch":
                                                    st.markdown(
                                                        "<div class='light-blue-box'><b>Procedure Mismatch</b></div>",
                                                        unsafe_allow_html=True,
                                                    )
                                                    col1, col2 = st.columns(2)
                                                    with col1:
                                                        st.markdown("**Client:**")
                                                        st.code(diff["client"], language=None)
                                                    with col2:
                                                        st.markdown("**Executed:**")
                                                        st.code(diff["executed"], language=None)

                            # EXECUTION DIFFERENCES SECTION
                            if data["execution_differences"]:
                                st.markdown("### ⚡ Execution Steps Differences")
                            
                                for step_num in sorted(data["execution_differences"].keys()):
                                    differences = data["execution_differences"][step_num]
                            
                                    # ✅ Count only real issues
                                    real_issues = [
                                        d for d in differences
                                        if d["type"] not in ["expected_with_dynamic_data"]
                                    ]
                            
                                    # ✅ Runtime-only validation
                                    runtime_only = [
                                        d for d in differences
                                        if d["type"] == "expected_with_dynamic_data"
                                    ]
                            
                                    # 🚫 Skip completely empty steps
                                    if not real_issues and not runtime_only:
                                        continue
                                    
                                    # ✅ Title logic
                                    if real_issues:
                                        title = f"📍 Execution Step {step_num} - {len(real_issues)} issue(s)"
                                    else:
                                        title = f"📍 Execution Step {step_num} - validated with runtime data"
                            
                                    with st.expander(title, expanded=True):
                                    
                                        # ─────────────────────────────
                                        # REAL ISSUES FIRST
                                        # ─────────────────────────────
                                        for diff in real_issues:
                                            if diff["type"] == "missing":
                                                st.error(f"⚠️ {diff['message']}")
                            
                                            elif diff["type"] == "procedure_mismatch":
                                                st.error("❌ Procedure mismatch")
                                                col1, col2 = st.columns(2)
                                                with col1:
                                                    st.markdown("**Client Procedure:**")
                                                    st.code(diff["client"], language=None)
                                                with col2:
                                                    st.markdown("**Executed Procedure:**")
                                                    st.code(diff["executed"], language=None)
                            
                                            elif diff["type"] == "expected_mismatch":
                                                st.warning("⚠ Expected results mismatch")
                                                col1, col2 = st.columns(2)
                                                with col1:
                                                    st.markdown("**Client Expected:**")
                                                    st.code(diff["client"], language=None)
                                                with col2:
                                                    st.markdown("**Executed Expected:**")
                                                    st.code(diff["executed"], language=None)
                            
                                            elif diff["type"] == "expected_vs_actual":
                                                st.error("❌ Expected vs Actual mismatch")
                                                col1, col2 = st.columns(2)
                                                with col1:
                                                    st.markdown("**Client Expected:**")
                                                    st.code(diff["client_expected"], language=None)
                                                with col2:
                                                    st.markdown("**Executed Actual:**")
                                                    st.code(diff["executed_actual"], language=None)
                            
                                            st.markdown("---")
                            
                                        # ─────────────────────────────
                                        # RUNTIME-GENERATED VALIDATION
                                        # ─────────────────────────────
                                        for diff in runtime_only:
                                            st.success("✔ Expected result met with runtime-generated data")
                            
                                            col1, col2 = st.columns(2)
                                            with col1:
                                                st.markdown("**Client Expected:**")
                                                st.code(diff.get("expected", ""), language=None)
                                            with col2:
                                                st.markdown("**Executed Actual:**")
                                                st.code(diff.get("actual", ""), language=None)
                            
                                            dynamic_data = diff.get("dynamic_data", {})
                                            if dynamic_data:
                                                st.markdown("**📌 Generated Values:**")
                                                for key, value in dynamic_data.items():
                                                    st.code(f"{key}: {value}", language=None)
                

                        else:
                            # Fallback for old format (list of strings)
                            diffs = data.get("differences", [])
                            if not diffs:
                                st.success("✅ No differences found. Validation passed!")
                            else:
                                st.error(f"❌ Differences detected ({len(diffs)}):")
                                for d in diffs:
                                    st.code(d)

                except Timeout:
                    st.error("⏱️ Comparison timed out.")
                except ConnectionError:
                    st.error("🔌 Backend not running.")
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
