"""
Multi-Agent System for Constraint Solving.

This package provides a modular multi-agent architecture for solving
high-level Java constraints using LLMs.

Architecture:
- TypeSolverAgent: Focuses on solving type-related constraints
- TypeSolverVerifier: Validates type_solver results (without using LLM)
- HeapSolverAgent: Focuses on solving heap-related constraints
- HeapSolverVerifier: Validates heap_solver results (without using LLM)
- RefinerAgent: Corrects errors detected by verifiers (using LLM)
- MultiAgentOrchestrator: Coordinates the entire workflow

Usage:
    from agents import MultiAgentOrchestrator
    
    orchestrator = MultiAgentOrchestrator(llm=llm, max_retries=2)
    result = orchestrator.solve(constraints=[...])
"""

from .utils import extract_first_json
from .type_solver_agent import TypeSolverAgent
from .type_solver_verifier import TypeSolverVerifier
from .heap_solver_agent import HeapSolverAgent
from .heap_solver_verifier import HeapSolverVerifier
from .refiner_agent import RefinerAgent
from .orchestrator import MultiAgentOrchestrator

__all__ = [
    'extract_first_json',
    'TypeSolverAgent',
    'TypeSolverVerifier',
    'HeapSolverAgent',
    'HeapSolverVerifier',
    'RefinerAgent',
    'MultiAgentOrchestrator',
]

__version__ = '3.0.0'
