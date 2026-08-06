import time
import random
import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)

def with_retry(
    func: Callable,
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 10.0,
    backoff_factor: float = 2.0,
    jitter: bool = True
) -> Any:
    """Executes a function with exponential backoff retry logic."""
    attempt = 0
    delay = initial_delay

    while attempt < max_attempts:
        try:
            return func()
        except Exception as e:
            attempt += 1
            if attempt >= max_attempts:
                logger.error(f"Function {func.__name__} failed after {max_attempts} attempts.")
                raise e
            
            if jitter:
                # Add random jitter between 0 and delay
                sleep_time = random.uniform(0, delay)
            else:
                sleep_time = delay
                
            logger.warning(f"Attempt {attempt} failed. Retrying in {sleep_time:.2f}s...")
            time.sleep(sleep_time)
            
            # Exponential backoff
            delay = min(delay * backoff_factor, max_delay)
