"""
Multi-Agent Orchestrator - Coordinates the workflow of type_solver, heap_solver, their verifiers, and refiner.

Workflow:
1. type_solver -> type_solver_verifier -> (if failed, refiner corrects, max 2 retries)
2. heap_solver -> heap_solver_verifier -> (if failed, refiner corrects, max 2 retries)
3. Return final result
"""

from typing import List, Dict, Optional, Any, Tuple
from langchain_openai import ChatOpenAI

from .type_solver_agent import TypeSolverAgent
from .type_solver_verifier import TypeSolverVerifier
from .heap_solver_agent import HeapSolverAgent
from .heap_solver_verifier import HeapSolverVerifier
from .refiner_agent import RefinerAgent
from .initializer_agent import InitializerAgent


class MultiAgentOrchestrator:
    """
    Coordinates the workflow of multiple agents.
    
    Workflow:
    1. type_solver solves type constraints
    2. type_solver_verifier validates results
    3. If failed, use refiner to correct and retry (max 2 times)
    4. heap_solver solves heap constraints based on type_solver results
    5. heap_solver_verifier validates results
    6. If failed, use refiner to correct and retry (max 2 times)
    7. Return final result
    """
    
    def __init__(
        self,
        llm: ChatOpenAI,
        max_retries: int = 2,
    ):
        """
        Initialize MultiAgentOrchestrator.
        
        Args:
            llm: ChatOpenAI instance (for type_solver and heap_solver)
            max_retries: Maximum number of retries (default: 2)
        """
        # Create agents
        self.type_solver = TypeSolverAgent(llm)
        self.type_solver_verifier = TypeSolverVerifier()
        self.heap_solver = HeapSolverAgent(llm)
        self.heap_solver_verifier = HeapSolverVerifier()
        self.initializer = InitializerAgent(llm)
        
        # Refiner uses temperature=0 for precise corrections
        refiner_llm = ChatOpenAI(
            model=llm.model_name,
            api_key=llm.openai_api_key,
            base_url=llm.openai_api_base if hasattr(llm, 'openai_api_base') else None,
            temperature=0.0,
            max_tokens=llm.max_tokens,
        )
        self.refiner = RefinerAgent(refiner_llm)
        
        self.max_retries = max_retries
        self.conversation_logs: List[Dict[str, Any]] = []
    
    def solve(
        self,
        constraints: List[str],
        type_hierarchy: Optional[Dict[str, str]] = None,
        variable_static_type: Optional[Dict[str, str]] = None,
        heap_state: Optional[Dict[str, Any]] = None,
        source_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Main orchestration flow.
        
        Args:
            constraints: List of constraints
            type_hierarchy: Type hierarchy information
            variable_static_type: Static types of variables
            heap_state: Heap state information
            source_context: Source code context
        
        Returns:
            Final solving result dictionary
        """
        self.conversation_logs = []
        
        # Step 1: type_solver solves
        type_solver_output, type_solver_output_raw = self._solve_type_constraints(
            constraints=constraints,
            variable_static_type=variable_static_type,
            type_hierarchy=type_hierarchy,
            source_context=source_context,
        )

        # Defensive: downstream logic assumes dict outputs.
        if type_solver_output is not None and not isinstance(type_solver_output, dict):
            return {
                "result": "UNKNOWN",
                "error": f"type_solver returned non-object JSON: {type(type_solver_output)}",
            }
        
        # If type_solver returns UNSAT or UNKNOWN, return directly
        if type_solver_output and type_solver_output.get("result") in ["UNSAT", "UNKNOWN"]:
            return {
                "result": type_solver_output.get("result"),
                "valuation": type_solver_output.get("valuation", []),
            }
        
        # If type_solver fails, return UNKNOWN
        if not type_solver_output:
            return {
                "result": "UNKNOWN",
                "error": "type_solver solving failed",
            }
        
        # Step 2: heap_solver solves
        heap_solver_output = self._solve_heap_constraints(
            constraints=constraints,
            source_context=source_context,
            heap_state=heap_state,
            type_solver_output=type_solver_output,
        )

        # Defensive: downstream logic assumes dict outputs.
        if heap_solver_output is not None and not isinstance(heap_solver_output, dict):
            return {
                "result": "UNKNOWN",
                "error": f"heap_solver returned non-object JSON: {type(heap_solver_output)}",
            }
        
        # Return final result, and if SAT, append initialization code via initializer agent
        if heap_solver_output:
            final_result = {
                "result": heap_solver_output.get("result", "UNKNOWN"),
                "valuation": heap_solver_output.get("valuation", []),
            }

            if final_result["result"] == "SAT":
                init_payload, init_raw, init_log = self.initializer.generate(
                    constraints=constraints,
                    heap_solver_output=heap_solver_output,
                )
                # Record initializer log
                if init_log:
                    self.conversation_logs.append(init_log)
                # Attach generated code (if any)
                if isinstance(init_payload, dict):
                    final_result["initialization_code"] = init_payload.get("initialization_code", "")
                    final_result["initialization_plan"] = init_payload.get("plan", {})

            return final_result
        else:
            return {
                "result": "UNKNOWN",
                "error": "heap_solver solving failed",
            }
    
    def _solve_type_constraints(
        self,
        constraints: List[str],
        variable_static_type: Optional[Dict[str, str]] = None,
        type_hierarchy: Optional[Dict[str, str]] = None,
        source_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[Dict], str]:
        """
        Solve type constraints, including validation and retry logic.
        
        Returns:
            Tuple of (type_solver_output, raw_output)
        """
        iteration = 0
        solver_output_raw = ""
        error_report = None
        
        while iteration <= self.max_retries:
            iteration += 1
            
            if iteration == 1:
                # First iteration: use type_solver
                solver_output, solver_output_raw, solver_log = self.type_solver.solve(
                    constraints=constraints,
                    variable_static_type=variable_static_type,
                    type_hierarchy=type_hierarchy,
                    source_context=source_context,
                )
                if solver_log:
                    solver_log["iteration"] = iteration
                    self.conversation_logs.append(solver_log)
            else:
                # Subsequent iterations: use refiner
                solver_output, solver_output_raw, refiner_log = self.refiner.refine_type_solver(
                    constraints=constraints,
                    solver_output_raw=solver_output_raw,
                    error_report=error_report,
                    variable_static_type=variable_static_type,
                    type_hierarchy=type_hierarchy,
                )
                if refiner_log:
                    refiner_log["iteration"] = iteration
                    self.conversation_logs.append(refiner_log)
            
            # Verify result
            error_report = self.type_solver_verifier.verify(
                constraints=constraints,
                type_solver_output=solver_output,
            )
            
            if error_report["is_well_formed"]:
                # Verification passed, return result
                return solver_output, solver_output_raw
            
            # Verification failed, check if should retry
            if iteration >= self.max_retries:
                # Max retries reached, return UNKNOWN
                return {
                    "result": "UNKNOWN",
                    "error": f"type_solver verification failed (retried {iteration} times)",
                }, solver_output_raw
        
        # Should not reach here
        return None, solver_output_raw
    
    def _solve_heap_constraints(
        self,
        constraints: List[str],
        source_context: Optional[Dict[str, Any]] = None,
        heap_state: Optional[Dict[str, Any]] = None,
        type_solver_output: Optional[Dict] = None,
    ) -> Optional[Dict]:
        """
        Solve heap constraints, including validation and retry logic.
        
        Returns:
            heap_solver_output
        """
        iteration = 0
        solver_output_raw = ""
        error_report = None
        
        while iteration <= self.max_retries:
            iteration += 1
            
            if iteration == 1:
                # First iteration: use heap_solver
                solver_output, solver_output_raw, solver_log = self.heap_solver.solve(
                    constraints=constraints,
                    source_context=source_context,
                    heap_state=heap_state,
                    type_solver_output=type_solver_output,
                )
                if solver_log:
                    solver_log["iteration"] = iteration
                    self.conversation_logs.append(solver_log)
            else:
                # Subsequent iterations: use refiner
                solver_output, solver_output_raw, refiner_log = self.refiner.refine_heap_solver(
                    constraints=constraints,
                    solver_output_raw=solver_output_raw,
                    error_report=error_report,
                    source_context=source_context,
                    heap_state=heap_state,
                    type_solver_output=type_solver_output,
                )
                if refiner_log:
                    refiner_log["iteration"] = iteration
                    self.conversation_logs.append(refiner_log)
            
            # Verify result
            error_report = self.heap_solver_verifier.verify(
                constraints=constraints,
                heap_solver_output=solver_output,
                type_solver_output=type_solver_output,
            )
            
            if error_report["is_well_formed"]:
                # Verification passed, return result
                return solver_output
            
            # Verification failed, check if should retry
            if iteration >= self.max_retries:
                # Max retries reached, return UNKNOWN
                return {
                    "result": "UNKNOWN",
                    "error": f"heap_solver verification failed (retried {iteration} times)",
                }
        
        # Should not reach here
        return None
