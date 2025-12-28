"""
Wrapper for LLM calls with rate limiting support.

Provides a synchronous wrapper for rate-limited LLM API calls.
"""

import asyncio
import logging
from typing import Any, Callable, Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage

from .api_rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)


class RateLimitedLLM:
    """
    Wrapper around ChatOpenAI that adds rate limiting.
    
    This wrapper intercepts LLM calls and applies rate limiting
    before making the actual API call.
    """
    
    def __init__(self, llm: ChatOpenAI):
        """
        Initialize RateLimitedLLM wrapper.
        
        Args:
            llm: ChatOpenAI instance to wrap
        """
        self.llm = llm
        self.rate_limiter = get_rate_limiter()
    
    def invoke(self, messages: list[BaseMessage], **kwargs) -> Any:
        """
        Invoke LLM with rate limiting.
        
        Args:
            messages: List of messages to send
            **kwargs: Additional arguments for LLM
            
        Returns:
            LLM response
        """
        if self.rate_limiter:
            # Use rate limiter's call_with_retry
            # Since agents are synchronous, we need to run async code
            try:
                # Try to get existing event loop
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If loop is running, we can't use it - use thread pool
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(
                            asyncio.run,
                            self._invoke_with_rate_limit(messages, **kwargs)
                        )
                        return future.result()
                return loop.run_until_complete(
                    self._invoke_with_rate_limit(messages, **kwargs)
                )
            except RuntimeError:
                # No event loop, create a new one
                return asyncio.run(
                    self._invoke_with_rate_limit(messages, **kwargs)
                )
        else:
            # No rate limiter, call directly
            return self.llm.invoke(messages, **kwargs)
    
    async def _invoke_with_rate_limit(
        self,
        messages: list[BaseMessage],
        **kwargs
    ) -> Any:
        """
        Async wrapper for rate-limited invoke.
        
        Args:
            messages: List of messages to send
            **kwargs: Additional arguments for LLM
            
        Returns:
            LLM response
        """
        if self.rate_limiter:
            # Wrap the synchronous invoke in an async function
            def _call_llm():
                return self.llm.invoke(messages, **kwargs)
            
            return await self.rate_limiter.call_with_retry(_call_llm)
        else:
            # No rate limiter, call directly
            return self.llm.invoke(messages, **kwargs)
    
    def __getattr__(self, name: str) -> Any:
        """
        Delegate all other attributes to the wrapped LLM.
        
        This allows RateLimitedLLM to be a drop-in replacement for ChatOpenAI.
        """
        return getattr(self.llm, name)


def wrap_llm_with_rate_limiting(llm: ChatOpenAI) -> ChatOpenAI:
    """
    Wrap an LLM instance with rate limiting.
    
    Args:
        llm: ChatOpenAI instance to wrap
        
    Returns:
        Wrapped LLM instance (or original if rate limiting disabled)
    """
    rate_limiter = get_rate_limiter()
    if rate_limiter:
        return RateLimitedLLM(llm)
    else:
        return llm

