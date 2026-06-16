import asyncio
import time
import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Callable, Coroutine, Dict, Optional, TypeVar

import httpx

logger = logging.getLogger(__name__)

T = TypeVar("T")

class Priority(IntEnum):
    HIGH = 0     # Direct user requests
    MEDIUM = 1   # Important background tasks
    LOW = 2      # Regular background cache warming

@dataclass(order=True)
class QueuedRequest:
    priority: Priority
    timestamp: float = field(compare=True)
    func: Callable[..., Any] = field(compare=False)
    args: tuple = field(default_factory=tuple, compare=False)
    kwargs: dict = field(default_factory=dict, compare=False)
    future: asyncio.Future = field(default_factory=lambda: asyncio.Future(), compare=False)

class RequestQueue:
    def __init__(self, limit: Optional[int] = None, period: int = 900):
        self.limit = limit          # Optional internal limit
        self.period = period        # 15 minutes (900 seconds)
        self.queue: asyncio.PriorityQueue[QueuedRequest] = asyncio.PriorityQueue()
        self.tokens = float(limit) if limit else 1.0
        self.last_update = time.monotonic()
        self._worker_task: Optional[asyncio.Task] = None
        
        # Adaptive throttling state
        self.remaining: Optional[int] = None
        self.reset_at: float = time.time() + period
        
    async def add_request(
        self, 
        priority: Priority, 
        func: Callable[..., Any], 
        *args: Any, 
        **kwargs: Any
    ) -> T:
        req = QueuedRequest(
            priority=priority, 
            timestamp=time.time(),
            func=func, 
            args=args, 
            kwargs=kwargs
        )
        await self.queue.put(req)
        return await req.future

    def _replenish_tokens(self):
        if not self.limit:
            self.tokens = 1.0
            return

        now = time.monotonic()
        elapsed = now - self.last_update
        # Rate = limit / period per second
        replenishment = elapsed * (self.limit / self.period)
        self.tokens = min(self.limit, self.tokens + replenishment)
        self.last_update = now

    async def _worker(self):
        while True:
            # 1. Internal Rate Limiting (Optional)
            if self.limit:
                self._replenish_tokens()
                if self.tokens < 1:
                    wait_time = (1 - self.tokens) / (self.limit / self.period)
                    await asyncio.sleep(max(0.1, wait_time))
                    continue
            
            # 2. Adaptive Throttling (GitHub headers)
            # If we know our remaining quota is very low, wait for reset
            if self.remaining is not None and self.remaining <= 5:
                now = time.time()
                if now < self.reset_at:
                    wait_time = self.reset_at - now + 1 # Add 1s buffer
                    logger.warning(f"Adaptive throttling: GitHub rate limit exhausted. Waiting {wait_time:.2f}s")
                    await asyncio.sleep(min(wait_time, 30)) # Wait in chunks
                    continue

            # 3. Process Request
            req: QueuedRequest = await self.queue.get()
            if self.limit:
                self.tokens -= 1
            
            try:
                result = await req.func(*req.args, **req.kwargs)
                if not req.future.done():
                    req.future.set_result(result)
                
                # Update adaptive throttling if result is an httpx Response or has headers
                if hasattr(result, 'headers'):
                    self._update_limits(result.headers)
                    
            except Exception as e:
                if not req.future.done():
                    req.future.set_exception(e)
            finally:
                self.queue.task_done()
                # Tiny breather to prevent tight-looping if no limit set
                if not self.limit:
                    await asyncio.sleep(0.01)

    def _update_limits(self, headers: Any):
        # GitHub specific rate limit headers
        remaining = headers.get("X-RateLimit-Remaining")
        reset = headers.get("X-RateLimit-Reset")
        
        if remaining is not None:
            try:
                self.remaining = int(remaining)
            except (ValueError, TypeError):
                pass
        if reset is not None:
            try:
                self.reset_at = float(reset)
            except (ValueError, TypeError):
                pass

    def start(self):
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._worker())

    async def stop(self):
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None

    def get_status(self):
        return {
            "queue_size": self.queue.qsize(),
            "tokens_available": round(self.tokens, 2) if self.limit else "unlimited",
            "github_remaining": self.remaining,
            "github_reset_at": self.reset_at,
            "limit": self.limit,
            "period": self.period
        }

# Global request queue - default to no internal limit, relying on adaptive throttling
request_queue = RequestQueue(limit=None)
