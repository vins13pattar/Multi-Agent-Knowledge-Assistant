from typing import Callable, Any
from src.tools.circuit_breaker import CircuitBreaker
from src.tools.retry import with_retry

# One circuit breaker per tool name, so a failing tool doesn't trip breakers
# for unrelated tools.
_circuit_breakers: dict[str, CircuitBreaker] = {}

def execute_tool(tool_name: str, func: Callable, *args, **kwargs) -> Any:
    """Executes a tool with resilience: retries wrapped around a per-tool circuit breaker."""
    if tool_name not in _circuit_breakers:
        _circuit_breakers[tool_name] = CircuitBreaker()
    breaker = _circuit_breakers[tool_name]

    return with_retry(lambda: breaker.call(lambda: func(*args, **kwargs)))
