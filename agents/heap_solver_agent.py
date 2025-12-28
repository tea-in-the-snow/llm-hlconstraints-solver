"""
Heap Solver Agent - Focuses on solving heap-related constraints.

Responsibility: Based on type_solver results (cannot override type_solver results, return UNSAT if conflict),
analyze heap-related constraints for each variable in the constraint set (including null constraints, reference relationships),
generate reference types for each variable.
"""

from typing import List, Dict, Optional, Any, Tuple
from pathlib import Path
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from .utils import extract_first_json


class HeapSolverAgent:
    """
    Focuses on solving heap-related constraints.
    
    Input:
    - constraints: List[str]
    - source_context: Dict[str, Any]
    - heap_state: Dict[str, Any]
    - type_solver_output: Dict
    
    Output:
    {
        "result": "SAT" | "UNSAT" | "UNKNOWN",
        "valuation": [
            {
                "variable": "head(ref)",
                "type": "LNode;",
                "newObject": true,
                "trueRef": true,
                "reference": 1
            }
        ]
    }
    """
    
    def __init__(self, llm: ChatOpenAI):
        """
        Initialize HeapSolverAgent.
        
        Args:
            llm: ChatOpenAI instance
        """
        self.llm = llm
    
    def solve(
        self,
        constraints: List[str],
        source_context: Optional[Dict[str, Any]] = None,
        heap_state: Optional[Dict[str, Any]] = None,
        type_solver_output: Optional[Dict] = None,
    ) -> Tuple[Optional[Dict], str, Dict[str, Any]]:
        """
        Solve heap-related constraints.
        
        Args:
            constraints: List of constraints
            source_context: Source code context
            heap_state: Heap state information
            type_solver_output: type_solver output results
        
        Returns:
            Tuple of (parsed_json_dict, raw_llm_output_string, conversation_log)
        """
        # Read ctx.md for reference information
        ctx_content = ""
        try:
            ctx_path = Path(__file__).parent.parent / "ctx.md"
            if ctx_path.exists():
                ctx_content = ctx_path.read_text(encoding="utf-8").strip()
        except Exception:
            pass
        
        system_prompt = (
            "You are an assistant specialized in solving heap-related constraints. "
            "Your task is to analyze heap-related constraints for each variable in the constraint set "
            "(including null constraints, reference relationships) based on type_solver results, "
            "generate reference types for each variable.\n\n"
            "Naming note: variables written with the suffix '(ref)' denote symbolic reference variables; "
            "they correspond to the same variable names in code without '(ref)', but in your final answer you must keep the '(ref)' suffix.\n\n"
            "CRITICAL: Understanding Type vs Value:\n"
            "In Java, a variable's TYPE (declared type) and its VALUE (runtime value) are SEPARATE concepts.\n"
            "- A variable can have type 'Node' but value 'null' - this is VALID and SATISFIABLE\n"
            "- Example: 'Node n = null;' - type is Node, value is null\n"
            "- type_solver provides the TYPE information (what type the variable can be)\n"
            "- heap_solver provides the VALUE information (whether it's null or points to an object)\n"
            "- A constraint like 'x is null' means the VALUE is null, but the TYPE can still be specified\n"
            "- type_solver assigning type 'LNode;' to a variable does NOT mean it cannot be null\n"
            "- A variable with type 'LNode;' can have reference=null if constraints require it\n\n"
            "Important constraints:\n"
            "1. Cannot override type_solver TYPE results - types must match\n"
            "2. Must maintain type information determined by type_solver\n"
            "3. Add heap-related information (newObject, trueRef, reference) on this basis\n"
            "4. MUST provide information for ALL variable expressions from type_solver output\n"
            "5. If constraints say a variable is null, set reference=null even if type_solver gave it a type\n\n"
            "Output format:\n"
            "- SAT: return {\"result\": \"SAT\", \"valuation\": [...]}\n"
            "- UNSAT: return {\"result\": \"UNSAT\"}\n"
            "- UNKNOWN: return {\"result\": \"UNKNOWN\"}\n\n"
            "For SAT valuations, each entry should contain:\n"
            "- variable: variable name (e.g., \"head(ref)\" or \"head(ref).next(ref)\")\n"
            "- type: JVM format type (must match type_solver results)\n"
            "- newObject: boolean (default true for new objects, false only if the reference points to another existing object or an object already in the heap)\n"
            "  Note: When solving high-level constraints, the task is to construct valid inputs for the method. "
            "Even if a variable is a method input parameter, newObject can still be true when creating new test inputs.\n"
            "- trueRef: boolean (true for symbolic reference, false for concrete address)\n"
            "- reference: unique ID (integer for new objects, null ONLY if constraints explicitly require null)\n"
            "  IMPORTANT: Prefer creating actual objects (use positive integer IDs) over null references.\n"
            "  Only use null if constraints explicitly state that a variable must be null.\n\n"
            "Important rules:\n"
            "1. MUST include ALL variables that type_solver provided in your valuation\n"
            "2. Do not invent new variable names that weren't in type_solver output\n"
            "3. Types must exactly match type_solver output\n"
            "4. If type_solver result is UNSAT, return UNSAT directly\n"
            "5. When constructing method inputs, newObject=true is valid for input parameters that need new object instances\n"
            "6. CRITICAL: Type and Value are SEPARATE - a variable can have a type but value=null:\n"
            "   - type_solver provides TYPE information (declared type)\n"
            "   - heap_solver provides VALUE information (reference/object ID)\n"
            "   - Example: type='LNode;', reference=null is VALID (like 'Node n = null;')\n"
            "   - If constraint says 'x is null', set reference=null regardless of type from type_solver\n"
            "   - type_solver assigning a type does NOT mean the value cannot be null\n"
            "   - Only return UNSAT if there's a real type mismatch, NOT if a typed variable is null\n"
            "7. When constraints explicitly require null, set reference=null even if type_solver gave a type\n"
            "8. Only create actual objects (reference with positive ID) when constraints require non-null\n\n"
            "You may show your reasoning process, but the final output must be valid JSON format."
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
            type_solver_block += "Important: You cannot change TYPE information determined by type_solver. "
            type_solver_block += "However, remember that TYPE and VALUE are separate: a variable can have type from type_solver but value=null if constraints require it. "
            type_solver_block += "If conflicts are found, return UNSAT.\n\n"
        else:
            type_solver_block = "Warning: No type_solver output available.\n\n"
        
        # Build source code context block (defensive against unexpected shapes)
        source_context_block = ""
        if isinstance(source_context, dict) and source_context:
            source_context_block = "Source Code Context:\n"
            source_context_block += "This is the actual source code of the method being analyzed. "
            source_context_block += "Use it to understand code structure, logic, and relationships.\n\n"
            
            method_name = source_context.get("method_name")
            if isinstance(method_name, str) and method_name:
                source_context_block += f"Method: {method_name}\n"
            class_name = source_context.get("class_name")
            if isinstance(class_name, str) and class_name:
                source_context_block += f"Class: {class_name}\n"
            source_file = source_context.get("source_file")
            if isinstance(source_file, str) and source_file:
                source_context_block += f"File: {source_file}\n"
            
            line_info = source_context.get("line_numbers")
            if isinstance(line_info, dict):
                source_context_block += f"Lines: {line_info.get('method_start', '?')}-{line_info.get('method_end', '?')}\n"
            
            source_context_block += "\n"
            
            method_source = source_context.get("method_source")
            if isinstance(method_source, str) and method_source:
                source_context_block += "Method Source Code:\n"
                source_context_block += "```java\n"
                source_context_block += method_source
                source_context_block += "```\n\n"
            
            class_source = source_context.get("class_source")
            if isinstance(class_source, str) and class_source:
                source_context_block += "Complete Class Source Code:\n"
                source_context_block += "```java\n"
                source_context_block += class_source
                source_context_block += "```\n\n"
            
            related = source_context.get("related_classes")
            if isinstance(related, dict) and related:
                source_context_block += "Related Classes (referenced in constraints):\n"
                for class_name, class_src in related.items():
                    if isinstance(class_src, str) and class_src:
                        source_context_block += f"\nClass: {class_name}\n"
                        source_context_block += "```java\n"
                        source_context_block += class_src
                        source_context_block += "```\n"
                source_context_block += "\n"
        
        # Build heap state information block (defensive against unexpected shapes)
        heap_state_block = ""
        if isinstance(heap_state, dict) and heap_state:
            heap_state_block = "Heap State Information:\n"
            heap_state_block += "This shows the current state of reachable objects in the heap.\n\n"
            
            aliases = heap_state.get("aliases")
            if isinstance(aliases, dict) and aliases:
                heap_state_block += "Aliases (variable → object reference):\n"
                for var_name, obj_ref in aliases.items():
                    heap_state_block += f"  {var_name} → {obj_ref}\n"
                heap_state_block += "\n"
            
            objects = heap_state.get("objects")
            if isinstance(objects, dict) and objects:
                heap_state_block += "Objects (reference → structure):\n"
                for obj_ref, obj_desc in objects.items():
                    if not isinstance(obj_desc, dict):
                        heap_state_block += f"  {obj_ref}: Unknown (non-dict)\n\n"
                        continue
                    class_name = obj_desc.get("class", "Unknown")
                    heap_state_block += f"  {obj_ref}: {class_name}\n"
                    
                    fields = obj_desc.get("fields", {})
                    if isinstance(fields, dict) and fields:
                        for field_name, field_value in fields.items():
                            heap_state_block += f"    {field_name}: {field_value}\n"
                    
                    if "elements" in obj_desc:
                        heap_state_block += f"    elements: {obj_desc['elements']}\n"
                    if "length" in obj_desc:
                        heap_state_block += f"    length: {obj_desc['length']}\n"
                    
                    heap_state_block += "\n"
        
        # Build reference information block from ctx.md
        reference_block = ""
        if ctx_content:
            reference_block = "Reference Information:\n"
            reference_block += "The following reference information may help you understand the constraints and solve them correctly:\n\n"
            reference_block += ctx_content + "\n\n"
        
        human_prompt = (
            f"{reference_block}"
            f"{type_solver_block}"
            f"{source_context_block}"
            f"{heap_state_block}"
            f"Constraints:\n{constraints_block}\n\n"
            "Please analyze heap-related constraints based on type_solver results and provide your answer (JSON format)."
        )
        
        try:
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt),
            ])
            raw_output = response.content if hasattr(response, 'content') else str(response)
            
            parsed, _ = extract_first_json(raw_output)
            log_entry = {
                "agent": "heap_solver",
                "stage": "solve",
                "system": system_prompt,
                "human": human_prompt,
                "response": raw_output,
            }
            return parsed, raw_output, log_entry
        except Exception as e:
            log_entry = {
                "agent": "heap_solver",
                "stage": "solve",
                "system": system_prompt,
                "human": human_prompt,
                "response": "",
                "error": str(e),
            }
            return None, f"Error during HeapSolver invocation: {str(e)}", log_entry
