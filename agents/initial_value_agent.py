"""
Initial Value Agent - Generates Java initialization code for method parameters.

This agent is similar to initializer_agent but simpler:
- Does not require constraints
- Focuses on generating valid initialization code for method parameters
- Can be used to generate initial test inputs

Inputs:
- parameter_types: List[Dict] - List of parameter information
  Each dict contains:
    - name: str - Parameter name (e.g., "p0")
    - type: str - Java type name (e.g., "java.lang.Appendable")
- classpath: Optional[str] - Classpath for type parsing

Output:
{
  "initialization_code": "...Java code...",
  "variable_assignments": {...}  # Map from parameter name to variable name
}
"""

from typing import List, Dict, Optional, Any, Tuple, Set
from pathlib import Path
import os
import sys

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import CLASS_PATH
from javaUtils.type_parse_wrapper import TypeParseServiceWrapper, TypeInfo
from .utils import extract_first_json


def _is_complex(type_info: Optional[TypeInfo]) -> bool:
    """Return True if the parsed type represents a non-primitive, non-array type."""
    if not type_info:
        return False
    if type_info.is_primitive() or type_info.is_array():
        return False
    return type_info.is_interface() or type_info.is_abstract() or type_info.is_concrete_class()


class InitialValueAgent:
    """
    Generates Java initialization code for method parameters without requiring constraints.
    """

    def __init__(self, llm: ChatOpenAI, classpath: Optional[str] = None):
        self.llm = llm
        self.classpath = classpath or CLASS_PATH
        self.service = TypeParseServiceWrapper(classpath=self.classpath)
        self.query_logs: List[Dict[str, Any]] = []

    @staticmethod
    def _get_default_interface_implementation(interface_name: str) -> Optional[str]:
        """
        Get a common default implementation class for well-known interfaces.
        Returns None if no default is available.
        """
        default_implementations = {
            "java.lang.Appendable": "java.lang.StringBuilder",
            "java.lang.CharSequence": "java.lang.String",
            "java.util.List": "java.util.ArrayList",
            "java.util.Set": "java.util.HashSet",
            "java.util.Map": "java.util.HashMap",
            "java.util.Collection": "java.util.ArrayList",
            "java.util.Iterable": "java.util.ArrayList",
            "java.util.Queue": "java.util.LinkedList",
            "java.util.Deque": "java.util.ArrayDeque",
            "java.util.NavigableSet": "java.util.TreeSet",
            "java.util.SortedSet": "java.util.TreeSet",
            "java.util.NavigableMap": "java.util.TreeMap",
            "java.util.SortedMap": "java.util.TreeMap",
            "java.io.Serializable": None,  # Marker interface
            "java.lang.Cloneable": None,  # Marker interface
        }
        return default_implementations.get(interface_name)

    def _collect_type_info(self, java_type: str, seen: Set[str]) -> Dict[str, Any]:
        """
        Collect type information for generating initialization code.
        Returns a simplified plan with constructors and default implementations.
        """
        if java_type in seen:
            return {"type": java_type, "classification": "seen"}
        seen.add(java_type)

        plan: Dict[str, Any] = {
            "type": java_type,
            "classification": None,
            "constructors": [],
            "defaultImplementation": None,
            "concreteSubclassConstructors": {},
            "concreteImplementationConstructors": {},
        }

        try:
            info = self.service.parse_type_info(java_type)
            if not info:
                plan["classification"] = "unknown"
                return plan

            plan["classification"] = info.class_type

            # Collect constructors
            constructors_map = info.constructors or {}
            for sig, params in constructors_map.items():
                param_types = list(params.values()) if isinstance(params, dict) else []
                plan["constructors"].append({
                    "signature": sig,
                    "params": param_types,
                })

            # Handle interfaces
            if info.is_interface():
                default_impl = self._get_default_interface_implementation(java_type)
                if default_impl:
                    plan["defaultImplementation"] = default_impl
                    # Try to get constructors for default implementation
                    try:
                        impl_info = self.service.parse_type_info(default_impl)
                        if impl_info and impl_info.constructors:
                            impl_constructors = []
                            for sig, params in impl_info.constructors.items():
                                param_types = list(params.values()) if isinstance(params, dict) else []
                                impl_constructors.append({
                                    "signature": sig,
                                    "params": param_types,
                                })
                            plan["concreteImplementationConstructors"][default_impl] = impl_constructors
                    except Exception:
                        pass  # Ignore errors

            # Handle abstract classes
            if info.is_abstract():
                subclass_ctors_raw = info.get_concrete_subclass_constructors()
                for subclass_name, ctors in (subclass_ctors_raw or {}).items():
                    entries = []
                    for sig, params in (ctors or {}).items():
                        param_types = list(params.values()) if isinstance(params, dict) else []
                        entries.append({
                            "signature": sig,
                            "params": param_types,
                        })
                    if entries:
                        plan["concreteSubclassConstructors"][subclass_name] = entries

        except Exception as e:
            plan["classification"] = "error"
            plan["error"] = str(e)

        return plan

    def generate(self, parameter_types: List[Dict[str, str]]) -> Tuple[Dict[str, Any], str, Dict[str, Any]]:
        """
        Generate Java initialization code for method parameters.

        Args:
            parameter_types: List of dicts, each with 'name' and 'type' keys
                Example: [{"name": "p0", "type": "java.lang.Appendable"}, ...]

        Returns:
            tuple(parsed_json, raw_llm_output, log_entry)
        """
        self.query_logs = []

        if not parameter_types:
            return {"initialization_code": "", "variable_assignments": {}}, "", {}

        # Collect type information for each parameter
        type_plans = {}
        seen_types: Set[str] = set()
        for param in parameter_types:
            param_name = param.get("name", "")
            param_type = param.get("type", "")
            if param_type:
                type_plans[param_name] = self._collect_type_info(param_type, seen_types)

        # System prompt
        system_prompt = (
            "You are a senior Java engineer. Given a list of method parameters with their types, "
            "generate Java code that initializes all parameters with valid, non-null values. "
            "Use actual objects and meaningful defaults instead of null whenever possible. "
            "Ensure the generated code is compilable and uses appropriate constructors or default values."
        )

        import json
        params_block = json.dumps(
            [{"name": p["name"], "type": p["type"], "plan": type_plans.get(p["name"], {})} 
             for p in parameter_types],
            indent=2,
            ensure_ascii=False
        )

        human_prompt = (
            "Parameter Types and Type Plans:\n"
            "```json\n" + params_block + "\n```\n\n" +
            "Requirements:\n"
            "- Generate Java code that initializes each parameter with a valid value.\n"
            "- Use variable names from the parameter list (e.g., 'p0', 'p1', etc.).\n"
            "- For each parameter, choose an appropriate initialization method:\n"
            "  * If the type is an interface, use a concrete implementation from 'concreteImplementationConstructors' "
            "    or use the 'defaultImplementation' if available (e.g., StringBuilder for Appendable).\n"
            "  * If the type is an abstract class, use a concrete subclass from 'concreteSubclassConstructors'.\n"
            "  * If the type has constructors, prefer the simplest one (fewest parameters, preferably no-arg).\n"
            "  * For primitive types, use default values (0, false, etc.).\n"
            "  * For arrays, create empty arrays with reasonable size.\n"
            "- MINIMIZE NULL VALUES: Always prefer creating actual objects over null.\n"
            "  Only use null if absolutely necessary and no alternative exists.\n"
            "- Generate code as a sequence of variable declarations and assignments.\n"
            "- Do NOT wrap code in a method - just generate the variable initialization statements.\n"
            "- Output ONLY the Java code, wrapped in triple backticks (```java).\n"
            "Example format:\n"
            "```java\n"
            "java.lang.Appendable p0 = new java.lang.StringBuilder();\n"
            "int p1 = 0;\n"
            "```"
        )

        try:
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt),
            ])
            raw_output = response.content if hasattr(response, 'content') else str(response)

            # Extract Java code block
            import re
            code_block = None
            m = re.search(r"```java\s*(.*?)```", raw_output, flags=re.DOTALL | re.IGNORECASE)
            if m:
                code_block = m.group(1).strip()

            # Extract variable assignments (map parameter names to variable names)
            variable_assignments = {}
            if code_block:
                for param in parameter_types:
                    param_name = param["name"]
                    # Look for assignments like "Type param_name = ..."
                    pattern = rf"(\w+)\s+{re.escape(param_name)}\s*="
                    match = re.search(pattern, code_block)
                    if match:
                        variable_assignments[param_name] = param_name

            result_payload = {
                "initialization_code": code_block or raw_output,
                "variable_assignments": variable_assignments,
                "type_plans": type_plans,
            }
            log_entry = {
                "agent": "initial_value",
                "stage": "generate",
                "system": system_prompt,
                "human": human_prompt,
                "response": raw_output,
                "queries": self.query_logs,
            }
            return result_payload, raw_output, log_entry
        except Exception as e:
            log_entry = {
                "agent": "initial_value",
                "stage": "generate",
                "system": system_prompt,
                "human": human_prompt,
                "response": "",
                "error": str(e),
            }
            return {
                "initialization_code": "",
                "variable_assignments": {},
                "type_plans": type_plans,
            }, f"Error during InitialValue generation: {str(e)}", log_entry

