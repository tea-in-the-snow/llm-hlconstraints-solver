"""
Multi-Agent Constraint Solver using LLM (FastAPI + LangChain).

Architecture:
- type_solver: Focuses on solving type-related constraints
- type_solver_verifier: Validates type_solver results (without using LLM)
- heap_solver: Focuses on solving heap-related constraints
- heap_solver_verifier: Validates heap_solver results (without using LLM)
- refiner: Corrects errors detected by verifiers (using LLM)

Workflow:
  type_solver -> type_solver_verifier -> (Pass) -> heap_solver -> heap_solver_verifier -> (Pass) -> Return
  (Fail) -> refiner -> retry (max 2 retries)

Endpoints:
- POST /solve : Constraint solving with multi-agent workflow
              Input: {"constraints": [...], "type_hierarchy": {...}, "variable_static_type": {...}, "heap_state": {...}, "source_context": {...}, "max_tokens": 512, "temperature": 0.0}
              Output: {"result": "SAT|UNSAT|UNKNOWN", "valuation": [...]}
- POST /initialize : Generate Java initialization code for method parameters (no constraints required)
              Input: {"parameter_types": [{"name": "p0", "type": "java.lang.Appendable"}, ...], "max_tokens": 512, "temperature": 0.0}
              Output: {"initialization_code": "...Java code...", "variable_assignments": {...}, "type_plans": {...}}

Configuration:
- Configure `OPENAI_API_KEY` and `LLM_MODEL` in `config.py`.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import json
from datetime import datetime
import os
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
import multiprocessing

from langchain_openai import ChatOpenAI

from config import (
    OPENAI_API_KEY, LLM_MODEL, BASE_URL, MAX_CONCURRENT_REQUESTS, THREAD_POOL_SIZE,
    API_REQUESTS_PER_MINUTE, API_REQUESTS_PER_SECOND, API_MAX_RETRIES, API_RATE_LIMITING_ENABLED
)
from logger import write_log
from agents import MultiAgentOrchestrator
from agents.api_rate_limiter import APIRateLimiter, set_rate_limiter
from agents.initial_value_agent import InitialValueAgent

# Configure logger with more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI()

# Initialize concurrency control
# Semaphore for limiting concurrent requests (0 = unlimited)
if MAX_CONCURRENT_REQUESTS > 0:
    request_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    logger.info(f"[CONFIG] Max concurrent requests: {MAX_CONCURRENT_REQUESTS}")
else:
    request_semaphore = None
    logger.info(f"[CONFIG] Concurrent requests: unlimited")

# Custom thread pool executor for asyncio.to_thread
if THREAD_POOL_SIZE > 0:
    thread_pool_executor = ThreadPoolExecutor(max_workers=THREAD_POOL_SIZE, thread_name_prefix="solve-worker")
    logger.info(f"[CONFIG] Custom thread pool size: {THREAD_POOL_SIZE}")
else:
    thread_pool_executor = None
    default_pool_size = min(32, (multiprocessing.cpu_count() or 1) + 4)
    logger.info(f"[CONFIG] Using default thread pool size: {default_pool_size}")

@app.on_event("startup")
async def startup_event():
    """Initialize resources on startup."""
    logger.info("[STARTUP] Application starting up...")
    if thread_pool_executor:
        logger.info(f"[STARTUP] Custom thread pool executor initialized with {THREAD_POOL_SIZE} workers")
    
    # Initialize API rate limiter if enabled
    if API_RATE_LIMITING_ENABLED and API_REQUESTS_PER_MINUTE > 0:
        rate_limiter = APIRateLimiter(
            requests_per_minute=API_REQUESTS_PER_MINUTE,
            requests_per_second=API_REQUESTS_PER_SECOND if API_REQUESTS_PER_SECOND > 0 else None,
            max_retries=API_MAX_RETRIES,
        )
        set_rate_limiter(rate_limiter)
        logger.info(
            f"[STARTUP] API rate limiter enabled: {API_REQUESTS_PER_MINUTE} req/min, "
            f"{API_REQUESTS_PER_SECOND or 'unlimited'} req/sec, max_retries={API_MAX_RETRIES}"
        )
    else:
        logger.info("[STARTUP] API rate limiting disabled")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup resources on shutdown."""
    logger.info("[SHUTDOWN] Application shutting down...")
    if thread_pool_executor:
        thread_pool_executor.shutdown(wait=True)
        logger.info("[SHUTDOWN] Thread pool executor shut down")


class SolveRequest(BaseModel):
    constraints: List[str]
    type_hierarchy: Optional[Dict[str, str]] = None
    variable_static_type: Optional[Dict[str, str]] = None
    heap_state: Optional[Dict[str, Any]] = None
    source_context: Optional[Dict[str, Any]] = None
    max_tokens: Optional[int] = 512
    temperature: Optional[float] = 0.0


class GenerateInitialValuesRequest(BaseModel):
    """Request model for generating initial values for method parameters."""
    parameter_types: List[Dict[str, str]]  # List of {"name": "p0", "type": "java.lang.Appendable"}
    max_tokens: Optional[int] = 512
    temperature: Optional[float] = 0.0


@app.post("/solve")
async def solve(req: SolveRequest):
    """
    Multi-Agent Constraint Solver Endpoint.
    
    Workflow:
    1. type_solver: Solve type-related constraints
    2. type_solver_verifier: Validate type solving results
    3. heap_solver: Solve heap-related constraints based on type results
    4. heap_solver_verifier: Validate heap solving results
    5. If validation fails, use refiner to correct and retry (max 2 times)
    
    Concurrency Control:
    - Uses semaphore to limit concurrent requests if MAX_CONCURRENT_REQUESTS > 0
    - Uses custom thread pool if THREAD_POOL_SIZE > 0
    """
    # Acquire semaphore if concurrency limit is set
    if request_semaphore:
        await request_semaphore.acquire()
        try:
            return await _solve_internal(req)
        finally:
            request_semaphore.release()
    else:
        return await _solve_internal(req)


async def _solve_internal(req: SolveRequest):
    """Internal solve implementation."""
    started_time = datetime.now()
    
    # Log incoming request
    logger.info(f"[RECEIVE] /solve request")
    logger.info(f"   Constraints: {req.constraints}")
    if req.type_hierarchy:
        logger.info(f"   Type hierarchy provided: {len(req.type_hierarchy)} types")
    if req.variable_static_type:
        logger.info(f"   Variable static type provided: {len(req.variable_static_type)} variables")
    if req.heap_state:
        logger.info(f"   Heap state provided")
    if req.source_context:
        logger.info(f"   Source context provided")
    
    # Prepare request data for logging
    request_data = {
        "constraints": req.constraints,
        "type_hierarchy": req.type_hierarchy,
        "variable_static_type": req.variable_static_type,
        "heap_state": req.heap_state,
        "source_context": req.source_context,
    }
    
    # Validate API key
    if not OPENAI_API_KEY:
        logger.error("[ERROR] API Key not configured")
        response_data = {"result": "UNKNOWN", "error": "OPENAI_API_KEY not configured in config.py"}
        ended_time = datetime.now()
        write_log(
            request=request_data,
            response=response_data,
            started_time=started_time,
            ended_time=ended_time,
            conversation_logs=None
        )
        return response_data
    
    logger.info(f"[OK] API Key validated, using model: {LLM_MODEL}")
    
    # Initialize LLM
    model = LLM_MODEL
    llm_kwargs = {
        "temperature": req.temperature or 0.0,
        "max_tokens": req.max_tokens or 512,
        "model": model,
        "api_key": OPENAI_API_KEY,
    }
    if BASE_URL:
        llm_kwargs["base_url"] = BASE_URL
    
    from agents.llm_wrapper import wrap_llm_with_rate_limiting
    
    base_llm = ChatOpenAI(**llm_kwargs)
    llm = wrap_llm_with_rate_limiting(base_llm)
    logger.info(f"[INIT] LLM initialized - model: {model}, temperature: {llm_kwargs['temperature']}, max_tokens: {llm_kwargs['max_tokens']}")
    
    # Run multi-agent orchestrator in a thread pool to avoid blocking the event loop
    conversation_logs = None
    try:
        logger.info(f"[ORCHESTRATOR] Starting multi-agent orchestrator (max_retries=2)")
        orchestrator = MultiAgentOrchestrator(llm=llm, max_retries=2)
        
        # Use asyncio.to_thread() to run the synchronous solve() in a thread pool
        # This allows the event loop to remain responsive to signals like SIGINT
        logger.info(f"[PROCESSING] Submitting solve task to thread pool...")
        if thread_pool_executor:
            # Use custom thread pool executor
            loop = asyncio.get_event_loop()
            response_data = await loop.run_in_executor(
                thread_pool_executor,
                orchestrator.solve,
                req.constraints,
                req.type_hierarchy,
                req.variable_static_type,
                req.heap_state,
                req.source_context,
            )
        else:
            # Use default thread pool
            response_data = await asyncio.to_thread(
                orchestrator.solve,
                req.constraints,
                req.type_hierarchy,
                req.variable_static_type,
                req.heap_state,
                req.source_context,
            )
        
        logger.info(f"[COMPLETE] Solve completed - result: {response_data.get('result')}")
        conversation_logs = orchestrator.conversation_logs
        
    except asyncio.CancelledError:
        # Handle cancellation gracefully (e.g., when SIGINT is received)
        logger.warning(f"[CANCELLED] Request was cancelled by user")
        response_data = {"result": "UNKNOWN", "error": "Request was cancelled"}
        if 'orchestrator' in locals():
            conversation_logs = getattr(orchestrator, "conversation_logs", None)
        raise
    except Exception as e:
        logger.error(f"[Error] Error during solving: {str(e)}")
        response_data = {"result": "UNKNOWN", "error": str(e)}
        if 'orchestrator' in locals():
            conversation_logs = getattr(orchestrator, "conversation_logs", None)
    
    ended_time = datetime.now()
    duration = (ended_time - started_time).total_seconds()
    
    # Write log
    logger.info(f"[LOGGING] Writing logs (duration: {duration:.2f}s)")
    write_log(
        request=request_data,
        response=response_data,
        started_time=started_time,
        ended_time=ended_time,
        conversation_logs=conversation_logs,
    )
    
    logger.info(f"[SUCCESS] Request completed successfully\n")
    
    return response_data


@app.post("/initialize")
async def initialize(req: GenerateInitialValuesRequest):
    """
    Generate Java initialization code for method parameters.
    
    This endpoint generates valid initialization code for method parameters
    without requiring constraints. It can be used to generate initial test inputs.
    
    Input:
    - parameter_types: List of parameter information, each with "name" and "type"
      Example: [{"name": "p0", "type": "java.lang.Appendable"}, ...]
    - max_tokens (optional, default 512)
    - temperature (optional, default 0.0)
    
    Output:
    - initialization_code: Java code string with variable initializations
    - variable_assignments: Map from parameter name to variable name
    - type_plans: Type information collected for each parameter
    """
    started_time = datetime.now()
    
    logger.info(f"[RECEIVE] /initialize request")
    logger.info(f"   Parameters: {len(req.parameter_types)} parameters")
    for param in req.parameter_types:
        logger.info(f"     {param.get('name', '?')}: {param.get('type', '?')}")
    
    request_data = {
        "parameter_types": req.parameter_types,
        "max_tokens": req.max_tokens,
        "temperature": req.temperature,
    }
    
    # Validate API key
    if not OPENAI_API_KEY:
        logger.error("[ERROR] API Key not configured")
        response_data = {
            "initialization_code": "",
            "variable_assignments": {},
            "error": "OPENAI_API_KEY not configured in config.py"
        }
        ended_time = datetime.now()
        write_log(
            request=request_data,
            response=response_data,
            started_time=started_time,
            ended_time=ended_time,
            conversation_logs=None
        )
        return response_data
    
    logger.info(f"[OK] API Key validated, using model: {LLM_MODEL}")
    
    # Initialize LLM
    model = LLM_MODEL
    llm_kwargs = {
        "temperature": req.temperature or 0.0,
        "max_tokens": req.max_tokens or 512,
        "model": model,
        "api_key": OPENAI_API_KEY,
    }
    if BASE_URL:
        llm_kwargs["base_url"] = BASE_URL
    
    from agents.llm_wrapper import wrap_llm_with_rate_limiting
    
    base_llm = ChatOpenAI(**llm_kwargs)
    llm = wrap_llm_with_rate_limiting(base_llm)
    logger.info(f"[INIT] LLM initialized - model: {model}, temperature: {req.temperature}")
    
    # Initialize InitialValueAgent
    agent = InitialValueAgent(llm)
    
    # Generate initialization code
    try:
        result, raw_output, log_entry = agent.generate(req.parameter_types)
        
        ended_time = datetime.now()
        duration = (ended_time - started_time).total_seconds()
        
        logger.info(f"[OK] Generated initialization code in {duration:.2f}s")
        logger.info(f"   Code length: {len(result.get('initialization_code', ''))} chars")
        
        # Write log
        write_log(
            request=request_data,
            response=result,
            started_time=started_time,
            ended_time=ended_time,
            conversation_logs=[log_entry] if log_entry else None
        )
        
        return result
    except Exception as e:
        logger.error(f"[ERROR] Failed to generate initial values: {e}", exc_info=True)
        response_data = {
            "initialization_code": "",
            "variable_assignments": {},
            "error": str(e)
        }
        ended_time = datetime.now()
        write_log(
            request=request_data,
            response=response_data,
            started_time=started_time,
            ended_time=ended_time,
            conversation_logs=None
        )
    return response_data
