import logging
from datetime import datetime
import json
import os

AUDIT_LOG_FILE = os.getenv("AUDIT_LOG_FILE", "/tmp/knowledge_assistant_audit.log")

def log_audit_event(user_id: str, action: str, resource: str, status: str, risk_level: str = "low"):
    """
    Logs an audit event for governance and compliance.
    In a real system, this would write to a secure, append-only database table.
    """
    event = {
        "timestamp": datetime.utcnow().isoformat(),
        "user_id": user_id,
        "action": action,
        "resource": resource,
        "status": status,
        "risk_level": risk_level
    }
    
    # Write to local file for now
    with open(AUDIT_LOG_FILE, "a") as f:
        f.write(json.dumps(event) + "\n")
        
    logging.info(f"AUDIT EVENT: {action} on {resource} by {user_id} (Status: {status})")
