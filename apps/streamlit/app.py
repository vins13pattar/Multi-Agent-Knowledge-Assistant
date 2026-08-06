import json
import os

import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Enterprise Knowledge Assistant",
    page_icon="🤖",
    layout="wide"
)


# --- Helper functions ---
def login(email: str, password: str):
    try:
        resp = requests.post(
            f"{API_URL}/api/v1/auth/login",
            json={"email": email, "password": password},
            timeout=10
        )
        if resp.status_code == 200:
            return resp.json()
        return None
    except requests.exceptions.ConnectionError:
        st.error("⚠️ Cannot connect to the API server.")
        return None


def _auth_headers():
    return {"Authorization": f"Bearer {st.session_state.token}"}


def chat(message: str, token: str, conversation_id: str | None = None):
    """Consumes the SSE stream from /chat/stream and returns the final payload."""
    payload = {"message": message}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    try:
        with requests.post(
            f"{API_URL}/api/v1/chat/stream",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=120,
            stream=True,
        ) as resp:
            if resp.status_code != 200:
                return {"response": f"API error: {resp.text}", "citations": []}

            event_type, data_lines = None, []
            for raw_line in resp.iter_lines(decode_unicode=True):
                if raw_line is None:
                    continue
                line = raw_line.strip()
                if line == "":
                    if event_type and data_lines:
                        data = json.loads("".join(data_lines))
                        if event_type == "done":
                            return {**data, "status": "done"}
                        if event_type == "approval_pending":
                            return {**data, "status": "approval_pending", "response": data.get("message")}
                        if event_type == "error":
                            return {"response": f"Error: {data.get('message')}", "citations": [], "status": "error"}
                    event_type, data_lines = None, []
                    continue
                if line.startswith("event:"):
                    event_type = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data_lines.append(line.split(":", 1)[1].strip())
            return {"response": "No response received from stream.", "citations": []}
    except requests.exceptions.ConnectionError:
        return {"response": "⚠️ Cannot connect to the API server.", "citations": []}


def upload_document(file, token: str):
    try:
        resp = requests.post(
            f"{API_URL}/api/v1/documents/upload",
            files={"file": (file.name, file, file.type)},
            headers={"Authorization": f"Bearer {token}"},
            timeout=30
        )
        return resp.json()
    except requests.exceptions.ConnectionError:
        return {"status": "error", "message": "Cannot connect to API."}


def api_get(path: str, params: dict | None = None):
    try:
        resp = requests.get(f"{API_URL}{path}", headers=_auth_headers(), params=params or {}, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        st.error(f"API error ({resp.status_code}): {resp.text}")
        return None
    except requests.exceptions.ConnectionError:
        st.error("⚠️ Cannot connect to the API server.")
        return None


def api_post(path: str, json_body: dict | None = None, params: dict | None = None):
    try:
        resp = requests.post(f"{API_URL}{path}", headers=_auth_headers(), json=json_body, params=params or {}, timeout=30)
        return resp
    except requests.exceptions.ConnectionError:
        st.error("⚠️ Cannot connect to the API server.")
        return None


# --- Session state defaults ---
for key, default in [("token", None), ("role", None), ("messages", []), ("conversation_id", None)]:
    if key not in st.session_state:
        st.session_state[key] = default

# --- Login View ---
if not st.session_state.token:
    st.title("🤖 Enterprise Knowledge Assistant")
    st.markdown("### Sign In")

    with st.form("login_form"):
        email = st.text_input("Email", placeholder="admin@example.com")
        password = st.text_input("Password", type="password", placeholder="password")
        submitted = st.form_submit_button("Login")

    if submitted:
        result = login(email, password)
        if result:
            st.session_state.token = result["access_token"]
            st.session_state.role = result["role"]
            st.rerun()
        else:
            st.error("Invalid credentials. Please try again.")

    st.divider()
    st.caption("Demo credentials: `admin@example.com` / `admin` or `employee@example.com` / `employee`")

# --- Main App View ---
else:
    with st.sidebar:
        st.title("🤖 Knowledge Assistant")
        st.markdown(f"**Role:** `{st.session_state.role.capitalize()}`")
        st.divider()

        if st.session_state.role == "admin":
            st.markdown("### 📄 Upload Document")
            uploaded_file = st.file_uploader(
                "Upload a PDF, TXT, or Markdown file",
                type=["pdf", "txt", "md"]
            )
            if uploaded_file and st.button("Ingest Document"):
                with st.spinner("Ingesting..."):
                    result = upload_document(uploaded_file, st.session_state.token)
                    if result.get("status") == "success":
                        st.success(result["message"])
                    else:
                        st.error(result.get("message", "Upload failed."))

        st.divider()
        if st.button("Logout"):
            st.session_state.token = None
            st.session_state.role = None
            st.session_state.messages = []
            st.session_state.conversation_id = None
            st.rerun()

    if st.session_state.role == "admin":
        tab_chat, tab_approvals, tab_docs, tab_audit = st.tabs(
            ["💬 Chat", "✅ Approval Queue", "📄 Document Status", "🧾 Audit Log"]
        )
    else:
        (tab_chat,) = st.tabs(["💬 Chat"])

    # --- Chat tab ---
    with tab_chat:
        st.title("💬 Chat")

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg.get("citations"):
                    with st.expander("📚 Sources"):
                        st.markdown(msg["citations"])

        if prompt := st.chat_input("Ask a question about company knowledge..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    result = chat(prompt, st.session_state.token, st.session_state.conversation_id)
                response = result.get("response", "No response.")
                citations = result.get("citations", [])
                risk = result.get("risk_level")
                if result.get("conversation_id"):
                    st.session_state.conversation_id = result["conversation_id"]

                st.markdown(response)

                if result.get("status") == "approval_pending":
                    st.warning("⏳ This action requires admin approval before it can proceed.")
                elif risk in ("high", "critical"):
                    st.warning("⚠️ This action was flagged as high risk.")

                if citations:
                    with st.expander("📚 Sources"):
                        for c in citations:
                            st.markdown(c)

            st.session_state.messages.append({
                "role": "assistant",
                "content": response,
                "citations": "\n".join(citations) if citations else None
            })

    # --- Admin-only tabs ---
    if st.session_state.role == "admin":
        with tab_approvals:
            st.title("✅ Approval Queue")
            st.caption("Actions flagged as medium risk or higher, paused by the HITL breakpoint until reviewed.")
            if st.button("🔄 Refresh", key="refresh_approvals"):
                st.rerun()

            approvals = api_get("/api/v1/approvals") or []
            if not approvals:
                st.info("No pending approvals.")
            for a in approvals:
                with st.container(border=True):
                    cols = st.columns([3, 1, 1, 1])
                    cols[0].markdown(f"**{a['action_type']}** — risk: `{a['risk_level']}`")
                    cols[0].caption(f"Requested at {a['created_at']} · id `{a['id']}`")
                    if cols[1].button("Approve", key=f"approve_{a['id']}"):
                        resp = api_post(f"/api/v1/approvals/{a['id']}/approve")
                        if resp is not None and resp.status_code == 200:
                            st.success("Approved and resumed.")
                            st.rerun()
                        elif resp is not None:
                            st.error(resp.text)
                    if cols[2].button("Reject", key=f"reject_{a['id']}"):
                        resp = api_post(f"/api/v1/approvals/{a['id']}/reject", params={"comment": "Rejected via admin dashboard"})
                        if resp is not None and resp.status_code == 200:
                            st.success("Rejected.")
                            st.rerun()
                        elif resp is not None:
                            st.error(resp.text)

        with tab_docs:
            st.title("📄 Document Ingestion Status")
            if st.button("🔄 Refresh", key="refresh_docs"):
                st.rerun()
            docs = api_get("/api/v1/documents") or []
            if not docs:
                st.info("No documents ingested yet.")
            else:
                status_icon = {"ingested": "✅", "ingesting": "⏳", "pending": "🕒", "failed": "❌"}
                for d in docs:
                    icon = status_icon.get(d["status"], "•")
                    st.markdown(f"{icon} **{d['name']}** — `{d['status']}` — {d['chunk_count']} chunks — {d['created_at']}")

        with tab_audit:
            st.title("🧾 Audit Log")
            limit = st.slider("Number of entries", 10, 200, 50, key="audit_limit")
            if st.button("🔄 Refresh", key="refresh_audit"):
                st.rerun()
            logs = api_get("/api/v1/audit-logs", params={"limit": limit}) or []
            if not logs:
                st.info("No audit log entries yet.")
            else:
                st.dataframe(logs, use_container_width=True)
