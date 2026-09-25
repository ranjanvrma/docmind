"""DocMind Streamlit frontend.

The UI holds no ML logic. Every action is an HTTP call to the FastAPI backend
(``DOCMIND_API_URL``, default http://127.0.0.1:8000), so the UI and API can
run in separate processes or containers.

Run with:  streamlit run frontend/streamlit_app.py
"""

from __future__ import annotations

import os

import pandas as pd
import requests
import streamlit as st

API_URL = os.getenv("DOCMIND_API_URL", "http://127.0.0.1:8000").rstrip("/")
SHORT_TIMEOUT = 15
LONG_TIMEOUT = 900  # processing large PDFs on CPU can take minutes


class APIError(Exception):
    pass


def api_request(method: str, path: str, timeout: float = SHORT_TIMEOUT, **kwargs):
    try:
        response = requests.request(method, f"{API_URL}{path}", timeout=timeout, **kwargs)
    except requests.ConnectionError as exc:
        raise APIError(f"Cannot reach the DocMind API at {API_URL}. Is it running? (python main.py api)") from exc
    except requests.Timeout as exc:
        raise APIError("The API request timed out.") from exc

    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        if isinstance(detail, list):  # FastAPI validation errors
            detail = "; ".join(f"{'.'.join(map(str, d.get('loc', [])[1:]))}: {d.get('msg')}" for d in detail)
        raise APIError(f"{detail} (HTTP {response.status_code})")
    return response.json() if response.content else None


def show_passage(hit: dict, label: str) -> None:
    with st.expander(label):
        st.caption(f"Document: {hit['doc_name']}  |  Page: {hit['page_number']}  |  Chunk: {hit['chunk_id']}")
        st.markdown(f"> {hit['text']}")


# ----------------------------------------------------------------------------
st.set_page_config(page_title="DocMind", layout="wide")
st.title("DocMind")
st.caption("Upload PDFs, search them semantically, and ask questions answered from their content.")

# --------------------------------------------------------------------- sidebar
health, documents = None, []
with st.sidebar:
    st.header("Backend")
    try:
        health = api_request("GET", "/health")
        documents = api_request("GET", "/documents")
        st.success(f"API connected ({health['indexed_chunks']} chunks indexed)")
        st.caption(f"Embeddings: `{health['embedding_model']}`")
        if health["llm_configured"]:
            st.caption(f"LLM: `{health['llm_provider']}` / `{health['llm_model']}`")
        else:
            st.warning("No LLM configured. Search works; Q&A needs LLM_API_KEY in .env.")
    except APIError as exc:
        st.error(str(exc))

    st.header("Retrieval settings")
    top_k = st.slider("Top-k chunks", min_value=1, max_value=20, value=5)
    processed = [d for d in documents if d["status"] == "processed"]
    names = {d["doc_id"]: d["filename"] for d in processed}
    selected = st.multiselect(
        "Limit to documents (optional)", options=list(names), format_func=lambda i: names[i]
    )
    doc_filter = selected or None

    st.header("Documents")
    if not documents:
        st.caption("No documents uploaded yet.")
    for d in documents:
        label = (d.get("classification") or {}).get("label", "")
        marker = {"processed": "[indexed]", "uploaded": "[not processed]", "failed": "[failed]"}[d["status"]]
        st.markdown(f"**{d['filename']}**  \n{marker} {label} · {d['page_count']} pages · {d['chunk_count']} chunks")

if health is None:
    st.stop()

# ---------------------------------------------------------------------- upload
st.subheader("1. Upload and index PDFs")
files = st.file_uploader("PDF files", type=["pdf"], accept_multiple_files=True)
col_upload, col_process = st.columns([1, 1])
if col_upload.button("Upload & process", type="primary", disabled=not files):
    try:
        payload = [("files", (f.name, f.getvalue(), "application/pdf")) for f in files]
        uploaded = api_request("POST", "/documents/upload", files=payload, timeout=120)
        for item in uploaded["items"]:
            msg = f"{item['filename']}: {item['status']}" + (f" - {item['detail']}" if item["detail"] else "")
            (st.warning if item["status"] != "uploaded" else st.info)(msg)
        ids = [i["doc_id"] for i in uploaded["items"] if i["doc_id"]]
        if ids:
            with st.spinner("Extracting, chunking, embedding and indexing..."):
                result = api_request("POST", "/documents/process", json={"doc_ids": ids}, timeout=LONG_TIMEOUT)
            for item in result["items"]:
                if item["status"] == "failed":
                    st.error(f"{item['filename']}: {item['detail']}")
                elif item["skipped"]:
                    st.info(f"{item['filename']}: already indexed")
                else:
                    st.success(f"{item['filename']}: indexed {item['chunk_count']} chunks")
                    if item["detail"]:
                        st.warning(item["detail"])
    except APIError as exc:
        st.error(str(exc))

if col_process.button("Process pending documents", disabled=not any(d["status"] != "processed" for d in documents)):
    try:
        with st.spinner("Processing..."):
            result = api_request("POST", "/documents/process", json={}, timeout=LONG_TIMEOUT)
        st.success(f"Done. {result['indexed_chunks']} chunks indexed.")
    except APIError as exc:
        st.error(str(exc))

# ------------------------------------------------------------------------ tabs
st.subheader("2. Explore")
tab_search, tab_ask, tab_docs = st.tabs(["Semantic search", "Ask a question", "Documents & classification"])

with tab_search:
    with st.form("search"):
        query = st.text_input("Search query", placeholder="e.g. What were the main risks identified?")
        submitted = st.form_submit_button("Search")
    if submitted:
        if not query.strip():
            st.warning("Enter a query.")
        else:
            try:
                data = api_request("POST", "/search", json={"query": query, "top_k": top_k, "doc_ids": doc_filter})
                if not data["results"]:
                    st.info("No results. Upload and process documents first.")
                for hit in data["results"]:
                    show_passage(
                        hit, f"#{hit['rank']}  ·  {hit['doc_name']}  ·  page {hit['page_number']}  ·  score {hit['score']:.3f}"
                    )
                st.caption("Score = cosine similarity between query and chunk embeddings (higher is more similar).")
            except APIError as exc:
                st.error(str(exc))

with tab_ask:
    with st.form("ask"):
        question = st.text_area("Question", placeholder="e.g. What is the refund policy for annual plans?")
        asked = st.form_submit_button("Ask", disabled=not health["llm_configured"])
    if not health["llm_configured"]:
        st.info("Question answering is disabled until an LLM is configured (see README > Environment variables).")
    if asked:
        if not question.strip():
            st.warning("Enter a question.")
        else:
            try:
                with st.spinner("Retrieving context and generating an answer..."):
                    data = api_request(
                        "POST",
                        "/ask",
                        json={"question": question, "top_k": top_k, "doc_ids": doc_filter},
                        timeout=180,
                    )
                st.markdown("#### Answer")
                st.markdown(data["answer"])
                if not data["answered_from_documents"]:
                    st.warning("The answer is not supported by cited passages from your documents.")
                if data["invalid_citations"]:
                    st.warning(
                        f"The model cited source numbers that were not provided: {data['invalid_citations']}. "
                        "Those citations are not real."
                    )
                if data["sources"]:
                    st.markdown("#### Sources")
                    st.caption("These are exactly the passages given to the LLM. 'Cited' means the answer references it.")
                    ordered = sorted(data["sources"], key=lambda s: (not s["cited"], s["source_number"]))
                    for src in ordered:
                        tag = "cited" if src["cited"] else "retrieved, not cited"
                        show_passage(
                            src,
                            f"Source {src['source_number']} ({tag})  ·  {src['doc_name']}  ·  page {src['page_number']}  ·  score {src['score']:.3f}",
                        )
            except APIError as exc:
                st.error(str(exc))

with tab_docs:
    if not documents:
        st.info("No documents yet.")
    else:
        rows = [
            {
                "File": d["filename"],
                "Status": d["status"],
                "Pages": d["page_count"],
                "Empty pages": len(d["empty_pages"]),
                "Chunks": d["chunk_count"],
                "Category": (d.get("classification") or {}).get("label"),
                "Method": (d.get("classification") or {}).get("method"),
                "Uploaded": d["uploaded_at"],
                "ID": d["doc_id"],
            }
            for d in documents
        ]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

        choice = st.selectbox("Inspect a document", options=[d["doc_id"] for d in documents],
                              format_func=lambda i: next(d["filename"] for d in documents if d["doc_id"] == i))
        doc = next(d for d in documents if d["doc_id"] == choice)
        if doc.get("error"):
            st.error(doc["error"])
        for warning in doc.get("warnings", []):
            st.warning(warning)
        if doc.get("classification"):
            cls = doc["classification"]
            st.markdown(f"**Predicted category:** {cls['label']}  (method: {cls['method']})")
            st.caption(
                "Supervised scores are class probabilities. Zero-shot scores are cosine similarities to "
                "category descriptions; they are not probabilities."
            )
            st.bar_chart(pd.Series(cls["scores"], name="score"))
        if st.button("Delete this document", type="secondary"):
            try:
                api_request("DELETE", f"/documents/{choice}")
                st.success("Deleted.")
                st.rerun()
            except APIError as exc:
                st.error(str(exc))
