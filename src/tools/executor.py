from typing import Callable, Any
from src.tools.circuit_breaker import CircuitBreaker
from src.tools.retry import with_retry

class ToolExecutor:
    """Executes a tool with resilience (retries and circuit breaking)."""
    
    def __init__(self, name: str):
        self.name = name
        self.circuit_breaker = CircuitBreaker()

    def execute(self, func: Callable, *args, **kwargs) -> Any:
        def wrapped_call():
            return func(*args, **kwargs)
            
        # First, wrap with circuit breaker
        def cb_call():
            return self.circuit_breaker.call(wrapped_call)
            
        # Then, apply retry logic over the circuit breaker call
        return with_retry(cb_call)

# Global registry of executors per tool
_executors = {}

def execute_tool(tool_name: str, func: Callable, *args, **kwargs) -> Any:
    if tool_name not in _executors:
        _executors[tool_name] = ToolExecutor(tool_name)
    
    executor = _executors[tool_name]
    return executor.execute(func, *args, **kwargs)
