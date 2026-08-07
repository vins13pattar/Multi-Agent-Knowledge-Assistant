from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
import shutil, os, uuid, json, time
from datetime import datetime
from typing import Dict

from src.database.session import get_db
from src.database.models import (
    User, UserRole, Conversation, Message, SenderType,
    Document, DocumentStatus, ApprovalRequest, ApprovalStatus,
    AuditLog, KnowledgeSource, KnowledgeSourceType, Feedback,
    ConversationStatus, RiskLevel, RagEvalMetric, RagEvalRun
)
from src.auth.jwt_handler import sign_jwt, TokenResponse, get_password_hash, verify_password
from apps.api.dependencies import get_current_user, require_admin, require_employee

app = FastAPI(
    title="Multi-Agent Knowledge Assistant API",
    description="Enterprise-grade multi-agent AI assistant backed by LangGraph, ChromaDB and PostgreSQL.",
    version="1.0.0"
)

# CORS_ALLOWED_ORIGINS is a comma-separated list of trusted browser origins
# (e.g. "https://ui.example.com"). Wildcard origins can never be combined
# with allow_credentials=True — browsers will not honor it, and it would
# otherwise let any site make credentialed requests as the logged-in user.
_cors_origins = [o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/v1/health/live", tags=["Health"])
def liveness_check():
    return {"status": "ok"}

@app.get("/api/v1/health/ready", tags=["Health"])
def readiness_check(db: Session = Depends(get_db)):
    try:
        db.execute(db.query(User).limit(1).statement)
        return {"status": "ready"}
    except Exception:
        raise HTTPException(status_code=503, detail="Database unavailable")

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: str
    password: str

@app.post("/api/v1/auth/login", response_model=TokenResponse, tags=["Auth"])
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email).first()
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if user.status.value != "active":
        raise HTTPException(status_code=403, detail="Account is disabled")

    user.last_login_at = datetime.utcnow()
    db.commit()

    # Log auth event
    audit = AuditLog(actor_id=user.id, action="LOGIN", resource_type="user", resource_id=str(user.id))
    db.add(audit)
    db.commit()

    token = sign_jwt(user_id=str(user.id), role=user.role.value)
    return TokenResponse(access_token=token, token_type="Bearer", role=user.role.value)

# ---------------------------------------------------------------------------
# Users (admin only)
# ---------------------------------------------------------------------------

class CreateUserRequest(BaseModel):
    email: str
    password: str
    role: UserRole = UserRole.employee

@app.get("/api/v1/users", tags=["Users"])
def list_users(db: Session = Depends(get_db), current_user: dict = Depends(require_admin)):
    users = db.query(User).all()
    return [{"id": str(u.id), "email": u.email, "role": u.role.value, "status": u.status.value} for u in users]

@app.post("/api/v1/users", tags=["Users"])
def create_user(request: CreateUserRequest, db: Session = Depends(get_db), current_user: dict = Depends(require_admin)):
    if db.query(User).filter(User.email == request.email).first():
        raise HTTPException(status_code=400, detail="User already exists")
    user = User(email=request.email, password_hash=get_password_hash(request.password), role=request.role)
    db.add(user)
    db.commit()
    return {"id": str(user.id), "email": user.email, "role": user.role.value}

# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

@app.get("/api/v1/conversations", tags=["Conversations"])
def list_conversations(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    convos = db.query(Conversation).filter(
        Conversation.user_id == current_user["user_id"]
    ).order_by(Conversation.updated_at.desc()).all()
    return [{"id": str(c.id), "title": c.title, "status": c.status.value, "created_at": str(c.created_at)} for c in convos]

@app.post("/api/v1/conversations", tags=["Conversations"])
def create_conversation(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    thread_id = str(uuid.uuid4())
    convo = Conversation(
        user_id=current_user["user_id"],
        title="New Conversation",
        thread_id=thread_id
    )
    db.add(convo)
    db.commit()
    return {"id": str(convo.id), "thread_id": thread_id, "title": convo.title}

@app.get("/api/v1/conversations/{conversation_id}", tags=["Conversations"])
def get_conversation(conversation_id: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    convo = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if str(convo.user_id) != current_user["user_id"] and current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    msgs = [{"id": str(m.id), "role": m.sender_type.value, "content": m.content, "created_at": str(m.created_at)} for m in convo.messages]
    return {"id": str(convo.id), "title": convo.title, "messages": msgs}

# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

@app.post("/api/v1/documents/upload", tags=["Documents"])
def upload_document(
    file: UploadFile = File(...),
    access_scope: str = "shared",
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    from src.rag.documents import load_document, split_documents
    from src.rag.store import add_documents_to_store
    import hashlib
    from pathlib import Path

    if access_scope not in ("shared", "restricted"):
        raise HTTPException(status_code=400, detail="access_scope must be 'shared' or 'restricted'")

    upload_dir = "/tmp/knowledge_assistant_uploads"
    os.makedirs(upload_dir, exist_ok=True)
    # Derive the on-disk name from a UUID + the original extension only —
    # never trust a client-supplied filename as a filesystem path.
    safe_suffix = Path(file.filename or "").suffix[:10]
    file_path = os.path.join(upload_dir, f"{uuid.uuid4()}{safe_suffix}")

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    with open(file_path, "rb") as f:
        content_hash = hashlib.sha256(f.read()).hexdigest()

    # Check for duplicate — only successfully-ingested documents count. A prior
    # failed attempt must not permanently block re-upload of the same content.
    existing = db.query(Document).filter(
        Document.content_hash == content_hash,
        Document.status != DocumentStatus.failed,
    ).first()
    if existing:
        return {"status": "duplicate", "message": f"Document already ingested as '{existing.name}'"}

    db.query(Document).filter(
        Document.content_hash == content_hash,
        Document.status == DocumentStatus.failed,
    ).delete()

    doc_record = Document(
        name=file.filename,
        content_hash=content_hash,
        status=DocumentStatus.ingesting,
        uploaded_by=current_user["user_id"],
        access_scope=access_scope,
    )
    db.add(doc_record)
    db.commit()

    try:
        documents = load_document(file_path)
        chunks = split_documents(documents)
        for chunk in chunks:
            chunk.metadata["access_scope"] = access_scope
            # Loaders set "source" to the on-disk temp path (a throwaway UUID
            # filename); overwrite with the original filename so citations
            # shown to users, and anything matching on source downstream
            # (e.g. the eval harness), are human-readable.
            chunk.metadata["source"] = file.filename
        add_documents_to_store(chunks)
        doc_record.status = DocumentStatus.ingested
        doc_record.chunk_count = len(chunks)
        db.commit()
        return {"status": "success", "document_id": str(doc_record.id), "message": f"Ingested {len(chunks)} chunks from {file.filename}"}
    except Exception as e:
        doc_record.status = DocumentStatus.failed
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/documents", tags=["Documents"])
def list_documents(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    query = db.query(Document)
    if current_user["role"] != "admin":
        query = query.filter(Document.access_scope == "shared")
    docs = query.order_by(Document.created_at.desc()).all()
    return [{"id": str(d.id), "name": d.name, "status": d.status.value, "chunk_count": d.chunk_count, "created_at": str(d.created_at)} for d in docs]

# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

@app.get("/api/v1/retrieval/search", tags=["Retrieval"])
def search_documents(query: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    from src.rag.store import retrieve_documents, access_scope_filter, format_citations
    results = retrieve_documents(query, filter_metadata=access_scope_filter(current_user["role"]))
    citations = format_citations(results)
    return {
        "query": query,
        "results": [{"content": d.page_content, "metadata": d.metadata} for d in results],
        "citations": citations
    }

# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

from src.graph.builder import build_graph
assistant_graph = build_graph()

class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None

def _sse(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"

def _run_chat_graph(convo: Conversation, request: ChatRequest, current_user: dict, db: Session):
    history = [{"role": m.sender_type.value, "content": m.content} for m in convo.messages]

    initial_state = {
        "conversation_id": str(convo.id),
        "user_id": current_user["user_id"],
        "user_role": current_user["role"],
        "messages": history,
        "retrieved_documents": [],
        "citations": [],
        "tool_requests": [],
        "tool_results": [],
        "errors": []
    }

    config = {"configurable": {"thread_id": convo.thread_id}}

    yield _sse("start", {"conversation_id": str(convo.id)})

    turn_started_at = time.monotonic()
    node_latencies_ms: Dict[str, int] = {}

    def _timed_stream(input_state):
        node_started_at = time.monotonic()
        for step in assistant_graph.stream(input_state, config=config):
            now = time.monotonic()
            for node_name in step.keys():
                node_latencies_ms[node_name] = round((now - node_started_at) * 1000)
                yield node_name
            node_started_at = now

    try:
        for node_name in _timed_stream(initial_state):
            yield _sse("node", {"node": node_name})

        snapshot = assistant_graph.get_state(config)
        state_values = snapshot.values

        # Tool-call path paused at the HITL breakpoint: auto-resume low risk,
        # otherwise create an ApprovalRequest and wait for a human decision.
        if snapshot.next and "tool_execution" in snapshot.next:
            # Fail closed: an unclassified action requires approval rather
            # than auto-executing, so a missing/broken safety classification
            # can never silently skip HITL review.
            risk = state_values.get("risk_level") or "critical"
            if risk == "low":
                for node_name in _timed_stream(None):
                    yield _sse("node", {"node": node_name})
                state_values = assistant_graph.get_state(config).values
            else:
                tool_requests = state_values.get("tool_requests", [])
                req = tool_requests[-1] if tool_requests else {}
                approval = ApprovalRequest(
                    conversation_id=convo.id,
                    requested_by=current_user["user_id"],
                    action_type=req.get("tool_name", "unknown"),
                    action_payload=req,
                    risk_level=RiskLevel(risk),
                    thread_id=convo.thread_id,
                )
                db.add(approval)
                pending_text = f"This action requires admin approval: {req.get('action_description', req.get('tool_name', ''))}"
                assistant_msg = Message(
                    conversation_id=convo.id,
                    sender_type=SenderType.assistant,
                    content=pending_text,
                    structured_content={"risk_level": risk, "approval_id": None}
                )
                db.add(assistant_msg)
                db.commit()
                assistant_msg.structured_content = {"risk_level": risk, "approval_id": str(approval.id)}
                db.commit()
                yield _sse("approval_pending", {
                    "approval_id": str(approval.id),
                    "risk_level": risk,
                    "message": pending_text
                })
                return

        messages = state_values.get("messages", [])
        response_text = messages[-1]["content"] if messages else "No response generated."
        citations = state_values.get("citations", [])
        risk = state_values.get("risk_level")

        assistant_msg = Message(
            conversation_id=convo.id,
            sender_type=SenderType.assistant,
            content=response_text,
            structured_content={"citations": citations, "risk_level": risk}
        )
        db.add(assistant_msg)
        if convo.title == request.message[:60]:
            convo.updated_at = datetime.utcnow()
        db.flush()

        # Only knowledge_query turns go through retrieval/verification — tool
        # requests and general conversation have nothing meaningful to score.
        if state_values.get("user_intent") == "knowledge_query":
            retrieved = state_values.get("retrieved_documents", [])
            verification = state_values.get("verification_result") or {}
            db.add(RagEvalMetric(
                message_id=assistant_msg.id,
                conversation_id=convo.id,
                user_intent=state_values.get("user_intent"),
                retrieved_count=len(retrieved),
                retrieval_empty=len(retrieved) == 0,
                faithfulness_status=verification.get("status"),
                unsupported_claims=verification.get("unsupported_claims", []),
                citation_count=len(citations),
                node_latencies_ms=node_latencies_ms,
                total_latency_ms=round((time.monotonic() - turn_started_at) * 1000),
            ))
        db.commit()

        yield _sse("done", {
            "conversation_id": str(convo.id),
            "response": response_text,
            "citations": citations,
            "risk_level": risk
        })
    except Exception as e:
        db.rollback()
        yield _sse("error", {"message": str(e)})

@app.post("/api/v1/chat/stream", tags=["Chat"])
def chat_stream(
    request: ChatRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    if request.conversation_id:
        convo = db.query(Conversation).filter(Conversation.id == request.conversation_id).first()
        if not convo:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        thread_id = str(uuid.uuid4())
        convo = Conversation(
            user_id=current_user["user_id"],
            title=request.message[:60],
            thread_id=thread_id
        )
        db.add(convo)
        db.commit()

    user_msg = Message(
        conversation_id=convo.id,
        sender_type=SenderType.user,
        content=request.message
    )
    db.add(user_msg)
    db.commit()
    db.refresh(convo)

    return StreamingResponse(
        _run_chat_graph(convo, request, current_user, db),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )

# ---------------------------------------------------------------------------
# Approvals
# ---------------------------------------------------------------------------

@app.get("/api/v1/approvals", tags=["Approvals"])
def list_approvals(db: Session = Depends(get_db), current_user: dict = Depends(require_admin)):
    approvals = db.query(ApprovalRequest).filter(
        ApprovalRequest.status == ApprovalStatus.pending
    ).order_by(ApprovalRequest.created_at.desc()).all()
    return [{
        "id": str(a.id),
        "action_type": a.action_type,
        "risk_level": a.risk_level.value,
        "status": a.status.value,
        "thread_id": a.thread_id,
        "created_at": str(a.created_at)
    } for a in approvals]

def _resume_graph_after_decision(approval: ApprovalRequest, decision: str, convo: Conversation | None, db: Session) -> str | None:
    """Resumes the paused LangGraph checkpoint for this approval's thread and
    persists the resulting assistant message. Returns the response text, if any."""
    config = {"configurable": {"thread_id": approval.thread_id}}
    assistant_graph.update_state(config, {"approval_status": decision})
    result_state = assistant_graph.invoke(None, config=config)

    messages = result_state.get("messages", [])
    response_text = messages[-1]["content"] if messages else None
    if response_text and convo:
        assistant_msg = Message(
            conversation_id=convo.id,
            sender_type=SenderType.assistant,
            content=response_text,
            structured_content={"citations": result_state.get("citations", []), "approval_id": str(approval.id)}
        )
        db.add(assistant_msg)
    return response_text

@app.post("/api/v1/approvals/{approval_id}/approve", tags=["Approvals"])
def approve_action(approval_id: str, db: Session = Depends(get_db), current_user: dict = Depends(require_admin)):
    approval = db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if approval.status != ApprovalStatus.pending:
        raise HTTPException(status_code=400, detail="Approval request already decided")

    approval.status = ApprovalStatus.approved
    approval.approved_by = current_user["user_id"]
    approval.decided_at = datetime.utcnow()
    audit = AuditLog(actor_id=current_user["user_id"], action="HITL_APPROVED", resource_type="approval", resource_id=approval_id)
    db.add(audit)
    db.commit()

    convo = db.query(Conversation).filter(Conversation.thread_id == approval.thread_id).first()
    response_text = _resume_graph_after_decision(approval, "approved", convo, db)
    db.commit()
    return {"status": "approved", "approval_id": approval_id, "response": response_text}

@app.post("/api/v1/approvals/{approval_id}/reject", tags=["Approvals"])
def reject_action(approval_id: str, comment: str = "", db: Session = Depends(get_db), current_user: dict = Depends(require_admin)):
    approval = db.query(ApprovalRequest).filter(ApprovalRequest.id == approval_id).first()
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if approval.status != ApprovalStatus.pending:
        raise HTTPException(status_code=400, detail="Approval request already decided")

    approval.status = ApprovalStatus.rejected
    approval.approved_by = current_user["user_id"]
    approval.approver_comment = comment
    approval.decided_at = datetime.utcnow()
    audit = AuditLog(actor_id=current_user["user_id"], action="HITL_REJECTED", resource_type="approval", resource_id=approval_id)
    db.add(audit)
    db.commit()

    convo = db.query(Conversation).filter(Conversation.thread_id == approval.thread_id).first()
    response_text = _resume_graph_after_decision(approval, "rejected", convo, db)
    db.commit()
    return {"status": "rejected", "approval_id": approval_id, "response": response_text}

# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

class FeedbackRequest(BaseModel):
    message_id: str
    rating: int
    category: str | None = None
    comment: str | None = None

@app.post("/api/v1/feedback", tags=["Feedback"])
def submit_feedback(request: FeedbackRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    message = db.query(Message).filter(Message.id == request.message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    if str(message.conversation.user_id) != current_user["user_id"] and current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    fb = Feedback(
        message_id=request.message_id,
        user_id=current_user["user_id"],
        rating=request.rating,
        category=request.category,
        comment=request.comment
    )
    db.add(fb)
    db.commit()
    return {"status": "recorded"}

# ---------------------------------------------------------------------------
# Audit Logs
# ---------------------------------------------------------------------------

@app.get("/api/v1/audit-logs", tags=["Audit"])
def get_audit_logs(limit: int = 50, db: Session = Depends(get_db), current_user: dict = Depends(require_admin)):
    logs = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()
    return [{
        "id": str(l.id),
        "actor_id": str(l.actor_id) if l.actor_id else None,
        "action": l.action,
        "resource_type": l.resource_type,
        "resource_id": l.resource_id,
        "created_at": str(l.created_at)
    } for l in logs]

# ---------------------------------------------------------------------------
# RAG Evals
# ---------------------------------------------------------------------------

@app.get("/api/v1/evals/metrics", tags=["Evals"])
def get_eval_metrics(days: int = 7, limit: int = 200, db: Session = Depends(get_db), current_user: dict = Depends(require_admin)):
    """Aggregated online RAG metrics — one row per knowledge_query chat turn,
    captured in the chat stream handler (see RagEvalMetric)."""
    from datetime import timedelta
    since = datetime.utcnow() - timedelta(days=days)
    rows = (
        db.query(RagEvalMetric)
        .filter(RagEvalMetric.created_at >= since)
        .order_by(RagEvalMetric.created_at.desc())
        .limit(limit)
        .all()
    )

    turn_count = len(rows)
    if turn_count == 0:
        return {
            "window_days": days,
            "turn_count": 0,
            "retrieval_empty_rate": None,
            "faithfulness_verified_rate": None,
            "avg_citation_count": None,
            "avg_total_latency_ms": None,
            "avg_node_latencies_ms": {},
            "feedback_by_faithfulness": {},
            "recent": [],
        }

    empty_count = sum(1 for r in rows if r.retrieval_empty)
    verified_count = sum(1 for r in rows if r.faithfulness_status == "verified")
    scored_count = sum(1 for r in rows if r.faithfulness_status is not None)
    total_latencies = [r.total_latency_ms for r in rows if r.total_latency_ms is not None]

    node_totals: Dict[str, list] = {}
    for r in rows:
        for node, ms in (r.node_latencies_ms or {}).items():
            node_totals.setdefault(node, []).append(ms)
    avg_node_latencies = {node: round(sum(vals) / len(vals)) for node, vals in node_totals.items()}

    message_ids = [r.message_id for r in rows]
    feedback_rows = db.query(Feedback).filter(Feedback.message_id.in_(message_ids)).all() if message_ids else []
    feedback_by_message = {f.message_id: f.rating for f in feedback_rows if f.rating is not None}
    ratings_by_status: Dict[str, list] = {}
    for r in rows:
        rating = feedback_by_message.get(r.message_id)
        if rating is not None and r.faithfulness_status:
            ratings_by_status.setdefault(r.faithfulness_status, []).append(rating)
    feedback_by_faithfulness = {status: round(sum(vals) / len(vals), 2) for status, vals in ratings_by_status.items()}

    return {
        "window_days": days,
        "turn_count": turn_count,
        "retrieval_empty_rate": round(empty_count / turn_count, 3),
        "faithfulness_verified_rate": round(verified_count / scored_count, 3) if scored_count else None,
        "avg_citation_count": round(sum(r.citation_count or 0 for r in rows) / turn_count, 2),
        "avg_total_latency_ms": round(sum(total_latencies) / len(total_latencies)) if total_latencies else None,
        "avg_node_latencies_ms": avg_node_latencies,
        "feedback_by_faithfulness": feedback_by_faithfulness,
        "recent": [{
            "created_at": str(r.created_at),
            "retrieved_count": r.retrieved_count,
            "faithfulness_status": r.faithfulness_status,
            "citation_count": r.citation_count,
            "total_latency_ms": r.total_latency_ms,
        } for r in rows],
    }


@app.get("/api/v1/evals/runs", tags=["Evals"])
def list_eval_runs(limit: int = 20, db: Session = Depends(get_db), current_user: dict = Depends(require_admin)):
    runs = db.query(RagEvalRun).order_by(RagEvalRun.started_at.desc()).limit(limit).all()
    return [{
        "id": str(r.id),
        "dataset_name": r.dataset_name,
        "status": r.status.value,
        "question_count": r.question_count,
        "avg_hit_rate": r.avg_hit_rate,
        "avg_mrr": r.avg_mrr,
        "avg_faithfulness": r.avg_faithfulness,
        "avg_answer_relevancy": r.avg_answer_relevancy,
        "started_at": str(r.started_at),
        "finished_at": str(r.finished_at) if r.finished_at else None,
    } for r in runs]


@app.get("/api/v1/evals/runs/{run_id}", tags=["Evals"])
def get_eval_run(run_id: str, db: Session = Depends(get_db), current_user: dict = Depends(require_admin)):
    run = db.query(RagEvalRun).filter(RagEvalRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Eval run not found")
    return {
        "id": str(run.id),
        "dataset_name": run.dataset_name,
        "status": run.status.value,
        "question_count": run.question_count,
        "avg_hit_rate": run.avg_hit_rate,
        "avg_mrr": run.avg_mrr,
        "avg_faithfulness": run.avg_faithfulness,
        "avg_answer_relevancy": run.avg_answer_relevancy,
        "error": run.error,
        "started_at": str(run.started_at),
        "finished_at": str(run.finished_at) if run.finished_at else None,
        "results": [{
            "question": res.question,
            "expected_source": res.expected_source,
            "retrieved_sources": res.retrieved_sources,
            "hit": res.hit,
            "reciprocal_rank": res.reciprocal_rank,
            "faithfulness_score": res.faithfulness_score,
            "answer_relevancy_score": res.answer_relevancy_score,
            "generated_answer": res.generated_answer,
        } for res in run.results],
    }


@app.post("/api/v1/evals/run", tags=["Evals"])
def trigger_eval_run(background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: dict = Depends(require_admin)):
    """Kicks off an offline eval run against the golden dataset in the
    background (it makes several LLM calls per question, so it's too slow to
    run inline) and returns the run id immediately so the dashboard can poll
    GET /api/v1/evals/runs/{run_id} for status."""
    from apps.api.eval_runner import create_run_row, execute_eval_run
    run_id = create_run_row(db, triggered_by=current_user["user_id"])
    background_tasks.add_task(execute_eval_run, run_id)
    return {"status": "started", "run_id": run_id}
