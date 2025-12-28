"""
API Rate Limiter and Retry Handler for LLM API calls.

Handles:
- Rate limiting to prevent 429 errors
- Exponential backoff retry for rate limit errors
- Request queuing for API key-based rate limiting
"""

import asyncio
import time
import logging
from typing import Callable, Any, Optional
from functools import wraps
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class APIRateLimiter:
    """
    Rate limiter for LLM API calls to prevent 429 (Too Many Requests) errors.
    
    Features:
    - Token bucket algorithm for rate limiting
    - Per-API-key rate limiting
    - Exponential backoff retry on 429 errors
    """
    
    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_second: Optional[int] = None,
        max_retries: int = 3,
        initial_backoff: float = 1.0,
        max_backoff: float = 60.0,
        backoff_multiplier: float = 2.0,
    ):
        """
        Initialize API Rate Limiter.
        
        Args:
            requests_per_minute: Maximum requests per minute (default: 60)
            requests_per_second: Maximum requests per second (None = no limit)
            max_retries: Maximum retry attempts for 429 errors (default: 3)
            initial_backoff: Initial backoff time in seconds (default: 1.0)
            max_backoff: Maximum backoff time in seconds (default: 60.0)
            backoff_multiplier: Backoff multiplier for exponential backoff (default: 2.0)
        """
        self.requests_per_minute = requests_per_minute
        self.requests_per_second = requests_per_second
        
        # Token bucket: track request timestamps
        self.request_timestamps: list = []
        self.lock = asyncio.Lock()
        
        # Retry configuration
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.backoff_multiplier = backoff_multiplier
        
        logger.info(
            f"[RATE_LIMITER] Initialized: {requests_per_minute} req/min, "
            f"{requests_per_second} req/sec (if set), max_retries={max_retries}"
        )
    
    async def acquire(self):
        """
        Acquire permission to make an API request (rate limiting).
        Blocks if rate limit would be exceeded.
        """
        async with self.lock:
            now = time.time()
            
            # Clean old timestamps (older than 1 minute)
            self.request_timestamps = [
                ts for ts in self.request_timestamps
                if now - ts < 60.0
            ]
            
            # Check per-minute limit
            if len(self.request_timestamps) >= self.requests_per_minute:
                # Calculate wait time until oldest request expires
                oldest_ts = min(self.request_timestamps)
                wait_time = 60.0 - (now - oldest_ts) + 0.1  # Add small buffer
                if wait_time > 0:
                    logger.warning(
                        f"[RATE_LIMITER] Rate limit reached ({len(self.request_timestamps)}/{self.requests_per_minute}), "
                        f"waiting {wait_time:.2f}s"
                    )
                    await asyncio.sleep(wait_time)
                    # Re-clean after waiting
                    now = time.time()
                    self.request_timestamps = [
                        ts for ts in self.request_timestamps
                        if now - ts < 60.0
                    ]
            
            # Check per-second limit if set
            if self.requests_per_second is not None:
                recent_requests = [
                    ts for ts in self.request_timestamps
                    if now - ts < 1.0
                ]
                if len(recent_requests) >= self.requests_per_second:
                    # Wait until oldest request in this second expires
                    oldest_ts = min(recent_requests)
                    wait_time = 1.0 - (now - oldest_ts) + 0.01  # Add small buffer
                    if wait_time > 0:
                        await asyncio.sleep(wait_time)
            
            # Record this request
            self.request_timestamps.append(time.time())
    
    def is_rate_limit_error(self, error: Exception) -> bool:
        """
        Check if an error is a rate limit error (429).
        
        Args:
            error: Exception to check
            
        Returns:
            True if error is a rate limit error
        """
        error_str = str(error).lower()
        error_type = type(error).__name__
        
        # Check for 429 status code
        if "429" in error_str or "rate limit" in error_str or "too many requests" in error_str:
            return True
        
        # Check for OpenAI/OpenAI-compatible API rate limit errors
        if hasattr(error, 'status_code') and error.status_code == 429:
            return True
        
        if hasattr(error, 'response'):
            if hasattr(error.response, 'status_code') and error.response.status_code == 429:
                return True
        
        return False
    
    async def call_with_retry(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Call a function with rate limiting and automatic retry on 429 errors.
        
        Args:
            func: Function to call (should be async or sync)
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
            
        Returns:
            Result of func call
            
        Raises:
            Exception: If all retries fail
        """
        backoff = self.initial_backoff
        
        for attempt in range(self.max_retries + 1):
            try:
                # Acquire rate limit permission
                await self.acquire()
                
                # Call the function
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                
                # Success - reset backoff for next potential error
                if attempt > 0:
                    logger.info(f"[RATE_LIMITER] Request succeeded after {attempt} retries")
                return result
                
            except Exception as e:
                # Check if it's a rate limit error
                if self.is_rate_limit_error(e) and attempt < self.max_retries:
                    wait_time = min(backoff, self.max_backoff)
                    logger.warning(
                        f"[RATE_LIMITER] Rate limit error (attempt {attempt + 1}/{self.max_retries + 1}): {str(e)}. "
                        f"Retrying after {wait_time:.2f}s"
                    )
                    await asyncio.sleep(wait_time)
                    backoff *= self.backoff_multiplier
                    continue
                else:
                    # Not a rate limit error, or max retries reached
                    raise


# Global rate limiter instance (can be configured per API key if needed)
_global_rate_limiter: Optional[APIRateLimiter] = None


def get_rate_limiter() -> Optional[APIRateLimiter]:
    """Get the global rate limiter instance."""
    return _global_rate_limiter


def set_rate_limiter(limiter: APIRateLimiter):
    """Set the global rate limiter instance."""
    global _global_rate_limiter
    _global_rate_limiter = limiter


def with_rate_limit(func: Callable) -> Callable:
    """
    Decorator to add rate limiting and retry to a function.
    
    Usage:
        @with_rate_limit
        async def my_api_call(...):
            ...
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        limiter = get_rate_limiter()
        if limiter:
            return await limiter.call_with_retry(func, *args, **kwargs)
        else:
            # No rate limiter configured, call directly
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
    
    return wrapper

