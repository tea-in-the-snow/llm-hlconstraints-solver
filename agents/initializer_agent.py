"""
Initializer Agent - Generates Java initialization code for symbolic objects.

Responsibility:
- Based on heap_solver results, query javaUtils (TypeParseService) for types and for complex
  field types' constructor signatures, recursively.
- Use the LLM to synthesize Java code that constructs all required objects, including imports.

Inputs:
- constraints: List[str]
- heap_solver_output: Dict (must contain result and valuation when SAT)
- classpath: Optional[str] (defaults to config.CLASS_PATH)

Output:
{
  "initialization_code": "...Java code...",
  "plan": { ... detailed type plan ... }
}
"""

from typing import List, Dict, Optional, Any, Tuple, Set
from pathlib import Path
import os
import sys

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

# Ensure project root is on sys.path so we can import javaUtils wrapper
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
    # interfaces/classes/abstract classes are considered complex
    return type_info.is_interface() or type_info.is_abstract() or type_info.is_concrete_class()


class InitializerAgent:
    """
    Generates Java initialization code for symbolic objects based on heap_solver output.
    """

    def __init__(self, llm: ChatOpenAI):
        self.llm = llm
        # Reuse the global classpath by default
        self.classpath = CLASS_PATH
        self.service = TypeParseServiceWrapper(classpath=self.classpath)
        # Internal query logs to surface in orchestrator conversation log
        self.query_logs: List[Dict[str, Any]] = []

    @staticmethod
    def _decode_jvm_type(jvm_sig: str) -> Optional[str]:
        """
        Decode a JVM type signature to a Java class name.
        Examples: "Ljava/util/ArrayList;" -> "java.util.ArrayList", "LNode;" -> "Node".
        Returns None if not an object type (e.g., primitives or arrays not handled here).
        """
        if not isinstance(jvm_sig, str):
            return None
        # Object type descriptor starts with 'L' and ends with ';'
        if jvm_sig.startswith('L') and jvm_sig.endswith(';'):
            class_name = jvm_sig[1:-1].replace('/', '.')
            return class_name
        # For arrays or primitives, we can extend later if needed.
        return None

    @staticmethod
    def _skip_recursive_type(class_name: str) -> bool:
        """Heuristically skip recursion for core JDK types to avoid bloating the plan sent to the LLM."""
        if not isinstance(class_name, str):
            return True
        prefixes = (
            "java.lang.",
            "java.util.",
            "java.io.",
            "java.nio.",
            "java.math.",
            "java.net.",
            "java.time.",
        )
        return class_name.startswith(prefixes)

    def _collect_type_plan(self, jvm_type: str, seen: Set[str]) -> Dict[str, Any]:
        """
        Recursively collect constructor information for a type, including complex parameter types.

        Returns a plan dict with:
        - type: { jvm, class }
        - constructors: [ { signature, params: [type] } ]
        - ctor_children: { paramType: childPlan }
        - fields: { name: type }  (kept for compatibility, but not recursed)
        """
        decoded = self._decode_jvm_type(jvm_type) or jvm_type
        plan: Dict[str, Any] = {
            "type": {
                "jvm": jvm_type,
                "class": decoded,
            },
            "constructors": [],
            "fields": {},
            "ctor_children": {},
        }

        # Use decoded class name to deduplicate
        dedup_key = decoded
        if dedup_key in seen:
            return plan
        seen.add(dedup_key)

        info = self.service.parse_type_info(decoded)
        if not info:
            # Log failed query
            self.query_logs.append({
                "query_type": decoded,
                "from_jvm": jvm_type,
                "status": "not_found",
            })
            return plan

        ctor_entries = []
        ctor_children: Dict[str, Any] = {}

        constructors_map = info.constructors or {}
        for sig, params in constructors_map.items():
            # params is an ordered map paramName -> type
            param_types = list(params.values()) if isinstance(params, dict) else []
            ctor_entries.append({
                "signature": sig,
                "params": param_types,
            })
            # Recurse on complex parameter types
            for ptype in param_types:
                decoded_child = self._decode_jvm_type(ptype) or ptype
                if self._skip_recursive_type(decoded_child):
                    continue
                child_info = self.service.parse_type_info(decoded_child)
                if _is_complex(child_info) and decoded_child not in ctor_children:
                    ctor_children[decoded_child] = self._collect_type_plan(decoded_child, seen)

        plan["constructors"] = ctor_entries
        plan["fields"] = info.fields or {}
        plan["ctor_children"] = ctor_children

        # Log successful query with constructor results
        self.query_logs.append({
            "query_type": decoded,
            "from_jvm": jvm_type,
            "status": "ok",
            "constructors": ctor_entries,
            "fields_count": len(plan["fields"]),
        })

        return plan

    def _build_initialization_plan(self, heap_solver_output: Dict[str, Any]) -> Dict[str, Any]:
        """Build a full initialization plan from heap solver valuations."""
        result: Dict[str, Any] = {"objects": []}
        valuations = heap_solver_output.get("valuation", []) if isinstance(heap_solver_output, dict) else []

        # Filter root variables (those without field deref) for object construction
        seen_types: Set[str] = set()
        for entry in valuations:
            if not isinstance(entry, dict):
                continue
            var = entry.get("variable")
            jvm_type = entry.get("type")
            new_object = entry.get("newObject", True)
            if not var or not jvm_type:
                continue
            # Only consider root objects (no "." deref) for direct construction
            if "." in var:
                continue

            type_plan = self._collect_type_plan(jvm_type, seen_types)
            result["objects"].append({
                "variable": var,
                "type": jvm_type,
                "newObject": new_object,
                "plan": type_plan,
            })

        return result

    def generate(self, constraints: List[str], heap_solver_output: Dict[str, Any]) -> Tuple[Dict[str, Any], str, Dict[str, Any]]:
        """
        Generate Java initialization code using LLM based on collected plans.

        Returns:
            tuple(parsed_json, raw_llm_output, log_entry)
        """
        # Reset query logs for this generation
        self.query_logs = []

        # If heap result is not SAT, return empty
        if not heap_solver_output or heap_solver_output.get("result") != "SAT":
            log_entry = {"agent": "initializer", "stage": "generate", "response": "", "error": "heap_solver not SAT"}
            return {"initialization_code": "", "plan": {}}, "heap_solver not SAT", log_entry

        init_plan = self._build_initialization_plan(heap_solver_output)

        # System prompt for code generation
        system_prompt = (
            "You are a senior Java engineer. Given a construction plan for several objects, "
            "generate Java code that constructs all symbolic objects with correct imports and "
            "clear variable assignments. Prefer using available public constructors from the plan; "
            "if no public constructors exist, use builder/static factory methods listed. "
            "Initialize nested fields according to the plan recursively. Ensure compilable code."
        )

        import json
        constraints_block = "\n".join(f"- {c}" for c in constraints)
        plan_block = json.dumps(init_plan, indent=2, ensure_ascii=False)

        human_prompt = (
            "Constraints (for context):\n" + constraints_block + "\n\n" +
            "Initialization Plan (JSON):\n" + "```json\n" + plan_block + "\n```\n\n" +
            "Requirements:\n" +
            "- Include all necessary import statements.\n" +
            "- Use variable names from the plan.\n" +
            "- For each object, choose a sensible constructor signature from the plan.\n" +
            "- Recursively initialize complex field types shown under children.\n" +
            "- Avoid private members; focus on public/protected constructors and fields.\n" +
            "- Output ONLY one Java code block wrapped in triple backticks (```java)."
        )

        try:
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=human_prompt),
            ])
            raw_output = response.content if hasattr(response, 'content') else str(response)

            # Try to extract Java code block
            import re
            code_block = None
            m = re.search(r"```java\s*(.*?)```", raw_output, flags=re.DOTALL | re.IGNORECASE)
            if m:
                code_block = m.group(1).strip()

            # Also try to extract any JSON (not required, but useful)
            parsed_json, _ = extract_first_json(raw_output)

            # Package the plan and generated code (fallback to raw_output if no fenced block found)
            result_payload = {
                "initialization_code": code_block or raw_output,
                "plan": init_plan,
            }
            log_entry = {
                "agent": "initializer",
                "stage": "generate",
                "system": system_prompt,
                "human": human_prompt,
                "response": raw_output,
                "queries": self.query_logs,
            }
            return result_payload, raw_output, log_entry
        except Exception as e:
            log_entry = {
                "agent": "initializer",
                "stage": "generate",
                "system": system_prompt,
                "human": human_prompt,
                "response": "",
                "error": str(e),
            }
            return {"initialization_code": "", "plan": init_plan}, f"Error during Initializer invocation: {str(e)}", log_entry
