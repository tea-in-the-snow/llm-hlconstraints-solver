"""
Refiner Agent - Corrects errors detected by verifiers (using LLM).

When type_solver_verifier or heap_solver_verifier detects invalid results,
this agent modifies and improves the output based on verifier feedback (using LLM).

When code_executor encounters compilation or runtime errors,
this agent fixes the Java code based on error messages (using LLM).
"""

from typing import List, Dict, Optional, Any, Tuple
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from .utils import extract_first_json


class RefinerAgent:
    """
    Corrects errors detected by verifiers.
    
    Input: Incorrect results and verifier output
    Output: Improved correct results
    """
    
    def __init__(self, llm: ChatOpenAI):
        """
        Initialize RefinerAgent.
        
        Args:
            llm: ChatOpenAI instance (should use temperature=0 for precise corrections)
        """
        self.llm = llm
    
    def refine_type_solver(
        self,
        constraints: List[str],
        solver_output_raw: str,
        error_report: Dict[str, Any],
        variable_static_type: Optional[Dict[str, str]] = None,
        type_hierarchy: Optional[Dict[str, str]] = None,
    ) -> Tuple[Optional[Dict], str, Dict[str, Any]]:
        """
        Refine type_solver output.
        
        Args:
            constraints: List of constraints
            solver_output_raw: Raw output from type_solver
            error_report: Error report from verifier
            variable_static_type: Static types of variables
            type_hierarchy: Type hierarchy information
        
        Returns:
            Tuple of (parsed_json_dict, raw_llm_output_string, conversation_log)
        """
        system_prompt = (
            "You are a constraint-solving assistant and error corrector. "
            "Your task is to fix the errors reported by type_solver_verifier.\n\n"
            "Given:\n"
            "1. Original constraints\n"
            "2. Previous (incorrect) type_solver output\n"
            "3. Specific errors reported by verifier\n\n"
            "Please:\n"
            "1. Understand why the previous output was wrong\n"
            "2. Fix these issues while respecting all original constraints\n"
            "3. Return a valid JSON object (SAT/UNSAT/UNKNOWN)\n\n"
            "For SAT valuation format:\n"
            "Each entry should contain: variable, type\n\n"
            "Important rules:\n"
            "1. MUST provide type information for ALL variable expressions that appear in constraints\n"
            "   (including simple variables and field access chains like 'head(ref).next(ref)')\n"
            "2. Do not invent new variable names that don't appear in constraints\n"
            "3. Types must conform to type hierarchy and static type constraints"
        )
        
        constraints_block = "\n".join(f"- {c}" for c in constraints)
        
        # Build variable static type information block
        static_type_block = ""
        if variable_static_type:
            static_type_block = "Variable Static Type Information:\n"
            for var_name, declared_type in variable_static_type.items():
                static_type_block += f"  {var_name}: {declared_type}\n"
            static_type_block += "\n"
        
        # Build type hierarchy information block
        type_hierarchy_block = ""
        if type_hierarchy:
            type_hierarchy_block = "Type Hierarchy Information:\n"
            for var_name, type_info in type_hierarchy.items():
                type_hierarchy_block += f"\nVariable: {var_name}\n{type_info}\n"
            type_hierarchy_block += "\n"
        
        # Format error report
        error_block = "Errors reported by Verifier:\n"
        if error_report.get("errors"):
            for error in error_report["errors"]:
                error_block += f"- [{error.get('error_type')}] {error.get('location')}: {error.get('message')}\n"
        else:
            error_block += "No error details\n"
        error_block += "\n"
        
        human_prompt = (
            f"{static_type_block}"
            f"{type_hierarchy_block}"
            f"Constraints:\n{constraints_block}\n\n"
            f"Previous (incorrect) type_solver output:\n{solver_output_raw}\n\n"
            f"{error_block}"
            "Please provide a corrected JSON solution."
        )
        
        try:
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt),
            ])
            raw_output = response.content if hasattr(response, 'content') else str(response)
            
            parsed, _ = extract_first_json(raw_output)
            log_entry = {
                "agent": "refiner",
                "stage": "refine_type_solver",
                "system": system_prompt,
                "human": human_prompt,
                "response": raw_output,
            }
            return parsed, raw_output, log_entry
        except Exception as e:
            log_entry = {
                "agent": "refiner",
                "stage": "refine_type_solver",
                "system": system_prompt,
                "human": human_prompt,
                "response": "",
                "error": str(e),
            }
            return None, f"Error during Refiner invocation: {str(e)}", log_entry
    
    def refine_heap_solver(
        self,
        constraints: List[str],
        solver_output_raw: str,
        error_report: Dict[str, Any],
        source_context: Optional[Dict[str, Any]] = None,
        heap_state: Optional[Dict[str, Any]] = None,
        type_solver_output: Optional[Dict] = None,
    ) -> Tuple[Optional[Dict], str, Dict[str, Any]]:
        """
        Refine heap_solver output.
        
        Args:
            constraints: List of constraints
            solver_output_raw: Raw output from heap_solver
            error_report: Error report from verifier
            source_context: Source code context
            heap_state: Heap state information
            type_solver_output: type_solver output (must be respected)
        
        Returns:
            Tuple of (parsed_json_dict, raw_llm_output_string, conversation_log)
        """
        system_prompt = (
            "You are a constraint-solving assistant and error corrector. "
            "Your task is to fix the errors reported by heap_solver_verifier.\n\n"
            "Given:\n"
            "1. Original constraints\n"
            "2. type_solver output (must be respected, cannot change types)\n"
            "3. Previous (incorrect) heap_solver output\n"
            "4. Specific errors reported by verifier\n\n"
            "Please:\n"
            "1. Understand why the previous output was wrong\n"
            "2. Fix these issues while respecting all original constraints and type_solver results\n"
            "3. Return a valid JSON object (SAT/UNSAT/UNKNOWN)\n\n"
            "For SAT valuation format:\n"
            "Each entry should contain: variable, type, newObject, trueRef, reference\n\n"
            "Important rules:\n"
            "1. MUST include ALL variables that type_solver provided in your valuation\n"
            "   (including field access chains like 'head(ref).next(ref)')\n"
            "2. Do not invent new variable names that weren't in type_solver output\n"
            "3. Types must exactly match type_solver output\n"
            "4. If type_solver result is UNSAT, return UNSAT directly"
        )
        
        constraints_block = "\n".join(f"- {c}" for c in constraints)
        
        # Build type_solver output information block
        type_solver_block = ""
        if type_solver_output:
            type_solver_block = "Type Solver Results (must be respected):\n"
            type_solver_block += "```json\n"
            import json
            type_solver_block += json.dumps(type_solver_output, indent=2, ensure_ascii=False)
            type_solver_block += "\n```\n\n"
        else:
            type_solver_block = "Warning: No type_solver output available.\n\n"
        
        # Build source code context block
        source_context_block = ""
        if source_context:
            source_context_block = "Source Code Context:\n"
            if "method_name" in source_context:
                source_context_block += f"Method: {source_context['method_name']}\n"
            if "class_name" in source_context:
                source_context_block += f"Class: {source_context['class_name']}\n"
            source_context_block += "\n"
            if "method_source" in source_context and source_context["method_source"]:
                source_context_block += "\nMethod Source Code:\n```java\n"
                source_context_block += source_context["method_source"]
                source_context_block += "```\n\n"
            if "related_classes" in source_context and source_context["related_classes"]:
                source_context_block += "\nRelated Classes:\n"
                related = source_context["related_classes"]
                if isinstance(related, dict):
                    for class_name, class_source in related.items():
                        if class_source:
                            source_context_block += f"\nClass: {class_name}\n```java\n"
                            source_context_block += class_source
                            source_context_block += "```\n"
        
        # Build heap state information block
        heap_state_block = ""
        if heap_state:
            heap_state_block = "Heap State Information:\n"
            if "aliases" in heap_state and heap_state["aliases"]:
                heap_state_block += "Aliases:\n"
                for var_name, obj_ref in heap_state["aliases"].items():
                    heap_state_block += f"  {var_name} → {obj_ref}\n"
                heap_state_block += "\n"
        
        # Format error report
        error_block = "Errors reported by Verifier:\n"
        if error_report.get("errors"):
            for error in error_report["errors"]:
                error_block += f"- [{error.get('error_type')}] {error.get('location')}: {error.get('message')}\n"
        else:
            error_block += "No error details\n"
        error_block += "\n"
        
        human_prompt = (
            f"{type_solver_block}"
            f"{source_context_block}"
            f"{heap_state_block}"
            f"Constraints:\n{constraints_block}\n\n"
            f"Previous (incorrect) heap_solver output:\n{solver_output_raw}\n\n"
            f"{error_block}"
            "Please provide a corrected JSON solution."
        )
        
        try:
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt),
            ])
            raw_output = response.content if hasattr(response, 'content') else str(response)
            
            parsed, _ = extract_first_json(raw_output)
            log_entry = {
                "agent": "refiner",
                "stage": "refine_heap_solver",
                "system": system_prompt,
                "human": human_prompt,
                "response": raw_output,
            }
            return parsed, raw_output, log_entry
        except Exception as e:
            log_entry = {
                "agent": "refiner",
                "stage": "refine_heap_solver",
                "system": system_prompt,
                "human": human_prompt,
                "response": "",
                "error": str(e),
            }
            return None, f"Error during Refiner invocation: {str(e)}", log_entry
    
    def refine_code_executor(
        self,
        java_code: str,
        compile_output: str = "",
        run_error: str = "",
        error: str = "",
        constraints: Optional[List[str]] = None,
        initialization_plan: Optional[Dict[str, Any]] = None,
        heap_solver_output: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str, Dict[str, Any]]:
        """
        Refine Java code that failed to compile or execute.
        
        Args:
            java_code: The original Java code that failed
            compile_output: Compilation error output (stdout/stderr from javac)
            run_error: Runtime error output (stderr from java)
            error: General error message
            constraints: Optional list of constraints (for context)
            initialization_plan: Optional initialization plan (for context)
            heap_solver_output: Optional heap solver output (for context)
        
        Returns:
            Tuple of (fixed_java_code, raw_llm_output_string, conversation_log)
        """
        system_prompt = (
            "You are a Java code debugging and fixing assistant. "
            "Your task is to fix compilation or runtime errors in Java code.\n\n"
            "Given:\n"
            "1. Original Java code that failed to compile or execute\n"
            "2. Compilation errors (if any)\n"
            "3. Runtime errors (if any)\n"
            "4. Additional context (constraints, initialization plan, etc.)\n\n"
            "Please:\n"
            "1. Analyze the error messages carefully\n"
            "2. Identify the root cause of the problem\n"
            "3. Fix the code while preserving the original intent\n"
            "4. Ensure the fixed code includes all necessary imports\n"
            "5. Ensure the fixed code can compile and run successfully\n\n"
            "Important rules:\n"
            "1. Output ONLY the corrected Java code wrapped in triple backticks (```java ... ```)\n"
            "2. Do not add explanations outside the code block\n"
            "3. Preserve the structure and logic of the original code\n"
            "4. Make sure all imports are included\n"
            "5. Ensure the main method and JSON serialization logic are preserved\n"
            "6. When outputting objects, use the format: {\"variable\": \"<variable_name_from_plan>\", \"object\": <serialized_json>}\n"
            "   This allows mapping objects back to symbolic references in constraints.\n\n"
            "Special handling for Gson serialization errors:\n"
            "If you encounter Gson serialization errors related to complex types (e.g., DecimalFormat, "
            "NumberFormat, or other JDK internal classes that declare multiple JSON fields with the same name), "
            "you should use a custom Gson configuration to exclude these problematic types. "
            "Use GsonBuilder with ExclusionStrategy to skip serialization of problematic classes:\n"
            "- Import: com.google.gson.GsonBuilder, com.google.gson.ExclusionStrategy, com.google.gson.FieldAttributes\n"
            "- Create a Gson instance using: new GsonBuilder().setExclusionStrategies(new ExclusionStrategy() {...}).create()\n"
            "- In the ExclusionStrategy, skip classes that cause serialization issues (e.g., DecimalFormat, NumberFormat)\n"
            "- This allows the rest of the object graph to be serialized successfully"
        )
        
        # Build error information block
        error_block = "Error Information:\n"
        if error:
            error_block += f"General Error: {error}\n"
        if compile_output:
            error_block += f"\nCompilation Output:\n{compile_output}\n"
        if run_error:
            error_block += f"\nRuntime Error:\n{run_error}\n"
        if not error and not compile_output and not run_error:
            error_block += "No specific error details provided\n"
        error_block += "\n"
        
        # Build constraints block (optional)
        constraints_block = ""
        if constraints:
            constraints_block = "Constraints (for context):\n"
            constraints_block += "\n".join(f"- {c}" for c in constraints)
            constraints_block += "\n\n"
        
        # Build initialization plan block (optional)
        plan_block = ""
        if initialization_plan:
            plan_block = "Initialization Plan (for context):\n"
            import json
            plan_block += "```json\n"
            plan_block += json.dumps(initialization_plan, indent=2, ensure_ascii=False)
            plan_block += "\n```\n\n"
        
        # Build heap solver output block (optional)
        heap_block = ""
        if heap_solver_output:
            heap_block = "Heap Solver Output (for context):\n"
            import json
            heap_block += "```json\n"
            heap_block += json.dumps(heap_solver_output, indent=2, ensure_ascii=False)
            heap_block += "\n```\n\n"
        
        human_prompt = (
            f"{constraints_block}"
            f"{plan_block}"
            f"{heap_block}"
            f"Original Java Code:\n```java\n{java_code}\n```\n\n"
            f"{error_block}"
            "Please provide the corrected Java code that fixes all compilation and runtime errors."
        )
        
        try:
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt),
            ])
            raw_output = response.content if hasattr(response, 'content') else str(response)
            
            # Extract Java code block from response
            import re
            code_block = None
            m = re.search(r"```java\s*(.*?)```", raw_output, flags=re.DOTALL | re.IGNORECASE)
            if m:
                code_block = m.group(1).strip()
            else:
                # If no code block found, try to use the raw output as code
                code_block = raw_output.strip()
            
            log_entry = {
                "agent": "refiner",
                "stage": "refine_code_executor",
                "system": system_prompt,
                "human": human_prompt,
                "response": raw_output,
            }
            return code_block, raw_output, log_entry
        except Exception as e:
            log_entry = {
                "agent": "refiner",
                "stage": "refine_code_executor",
                "system": system_prompt,
                "human": human_prompt,
                "response": "",
                "error": str(e),
            }
            return java_code, f"Error during Refiner invocation: {str(e)}", log_entry