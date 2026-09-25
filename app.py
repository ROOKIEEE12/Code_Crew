"""
app.py
------
A web interface for CodeCrew, built with Streamlit.
Run: streamlit run app.py

Describe anything from a single function to a full website. Watch every
agent's progress live, then browse the generated files, download the whole
project as a zip, and see whether all checks passed.
"""

import io
import zipfile

import streamlit as st
from orchestrator import run_pipeline

st.set_page_config(page_title="CodeCrew", page_icon="🤖", layout="wide")

st.title("🤖 CodeCrew — Multi-Agent Software Engineering Team")
st.caption(
    "Describe what you want built — a single function, or a full website. "
    "A team of AI agents will plan, code, test, debug, and document it."
)

request = st.text_area(
    "What do you want built?",
    placeholder="e.g. A personal portfolio website with a home page, an about section, and a contact form.",
    height=100,
)

if st.button("🚀 Build it", type="primary") and request.strip():
    log_placeholder = st.empty()
    logs = []

    def live_log(message: str):
        logs.append(message)
        log_placeholder.code("\n".join(logs), language=None)

    with st.spinner("The team is working..."):
        result = run_pipeline(request, log=live_log)

    plan = result["plan"]
    files = result["files"]

    if result["tests_passed"]:
        st.success(f"✅ '{plan['project_name']}' is done — all checks passed!")
    else:
        st.warning(f"⚠️ '{plan['project_name']}' finished, but some issues remain after retries.")

    st.subheader(plan["project_name"])
    st.write(plan["summary"])
    st.caption(f"Saved to: `{result['project_dir']}`")

    # Zip everything up for a one-click download
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, f in files.items():
            zf.writestr(path, f["code"])
        zf.writestr("README.md", result["readme"])
    st.download_button(
        "⬇️ Download project as .zip",
        data=zip_buffer.getvalue(),
        file_name=f"{plan['project_name']}.zip",
        mime="application/zip",
    )

    tab_names = list(files.keys()) + ["README.md"]
    tabs = st.tabs(tab_names)
    for tab, path in zip(tabs, files.keys()):
        with tab:
            st.code(files[path]["code"], language=files[path]["language"])
    with tabs[-1]:
        st.markdown(result["readme"])

    with st.expander("🔍 Testing & QA report"):
        cr = result["check_result"]
        if cr:
            st.write("**Syntax checks:**")
            for path, r in cr["syntax_results"].items():
                icon = "✅" if r["passed"] else ("⏭️" if not r["checked"] else "❌")
                st.text(f"{icon} {path}")
            st.write("**Python test suite:**", "✅ passed" if cr["pytest"]["passed"] else "❌ failed")
            if cr["review"]["issues"]:
                st.write("**QA review findings:**")
                for issue in cr["review"]["issues"]:
                    st.text(f"[{issue.get('severity', '?')}] {issue['file']}: {issue['problem']}")
            else:
                st.write("**QA review findings:** none")

    with st.expander("🪵 Full agent activity log"):
        st.text("\n".join(result["activity_log"]))
