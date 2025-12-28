"""
Multi-Agent Orchestrator - Coordinates the workflow of type_solver, heap_solver, their verifiers, and refiner.

Workflow:
1. type_solver -> type_solver_verifier -> (if failed, refiner corrects, max 2 retries)
2. heap_solver -> heap_solver_verifier -> (if failed, refiner corrects, max 2 retries)
3. initializer -> code_executor -> (if failed, refiner corrects code, max 2 retries)
4. Return final result
"""

from typing import List, Dict, Optional, Any, Tuple
from langchain_openai import ChatOpenAI

from .type_solver_agent import TypeSolverAgent
from .type_solver_verifier import TypeSolverVerifier
from .heap_solver_agent import HeapSolverAgent
from .heap_solver_verifier import HeapSolverVerifier
from .refiner_agent import RefinerAgent
from .initializer_agent import InitializerAgent
from .code_executor_agent import CodeExecutorAgent


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
    7. initializer generates Java initialization code
    8. code_executor compiles and executes the code
    9. If failed, use refiner to fix code and retry (max 2 times)
    10. Return final result
    """
    
    def __init__(
        self,
        llm: ChatOpenAI,
        max_retries: int = 2,
        classpath: str = "",
        jdk_home: Optional[str] = None,
    ):
        """
        Initialize MultiAgentOrchestrator.
        
        Args:
            llm: ChatOpenAI instance (for type_solver and heap_solver)
            max_retries: Maximum number of retries (default: 2)
            classpath: Classpath for code execution (colon-separated on Linux)
            jdk_home: Optional path to JDK installation
        """
        # Create agents
        self.type_solver = TypeSolverAgent(llm)
        self.type_solver_verifier = TypeSolverVerifier()
        self.heap_solver = HeapSolverAgent(llm)
        self.heap_solver_verifier = HeapSolverVerifier()
        self.initializer = InitializerAgent(llm)
        self.code_executor = CodeExecutorAgent(classpath=classpath, jdk_home=jdk_home)
        
        # Refiner uses temperature=0 for precise corrections
        from .llm_wrapper import wrap_llm_with_rate_limiting
        
        refiner_llm_base = ChatOpenAI(
            model=llm.model_name,
            api_key=llm.openai_api_key,
            base_url=llm.openai_api_base if hasattr(llm, 'openai_api_base') else None,
            temperature=0.0,
            max_tokens=llm.max_tokens,
        )
        refiner_llm = wrap_llm_with_rate_limiting(refiner_llm_base)
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
                    type_solver_output=type_solver_output,
                    variable_static_type=variable_static_type,
                )
                # Record initializer log
                if init_log:
                    self.conversation_logs.append(init_log)
                # Attach generated code (if any)
                if isinstance(init_payload, dict):
                    final_result["initialization_code"] = init_payload.get("initialization_code", "")
                    final_result["initialization_plan"] = init_payload.get("plan", {})
                    
                    # CRITICAL: Update valuation to include all initialized objects
                    # The initialization_plan may contain variables not in heap_solver output
                    # (e.g., method parameters added from variable_static_type)
                    # We need to add these to valuation so Java side can process them
                    final_result["valuation"] = self._merge_valuations_with_initialization_plan(
                        heap_solver_output.get("valuation", []),
                        init_payload.get("plan", {}),
                    )
                    
                    # Execute the generated code with retry logic using refiner
                    init_code = final_result.get("initialization_code", "")
                    if init_code:
                        exec_result = self._execute_code_with_retry(
                            java_code=init_code,
                            constraints=constraints,
                            initialization_plan=init_payload.get("plan", {}),
                            heap_solver_output=heap_solver_output,
                        )
                        
                        # Attach execution results
                        final_result["execution_success"] = exec_result.get("success", False)
                        raw_objects = exec_result.get("objects", [])
                        final_result["objects"] = raw_objects
                        final_result["initialization_code"] = exec_result.get("final_code", init_code)
                        
                        # Build mapping from symbolic references to objects
                        object_map = self._build_object_mapping(
                            raw_objects=raw_objects,
                            heap_solver_output=heap_solver_output,
                        )
                        final_result["object_mapping"] = object_map
                        
                        # Log execution details
                        exec_log = {
                            "agent": "code_executor",
                            "stage": "execute",
                            "success": exec_result.get("success", False),
                            "compile_output": exec_result.get("compile_output", ""),
                            "run_output": exec_result.get("run_output", ""),
                            "run_error": exec_result.get("run_error", ""),
                            "error": exec_result.get("error", ""),
                            "objects_count": len(exec_result.get("objects", [])),
                            "iterations": exec_result.get("iterations", 1),
                        }
                        self.conversation_logs.append(exec_log)

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
    
    def _execute_code_with_retry(
        self,
        java_code: str,
        constraints: Optional[List[str]] = None,
        initialization_plan: Optional[Dict[str, Any]] = None,
        heap_solver_output: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute Java code with retry logic using refiner when execution fails.
        
        Args:
            java_code: The Java code to execute
            constraints: Optional list of constraints (for refiner context)
            initialization_plan: Optional initialization plan (for refiner context)
            heap_solver_output: Optional heap solver output (for refiner context)
        
        Returns:
            Execution result dictionary with additional fields:
                - final_code: The final code that was executed (may be refined)
                - iterations: Number of execution attempts
        """
        iteration = 0
        current_code = java_code
        
        while iteration <= self.max_retries:
            iteration += 1
            
            # Execute the code
            exec_result = self.code_executor.compile_and_execute(current_code)
            
            if exec_result.get("success", False):
                # Execution succeeded, return result
                exec_result["final_code"] = current_code
                exec_result["iterations"] = iteration
                return exec_result
            
            # Execution failed, check if should retry
            if iteration >= self.max_retries:
                # Max retries reached, return failure result
                exec_result["final_code"] = current_code
                exec_result["iterations"] = iteration
                return exec_result
            
            # Use refiner to fix the code
            fixed_code, refiner_raw, refiner_log = self.refiner.refine_code_executor(
                java_code=current_code,
                compile_output=exec_result.get("compile_output", ""),
                run_error=exec_result.get("run_error", ""),
                error=exec_result.get("error", ""),
                constraints=constraints,
                initialization_plan=initialization_plan,
                heap_solver_output=heap_solver_output,
            )
            
            # Record refiner log
            if refiner_log:
                refiner_log["iteration"] = iteration
                self.conversation_logs.append(refiner_log)
            
            # Update current_code for next iteration
            current_code = fixed_code
        
        # Should not reach here
        exec_result = {
            "success": False,
            "error": "Unexpected error in _execute_code_with_retry",
            "final_code": current_code,
            "iterations": iteration,
        }
        return exec_result
    
    def _merge_valuations_with_initialization_plan(
        self,
        heap_valuation: List[Dict[str, Any]],
        initialization_plan: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Merge heap_solver valuation with variables from initialization_plan.
        
        This ensures that all initialized objects (including those added from variable_static_type)
        are included in the final valuation, even if they weren't in heap_solver output.
        
        Args:
            heap_valuation: Original valuation from heap_solver
            initialization_plan: Initialization plan containing all objects to be initialized
        
        Returns:
            Merged valuation list
        """
        # Start with heap_solver valuation
        merged = list(heap_valuation) if heap_valuation else []
        
        # Build a set of variables already in heap valuation
        existing_vars = set()
        for entry in merged:
            if isinstance(entry, dict) and "variable" in entry:
                existing_vars.add(entry["variable"])
        
        # Add variables from initialization_plan that are not in heap valuation
        objects = initialization_plan.get("objects", []) if isinstance(initialization_plan, dict) else []
        next_ref_id = len(merged) + 1  # Start reference IDs after existing ones
        
        for obj in objects:
            if isinstance(obj, dict):
                var_name = obj.get("variable")
                if var_name and var_name not in existing_vars:
                    # Add this variable to valuation
                    merged.append({
                        "variable": var_name,
                        "type": obj.get("type", "Ljava/lang/Object;"),
                        "newObject": obj.get("newObject", True),
                        "trueRef": True,
                        "reference": next_ref_id,
                    })
                    existing_vars.add(var_name)
                    next_ref_id += 1
        
        return merged
    
    def _build_object_mapping(
        self,
        raw_objects: List[Dict[str, Any]],
        heap_solver_output: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Build a mapping from symbolic references (constraints variables) to executed objects.
        
        Args:
            raw_objects: List of objects returned from code execution
            heap_solver_output: Heap solver output containing valuation with variable names
        
        Returns:
            Dictionary mapping variable names to their corresponding objects
        """
        mapping: Dict[str, Any] = {}
        
        # Extract variable names from heap_solver valuation
        valuations = heap_solver_output.get("valuation", []) if isinstance(heap_solver_output, dict) else []
        variable_to_ref: Dict[str, str] = {}
        for entry in valuations:
            if isinstance(entry, dict):
                var = entry.get("variable")
                if var:
                    variable_to_ref[var] = var
        
        # Process raw objects - they may be in new format (with "variable" field) or legacy format
        for obj in raw_objects:
            if isinstance(obj, dict):
                if "variable" in obj:
                    # New format: object has variable name explicitly
                    var_name = obj["variable"]
                    obj_data = obj.get("object", obj)
                    mapping[var_name] = obj_data
                else:
                    # Legacy format: try to match by position or other heuristics
                    # For now, we'll try to match by order with valuation
                    pass
        
        # If we have objects but no explicit variable mapping, try to match by order
        # This handles legacy format where objects are returned without variable names
        if not mapping and raw_objects:
            root_variables = [
                entry.get("variable")
                for entry in valuations
                if isinstance(entry, dict) and "." not in entry.get("variable", "")
            ]
            for i, obj in enumerate(raw_objects):
                if i < len(root_variables):
                    var_name = root_variables[i]
                    if isinstance(obj, dict) and "variable" in obj:
                        # Use the object data, not the wrapper
                        mapping[var_name] = obj.get("object", obj)
                    else:
                        mapping[var_name] = obj
        
        return mapping
