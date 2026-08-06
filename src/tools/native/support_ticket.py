import uuid
from typing import Any, Dict


def create_support_ticket(subject: str, description: str = "", priority: str = "medium") -> Dict[str, Any]:
    """Creates a support ticket (mock native tool — no external ticketing system wired up)."""
    ticket_id = f"TCK-{uuid.uuid4().hex[:8].upper()}"
    return {
        "ticket_id": ticket_id,
        "subject": subject,
        "description": description,
        "priority": priority,
        "status": "open",
    }
