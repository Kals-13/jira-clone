import logging
import time
from enum import Enum
from typing import Callable, Any

logger = logging.getLogger("jiralite.resilience")

class BreakerState(Enum):
    CLOSED = "CLOSED"  
    OPEN = "OPEN"      
    HALF_OPEN = "HALF_OPEN" 

class NotificationCircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 10.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = BreakerState.CLOSED
        self.failure_count = 0
        self.last_state_change = time.monotonic()
        self.dead_letter_queue: list[dict] = []

    def record_success(self):
        self.failure_count = 0
        self.state = BreakerState.CLOSED

    def record_failure(self, payload: dict):
        self.failure_count += 1
        self.dead_letter_queue.append(payload)
        logger.warning(f"Downstream microservice error recorded ({self.failure_count}/{self.failure_threshold})")
        
        if self.failure_count >= self.failure_threshold:
            self.state = BreakerState.OPEN
            self.last_state_change = time.monotonic()
            logger.error("Circuit Breaker flipped to OPEN state. External service bypassed.")

    async def call_external_service(self, func: Callable, payload: dict, *args, **kwargs) -> Any:
        current_time = time.monotonic()

        if self.state == BreakerState.OPEN:
            if current_time - self.last_state_change > self.recovery_timeout:
                self.state = BreakerState.HALF_OPEN
                logger.info("Circuit Breaker entered HALF-OPEN state. Testing connection...")
            else:
                logger.debug("Circuit Breaker blocking call. Queueing event to buffer.")
                self.dead_letter_queue.append(payload)
                return {"status": "queued", "circuit_breaker": "OPEN"}

        try:
            result = await func(payload, *args, **kwargs)
            
            if self.state == BreakerState.HALF_OPEN:
                self.record_success()
                logger.info("Circuit Breaker successfully recovered and closed!")
            return result

        except Exception as e:
            self.record_failure(payload)
            return {
                "status": "queued", 
                "error": str(e),
                "current_breaker_state": self.state.value
            }

notification_bus = NotificationCircuitBreaker(failure_threshold=5, recovery_timeout=5.0)
