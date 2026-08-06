from typing import Annotated, List, Dict, Any, Optional
from typing_extensions import TypedDict
import operator

def append_to_list(current: List, new: List) -> List:
    return current + (new if isinstance(new, list) else [new])

class AssistantState(TypedDict):
    conversation_id: str
    user_id: str
    user_role: str
    messages: Annotated[List[Dict[str, Any]], append_to_list]
    user_intent: Optional[str]
    retrieved_documents: Annotated[List[Dict[str, Any]], append_to_list]
    citations: Annotated[List[str], append_to_list]
    tool_requests: Annotated[List[Dict[str, Any]], append_to_list]
    tool_results: Annotated[List[Dict[str, Any]], append_to_list]
    risk_level: Optional[str]
    approval_request_id: Optional[str]
    approval_status: Optional[str]
    response_draft: Optional[str]
    verification_result: Optional[Dict[str, Any]]
    errors: Annotated[List[Dict[str, Any]], append_to_list]
