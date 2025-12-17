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

Configuration:
- Configure `OPENAI_API_KEY` and `LLM_MODEL` in `config.py`.
"""

from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import json
from datetime import datetime
import os
import asyncio
import logging

from langchain_openai import ChatOpenAI

from config import OPENAI_API_KEY, LLM_MODEL, BASE_URL
from logger import write_log
from agents import MultiAgentOrchestrator

# Configure logger with more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI()


class SolveRequest(BaseModel):
    constraints: List[str]
    type_hierarchy: Optional[Dict[str, str]] = None
    variable_static_type: Optional[Dict[str, str]] = None
    heap_state: Optional[Dict[str, Any]] = None
    source_context: Optional[Dict[str, Any]] = None
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
    """
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
    
    llm = ChatOpenAI(**llm_kwargs)
    logger.info(f"[INIT] LLM initialized - model: {model}, temperature: {llm_kwargs['temperature']}, max_tokens: {llm_kwargs['max_tokens']}")
    
    # Run multi-agent orchestrator in a thread pool to avoid blocking the event loop
    conversation_logs = None
    try:
        logger.info(f"[ORCHESTRATOR] Starting multi-agent orchestrator (max_retries=2)")
        orchestrator = MultiAgentOrchestrator(llm=llm, max_retries=2)
        
        # Use asyncio.to_thread() to run the synchronous solve() in a thread pool
        # This allows the event loop to remain responsive to signals like SIGINT
        logger.info(f"[PROCESSING] Submitting solve task to thread pool...")
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
