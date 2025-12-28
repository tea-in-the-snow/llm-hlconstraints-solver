"""
Type Solver Agent - Focuses on solving type-related constraints.

Responsibility: Analyze type-related constraints for each variable in the constraint set,
combine with variable static types and source code context,
generate type information solutions for each variable.
"""

from typing import List, Dict, Optional, Any, Tuple
from pathlib import Path
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

from .utils import extract_first_json


class TypeSolverAgent:
    """
    Focuses on solving type-related constraints.
    
    Input:
    - constraints: List[str]
    - variable_static_type: Dict[str, str]
    - type_hierarchy: Dict[str, str]
    
    Output:
    {
        "result": "SAT" | "UNSAT" | "UNKNOWN",
        "valuation": [
            {
                "variable": "head(ref)",
                "type": "LNode;",
            }
        ]
    }
    """
    
    def __init__(self, llm: ChatOpenAI):
        """
        Initialize TypeSolverAgent.
        
        Args:
            llm: ChatOpenAI instance
        """
        self.llm = llm
    
    def solve(
        self,
        constraints: List[str],
        variable_static_type: Optional[Dict[str, str]] = None,
        type_hierarchy: Optional[Dict[str, str]] = None,
        source_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[Dict], str, Dict[str, Any]]:
        """
        Solve type-related constraints.
        
        Args:
            constraints: List of constraints
            variable_static_type: Mapping of variable static types
            type_hierarchy: Type hierarchy information
            source_context: Source code context
        
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
            "You are an assistant specialized in solving type constraints. "
            "Your task is to analyze type-related constraints for each variable in the constraint set, "
            "combine with variable static types and type hierarchy information, "
            "generate type information solutions for each variable.\n\n"
            "Naming note: variables written with the suffix '(ref)' denote symbolic reference variables; "
            "they correspond to the same variable names in code without '(ref)', but in your final answer you must keep the '(ref)' suffix.\n\n"
            "Output format:\n"
            "- SAT: return {\"result\": \"SAT\", \"valuation\": [...]}\n"
            "- UNSAT: return {\"result\": \"UNSAT\"}\n"
            "- UNKNOWN: return {\"result\": \"UNKNOWN\"}\n\n"
            "For SAT valuations, each entry should contain:\n"
            "- variable: variable name (e.g., \"head(ref)\" or \"head(ref).next(ref)\")\n"
            "- type: JVM format type (e.g., \"LNode;\", \"Ljava/util/ArrayList;\")\n\n"
            "Important rules:\n"
            "1. MUST provide type information for ALL variable expressions that appear in constraints\n"
            "   - This includes simple variables like 'head(ref)'\n"
            "   - AND field access chains like 'head(ref).next(ref)', 'obj(ref).field(ref).subfield(ref)', etc.\n"
            "2. Do not invent new variable names that don't appear in constraints (e.g., 'obj#1', 'node1', etc.)\n"
            "3. Types must conform to type hierarchy and static type constraints\n"
            "4. If a variable's static type is given, the actual type must be a subtype or the same type\n"
            "5. Type must be an actual runtime concrete type, NOT an interface type or abstract class\n"
            "   For example, use \"Ljava/util/ArrayList;\" instead of \"Ljava/util/List;\"\n"
            "   CRITICAL: Even if the static type is an interface, you MUST choose a concrete implementation:\n"
            "   - For java.lang.Appendable, use java.lang.StringBuilder\n"
            "   - For java.util.List, use java.util.ArrayList\n"
            "   - For java.util.Set, use java.util.HashSet\n"
            "   - For java.util.Map, use java.util.HashMap\n"
            "   - For java.util.Collection, use java.util.ArrayList\n"
            "   - For other interfaces, choose a common concrete implementation class\n"
            "6. For field access expressions like 'obj(ref).field(ref)', determine the type based on:\n"
            "   - The type of the parent object (obj)\n"
            "   - The field definition in the parent's class\n"
            "   - Any constraints on that field\n\n"
            "Type selection preferences:\n"
            "7. When multiple types are possible and satisfy all constraints, prefer the TOP-MOST parent type\n"
            "   - For example, if a variable can be Object or String, choose Object\n"
            "8. When multiple primitive/wrapper types are possible, AVOID String type and prefer numeric types\n"
            "   - For example, prefer Integer over String, Double over String, Long over String, etc.\n"
            "   - Only use String type if it is explicitly required by constraints\n\n"
            "You may show your reasoning process, but the final output must be valid JSON format."
        )
        
        constraints_block = "\n".join(f"- {c}" for c in constraints)
        
        # Build variable static type information block (defensive)
        static_type_block = ""
        if isinstance(variable_static_type, dict) and variable_static_type:
            static_type_block = "Variable Static Type Information:\n"
            static_type_block += "These are the declared static types of variables. "
            static_type_block += "The actual runtime type must be a subtype or the same type as the declared type.\n\n"
            for var_name, declared_type in variable_static_type.items():
                static_type_block += f"  {var_name}: declared type is {declared_type}\n"
            static_type_block += "\n"
        
        # Build type hierarchy information block (defensive)
        type_hierarchy_block = ""
        if isinstance(type_hierarchy, dict) and type_hierarchy:
            type_hierarchy_block = "Type Hierarchy Information:\n"
            for var_name, type_info in type_hierarchy.items():
                type_hierarchy_block += f"\nVariable: {var_name}\n{type_info}\n"
            type_hierarchy_block += "\n"
        
        # Build source code context block (defensive)
        source_context_block = ""
        if isinstance(source_context, dict) and source_context:
            source_context_block = "Source Code Context:\n"
            source_context_block += "This is the actual source code of the method being analyzed. "
            source_context_block += "Use it to understand code structure, logic, and type relationships.\n\n"
            
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
        
        # Build reference information block from ctx.md
        reference_block = ""
        if ctx_content:
            reference_block = "Reference Information:\n"
            reference_block += "The following reference information may help you understand the constraints and solve them correctly:\n\n"
            reference_block += ctx_content + "\n\n"
        
        human_prompt = (
            f"{reference_block}"
            f"{static_type_block}"
            f"{type_hierarchy_block}"
            f"{source_context_block}"
            f"Constraints:\n{constraints_block}\n\n"
            "Please analyze type-related constraints and provide your answer (JSON format)."
        )
        
        try:
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt),
            ])
            raw_output = response.content if hasattr(response, 'content') else str(response)
            
            parsed, _ = extract_first_json(raw_output)
            log_entry = {
                "agent": "type_solver",
                "stage": "solve",
                "system": system_prompt,
                "human": human_prompt,
                "response": raw_output,
            }
            return parsed, raw_output, log_entry
        except Exception as e:
            log_entry = {
                "agent": "type_solver",
                "stage": "solve",
                "system": system_prompt,
                "human": human_prompt,
                "response": "",
                "error": str(e),
            }
            return None, f"Error during TypeSolver invocation: {str(e)}", log_entry
