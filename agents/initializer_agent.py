"""
Initializer Agent - Generates Java initialization code for symbolic objects.

Responsibility:
- Based on heap_solver, type_solver results, and variable_static_type, query javaUtils (TypeParseService) 
  for types and for complex field types' constructor signatures, recursively.
- Use the LLM to synthesize Java code that constructs all required objects, including imports.
- Initialize ALL method parameters from variable_static_type, even if they don't appear in constraints or solver outputs.
- Initialize ALL symbolic references from type_solver, even if they don't appear in heap_solver output.
- Avoid null values unless heap_solver explicitly requires them (heap_solver is authoritative for null decisions).

Inputs:
- constraints: List[str]
- heap_solver_output: Dict (must contain result and valuation when SAT)
- type_solver_output: Optional[Dict] (contains symbolic references from type solving)
- variable_static_type: Optional[Dict[str, str]] (static types of method parameters - ALL must be initialized)
- classpath: Optional[str] (defaults to config.CLASS_PATH)

Output:
{
  "initialization_code": "...Java code...",
  "plan": { ... detailed type plan ... }
}

Key Rules:
1. ALL parameters in variable_static_type must be initialized (unless heap_solver requires null)
2. heap_solver is authoritative: if heap_solver says reference=null, skip initialization
3. If a parameter is not in type_solver_output, infer type from variable_static_type
4. If a parameter is not in heap_solver_output, create it (non-null by default)
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

    @staticmethod
    def _get_default_interface_implementation(interface_name: str) -> Optional[str]:
        """
        Get a common default implementation class for well-known interfaces.
        Returns None if no default is available.
        
        Priority: Prefer numeric types over String for Comparable and similar interfaces.
        """
        default_implementations = {
            "java.lang.Appendable": "java.lang.StringBuilder",
            "java.lang.CharSequence": "java.lang.String",
            "java.lang.Comparable": "java.lang.Integer",  # Prefer Integer over String
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
            "java.io.Serializable": None,  # Marker interface, skip
            "java.lang.Cloneable": None,  # Marker interface, skip
        }
        return default_implementations.get(interface_name)

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
                # Filled later once we have TypeInfo; keep key for LLM
                # so it can see "class" / "abstract class" / "interface".
                "classification": None,
            },
            "constructors": [],
            "fields": {},
            "ctor_children": {},
            # For abstract classes: populated with concrete subclass choices.
            # Shape:
            #   {
            #     "com.foo.Concrete": [
            #        {"signature": "...", "params": ["java.lang.String", "..."]},
            #        ...
            #     ],
            #     ...
            #   }
            "concreteSubclassConstructors": {},
            # For interfaces: populated with concrete implementation class constructors.
            # Shape same as concreteSubclassConstructors:
            #   {
            #     "com.foo.Implementation": [
            #        {"signature": "...", "params": ["java.lang.String", "..."]},
            #        ...
            #     ],
            #     ...
            #   }
            "concreteImplementationConstructors": {},
            # Suggested default implementation for well-known interfaces
            "defaultImplementation": None,
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

        # Record high-level classification for the LLM
        plan["type"]["classification"] = info.class_type

        ctor_entries: List[Dict[str, Any]] = []
        ctor_children: Dict[str, Any] = {}

        # Normal constructors for this type
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

        # If this is an abstract class, surface concrete subclass constructors
        # that Java side already computed, so LLM can safely choose them
        # instead of instantiating the abstract type directly.
        if info.is_abstract():
            subclass_ctors_raw = info.get_concrete_subclass_constructors()
            subclass_ctors_plan: Dict[str, List[Dict[str, Any]]] = {}
            for subclass_name, ctors in subclass_ctors_raw.items():
                entries: List[Dict[str, Any]] = []
                for sig, params in (ctors or {}).items():
                    param_types = list(params.values()) if isinstance(params, dict) else []
                    entries.append({
                        "signature": sig,
                        "params": param_types,
                    })
                    # Also ensure we collect type plans for parameter types of subclass
                    for ptype in param_types:
                        decoded_child = self._decode_jvm_type(ptype) or ptype
                        if self._skip_recursive_type(decoded_child):
                            continue
                        child_info = self.service.parse_type_info(decoded_child)
                        if _is_complex(child_info) and decoded_child not in ctor_children:
                            ctor_children[decoded_child] = self._collect_type_plan(decoded_child, seen)
                if entries:
                    subclass_ctors_plan[subclass_name] = entries
            plan["concreteSubclassConstructors"] = subclass_ctors_plan

        # If this is an interface, collect constructors of concrete implementation classes
        if info.is_interface():
            impl_ctors_plan: Dict[str, List[Dict[str, Any]]] = {}
            implemented_classes = info.implemented_class_names or []
            
            # Add default implementation if available
            default_impl = self._get_default_interface_implementation(decoded)
            if default_impl:
                plan["defaultImplementation"] = default_impl
                if default_impl not in implemented_classes:
                    implemented_classes = [default_impl] + implemented_classes
            
            # For Comparable interface, prioritize numeric types over String
            if decoded == "java.lang.Comparable":
                # Reorder to put numeric types first
                numeric_types = ["java.lang.Integer", "java.lang.Double", "java.lang.Long", 
                               "java.lang.Float", "java.lang.Short", "java.lang.Byte"]
                string_type = "java.lang.String"
                
                # Separate numeric types, String, and others
                numeric_found = [t for t in numeric_types if t in implemented_classes]
                string_found = [t for t in [string_type] if t in implemented_classes]
                others = [t for t in implemented_classes if t not in numeric_types and t != string_type]
                
                # Reorder: numeric types first, then others, then String last
                implemented_classes = numeric_found + others + string_found
            
            # Collect constructors for concrete implementation classes
            for impl_name in implemented_classes[:5]:  # Limit to first 5 to avoid bloating
                if impl_name in seen:
                    continue
                # Skip if it's a skip type (to avoid recursion into JDK internals)
                if self._skip_recursive_type(impl_name):
                    # But still try to get basic constructor info for common JDK types
                    impl_info = self.service.parse_type_info(impl_name)
                    if impl_info and impl_info.constructors:
                        entries: List[Dict[str, Any]] = []
                        for sig, params in (impl_info.constructors or {}).items():
                            param_types = list(params.values()) if isinstance(params, dict) else []
                            entries.append({
                                "signature": sig,
                                "params": param_types,
                            })
                        if entries:
                            impl_ctors_plan[impl_name] = entries
                    continue
                
                impl_info = self.service.parse_type_info(impl_name)
                if not impl_info or not impl_info.is_concrete_class():
                    continue
                
                entries: List[Dict[str, Any]] = []
                constructors_map = impl_info.constructors or {}
                for sig, params in constructors_map.items():
                    param_types = list(params.values()) if isinstance(params, dict) else []
                    entries.append({
                        "signature": sig,
                        "params": param_types,
                    })
                    # Also ensure we collect type plans for parameter types
                    for ptype in param_types:
                        decoded_child = self._decode_jvm_type(ptype) or ptype
                        if self._skip_recursive_type(decoded_child):
                            continue
                        child_info = self.service.parse_type_info(decoded_child)
                        if _is_complex(child_info) and decoded_child not in ctor_children:
                            ctor_children[decoded_child] = self._collect_type_plan(decoded_child, seen)
                if entries:
                    impl_ctors_plan[impl_name] = entries
            
            plan["concreteImplementationConstructors"] = impl_ctors_plan

        # Log successful query with constructor results
        self.query_logs.append({
            "query_type": decoded,
            "from_jvm": jvm_type,
            "status": "ok",
            "constructors": ctor_entries,
            "fields_count": len(plan["fields"]),
        })

        return plan

    def _extract_null_constraints(self, constraints: List[str]) -> Set[str]:
        """
        Extract variables that are explicitly required to be null from constraints.
        IMPORTANT: Only extract variables that MUST be null, not those that must be non-null.
        Constraints like "!('var' is null)" mean var is NOT null, so should be excluded.
        
        Returns:
            Set of variable names that must be null
        """
        null_vars = set()
        import re
        
        for constraint in constraints:
            # Skip if this is a negation constraint (starts with !)
            # "!('var' is null)" means var is NOT null, so we should not add it
            if constraint.strip().startswith('!'):
                continue
            
            # Pattern to match "variable is null" or "variable == null" or similar
            # Match patterns like: 'var(ref) is null', 'var(ref) == null', 'var(ref) = null'
            # Use case-insensitive matching for "null" keyword
            patterns = [
                r"['\"]?([a-zA-Z_][a-zA-Z0-9_]*(?:\(ref\))?(?:\.[a-zA-Z_][a-zA-Z0-9_]*\(ref\))*)['\"]?\s+(?:is\s+)?null\b",
                r"['\"]?([a-zA-Z_][a-zA-Z0-9_]*(?:\(ref\))?(?:\.[a-zA-Z_][a-zA-Z0-9_]*\(ref\))*)['\"]?\s*==\s*null\b",
                r"['\"]?([a-zA-Z_][a-zA-Z0-9_]*(?:\(ref\))?(?:\.[a-zA-Z_][a-zA-Z0-9_]*\(ref\))*)['\"]?\s*=\s*null\b",
                r"null\s*==\s*['\"]?([a-zA-Z_][a-zA-Z0-9_]*(?:\(ref\))?(?:\.[a-zA-Z_][a-zA-Z0-9_]*\(ref\))*)['\"]?",
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, constraint, re.IGNORECASE)
                for match in matches:
                    if '(ref)' in match:
                        null_vars.add(match)
        
        return null_vars

    @staticmethod
    def _java_type_to_jvm(java_type: str) -> str:
        """
        Convert Java type name to JVM format.
        Examples: "java.lang.String" -> "Ljava/lang/String;", "int" -> "I"
        """
        if not java_type:
            return ""
        
        # Primitive types
        primitive_map = {
            "boolean": "Z",
            "byte": "B",
            "char": "C",
            "double": "D",
            "float": "F",
            "int": "I",
            "long": "J",
            "short": "S",
        }
        if java_type in primitive_map:
            return primitive_map[java_type]
        
        # Array types
        if java_type.endswith("[]"):
            element_type = java_type[:-2]
            return "[" + InitializerAgent._java_type_to_jvm(element_type)
        
        # Object types
        return "L" + java_type.replace(".", "/") + ";"

    def _build_initialization_plan(
        self, 
        heap_solver_output: Dict[str, Any],
        type_solver_output: Optional[Dict[str, Any]] = None,
        constraints: Optional[List[str]] = None,
        variable_static_type: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Build a full initialization plan from heap solver valuations, type solver output, and variable static types.
        
        This ensures:
        1. All symbolic references from type_solver are initialized
        2. All method parameters from variable_static_type are initialized
        3. Variables are only null if heap_solver explicitly requires it
        """
        result: Dict[str, Any] = {"objects": []}
        heap_valuations = heap_solver_output.get("valuation", []) if isinstance(heap_solver_output, dict) else []
        
        # Extract null constraints to know which variables must be null
        null_required_vars = set()
        if constraints:
            null_required_vars = self._extract_null_constraints(constraints)
        
        # Build a map from variable name to heap solver entry for quick lookup
        heap_var_map: Dict[str, Dict[str, Any]] = {}
        for entry in heap_valuations:
            if isinstance(entry, dict):
                var = entry.get("variable")
                if var:
                    heap_var_map[var] = entry
        
        # Collect all root variables (those without field deref) from type_solver
        type_var_map: Dict[str, str] = {}  # variable -> jvm_type
        if type_solver_output and type_solver_output.get("result") == "SAT":
            type_valuations = type_solver_output.get("valuation", [])
            for entry in type_valuations:
                if isinstance(entry, dict):
                    var = entry.get("variable")
                    jvm_type = entry.get("type")
                    if var and jvm_type and "." not in var:  # Only root variables
                        type_var_map[var] = jvm_type
        
        # Also collect root variables from heap_solver (in case some are missing from type_solver)
        for var in heap_var_map.keys():
            if "." not in var and var not in type_var_map:
                entry = heap_var_map[var]
                jvm_type = entry.get("type")
                if jvm_type:
                    type_var_map[var] = jvm_type
        
        # CRITICAL: Add all method parameters from variable_static_type
        # These are the method input parameters that must be initialized
        # This ensures ALL method parameters are initialized, even if they don't appear in constraints
        if variable_static_type:
            for param_name, static_type in variable_static_type.items():
                # Create the symbolic reference variable name (add "(ref)" suffix)
                # Note: "receiver" becomes "receiver(ref)", "p0" becomes "p0(ref)", etc.
                var_name = f"{param_name}(ref)"
                
                # Skip if already in type_var_map (from type_solver or heap_solver)
                # This preserves the type information from solvers if available
                if var_name in type_var_map:
                    continue
                
                # Convert Java type to JVM format
                jvm_type = self._java_type_to_jvm(static_type)
                if jvm_type:
                    type_var_map[var_name] = jvm_type
                    # Log that we're adding a parameter from static types
                    self.query_logs.append({
                        "query_type": f"parameter_{param_name}",
                        "from_static_type": static_type,
                        "jvm_type": jvm_type,
                        "status": "added_from_static_type",
                    })
        
        # Log for debugging: if type_var_map is still empty, something is wrong
        if not type_var_map:
            self.query_logs.append({
                "query_type": "debug_empty_type_var_map",
                "status": "warning",
                "type_solver_available": type_solver_output is not None,
                "type_solver_result": type_solver_output.get("result") if type_solver_output else None,
                "heap_var_count": len(heap_var_map),
                "static_type_count": len(variable_static_type) if variable_static_type else 0,
            })
        
        # Build initialization plan for all root variables
        seen_types: Set[str] = set()
        
        # DEBUG: Log what we're about to process
        self.query_logs.append({
            "query_type": "debug_initialization_plan_start",
            "type_var_map_size": len(type_var_map),
            "type_var_map_keys": list(type_var_map.keys()),
            "heap_var_map_size": len(heap_var_map),
            "heap_var_map_keys": list(heap_var_map.keys()),
        })
        
        for var, jvm_type in type_var_map.items():
            try:
                # Check if this variable is required to be null by constraints
                is_null_required_by_constraint = var in null_required_vars
                
                # Get heap solver info if available
                heap_entry = heap_var_map.get(var)
                new_object = True
                is_null_required_by_heap = False
                
                if heap_entry:
                    new_object = heap_entry.get("newObject", True)
                    # Check if heap solver explicitly requires null
                    reference = heap_entry.get("reference")
                    if reference is None or reference == "null":
                        # Heap solver says null - this is the authoritative source
                        # Only skip if heap solver explicitly requires null
                        is_null_required_by_heap = True
                    else:
                        # Reference exists, create object
                        new_object = True
                
                # DEBUG: Log decision for this variable
                self.query_logs.append({
                    "query_type": f"debug_processing_{var}",
                    "jvm_type": jvm_type,
                    "is_null_required_by_heap": is_null_required_by_heap,
                    "is_null_required_by_constraint": is_null_required_by_constraint,
                    "will_skip": is_null_required_by_heap or is_null_required_by_constraint,
                })
                
                # CRITICAL: Only skip initialization if heap_solver explicitly requires null
                # Constraints saying "is null" are also respected, but heap_solver is authoritative
                if is_null_required_by_heap or is_null_required_by_constraint:
                    # Skip initialization only if explicitly required
                    continue
                
                # CRITICAL: Skip type plan collection for array and primitive types
                # Arrays start with '[' in JVM format (e.g., [J for long[], [[I for int[][])
                # Primitives are single chars (I, J, D, F, etc.)
                # These don't need constructor information
                is_array_or_primitive = (
                    jvm_type.startswith('[') or  # Array type
                    (len(jvm_type) == 1 and jvm_type in 'ZBCSIJFD')  # Primitive type
                )
                
                if is_array_or_primitive:
                    # Log that we're skipping type plan for array/primitive
                    self.query_logs.append({
                        "query_type": f"skip_array_or_primitive_{var}",
                        "jvm_type": jvm_type,
                        "status": "skipped_type_plan",
                    })
                    # Still add to result but with empty plan
                    result["objects"].append({
                        "variable": var,
                        "type": jvm_type,
                        "newObject": new_object,
                        "plan": {
                            "type": {"jvm": jvm_type, "class": self._decode_jvm_type(jvm_type) or jvm_type},
                            "constructors": [],
                            "fields": {},
                            "ctor_children": {},
                        },
                    })
                    continue
                
                type_plan = self._collect_type_plan(jvm_type, seen_types)
                result["objects"].append({
                    "variable": var,
                    "type": jvm_type,
                    "newObject": new_object,
                    "plan": type_plan,
                })
            except Exception as e:
                # Log error but continue processing other variables
                self.query_logs.append({
                    "query_type": f"error_processing_{var}",
                    "from_jvm": jvm_type,
                    "status": "error",
                    "error": str(e),
                })
                # Still add the object even if type plan collection failed
                result["objects"].append({
                    "variable": var,
                    "type": jvm_type,
                    "newObject": new_object,
                    "plan": {
                        "type": {"jvm": jvm_type, "class": self._decode_jvm_type(jvm_type) or jvm_type},
                        "constructors": [],
                        "fields": {},
                        "ctor_children": {},
                    },
                })

        return result

    def generate(
        self, 
        constraints: List[str], 
        heap_solver_output: Dict[str, Any],
        type_solver_output: Optional[Dict[str, Any]] = None,
        variable_static_type: Optional[Dict[str, str]] = None,
    ) -> Tuple[Dict[str, Any], str, Dict[str, Any]]:
        """
        Generate Java initialization code using LLM based on collected plans.

        Args:
            constraints: List of constraints
            heap_solver_output: Heap solver output (must contain result and valuation when SAT)
            type_solver_output: Optional type solver output to get all symbolic references
            variable_static_type: Static types of method parameters (must initialize all of them)

        Returns:
            tuple(parsed_json, raw_llm_output, log_entry)
        """
        # Reset query logs for this generation
        self.query_logs = []

        # If heap result is not SAT, return empty
        if not heap_solver_output or heap_solver_output.get("result") != "SAT":
            log_entry = {"agent": "initializer", "stage": "generate", "response": "", "error": "heap_solver not SAT"}
            return {"initialization_code": "", "plan": {}}, "heap_solver not SAT", log_entry

        init_plan = self._build_initialization_plan(
            heap_solver_output, 
            type_solver_output=type_solver_output,
            constraints=constraints,
            variable_static_type=variable_static_type,
        )

        # System prompt for code generation
        system_prompt = (
            "You are a senior Java engineer. Given a construction plan for several objects, "
            "generate Java code that constructs all symbolic objects with correct imports and "
            "clear variable assignments. Prefer using available public constructors from the plan; "
            "if no public constructors exist, use builder/static factory methods listed. "
            "Initialize nested fields according to the plan recursively. Ensure compilable code. "
            "CRITICAL: Minimize nulls. Prefer real objects/default values/empty collections. "
            "IMPORTANT: For basic types (String, wrappers), use LITERAL VALUES (e.g., String=\"example string\", int=0, Integer=42). "
            "NEVER generate String via constructors (FORBIDDEN: new String(), new String(\"\")). "
            "When choosing interface implementations (e.g., Comparable), prefer numeric types (Integer/Double/Long) over String."
        )

        import json
        constraints_block = "\n".join(f"- {c}" for c in constraints)
        plan_block = json.dumps(init_plan, indent=2, ensure_ascii=False)

        human_prompt = (
            "Constraints (context):\n" + constraints_block + "\n\n"
            "Initialization Plan (JSON):\n```json\n" + plan_block + "\n```\n\n"
            "Requirements (must follow):\n"
            "- Imports: include all needed imports, especially 'import com.google.gson.Gson;'.\n"
            "- Naming: use plan variable names but remove '(ref)' suffix in Java identifiers (e.g., plot(ref) -> plot).\n"
            "- Construction: for each plan object, pick a sensible public ctor (prefer fewer params) from the plan.\n"
            "- Abstract: if plan marks 'abstract class', DO NOT instantiate it; use a concrete subclass from 'concreteSubclassConstructors'.\n"
            "- Interface: if plan marks 'interface', DO NOT instantiate it; use a concrete impl from 'concreteImplementationConstructors'.\n"
            "  - Prefer numeric impls over String when possible (Comparable: Integer/Double/Long > String). If 'defaultImplementation' exists, prefer it.\n"
            "  - Never pass null for interface-typed parameters.\n"
            "- Null policy (critical): only use null when heap_solver explicitly requires it (reference=null). Otherwise create real objects.\n"
            "  - ALL method parameters in the plan must be initialized non-null unless heap_solver requires null.\n"
            "- Defaults:\n"
            "  - Collections: use empty collections (new ArrayList<>(), new HashSet<>(), new HashMap<>()) instead of null.\n"
            "  - Basic types: use literals, not constructors. String default is \"example string\".\n"
            "    - Only use empty string \"\" if constraints explicitly require empty string for that variable.\n"
            "    Examples: Integer p0 = 42;  String s = \"example string\";\n"
            "- Recursion: initialize complex ctor parameters using 'ctor_children' when available.\n"
            "- Output: produce ONLY one Java code block wrapped in ```java ... ```.\n"
            "- Serialization at end of main: serialize each created object with Gson and print one JSON per line:\n"
            "  {\"variable\":\"<var_from_plan>\",\"object\":<gson.toJson(var_without_ref)>}\n"
            "  Use GsonBuilder + ExclusionStrategy to skip java.text/java.awt and DecimalFormat/NumberFormat exactly as below:\n"
            "  new GsonBuilder().setExclusionStrategies(new ExclusionStrategy(){\n"
            "    public boolean shouldSkipField(FieldAttributes f){ return f.getDeclaredClass().getName().startsWith(\"java.text.\") || f.getDeclaredClass().getName().startsWith(\"java.awt.\") || f.getDeclaredClass().getName().equals(\"java.text.DecimalFormat\") || f.getDeclaredClass().getName().equals(\"java.text.NumberFormat\"); }\n"
            "    public boolean shouldSkipClass(Class<?> c){ return c.getName().startsWith(\"java.text.\") || c.getName().startsWith(\"java.awt.\") || c.getName().equals(\"java.text.DecimalFormat\") || c.getName().equals(\"java.text.NumberFormat\"); }\n"
            "  }).create();\n"
            "  (Remember to import GsonBuilder, ExclusionStrategy, FieldAttributes.)\n"
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

            def _constraints_require_empty_string_for_var(
                constraints_list: List[str],
                plan_var: str,
                java_var: str,
            ) -> bool:
                """
                Best-effort heuristic: if constraints mention empty string for this variable,
                we should not force-replace empty string initializations.
                """
                for c in (constraints_list or []):
                    if not isinstance(c, str):
                        continue
                    if "\"\"" not in c:
                        continue
                    # Variable might appear as p0, 'p0', p0(ref), 'p0(ref)' etc.
                    if (plan_var and plan_var in c) or (java_var and java_var in c) or (java_var and f"'{java_var}'" in c):
                        return True
                return False

            def _enforce_string_defaults(
                java_code: str,
                init_plan_local: Dict[str, Any],
                constraints_list: List[str],
                default_literal: str = "\"example string\"",
            ) -> str:
                """
                Deterministic safeguard for common LLM slips:
                - Replace `new String()` / `new String("")` with the default literal
                - Replace `String x = ""` with default literal, unless constraints require empty for that var
                """
                if not isinstance(java_code, str) or not java_code:
                    return java_code
                import re

                objects = (init_plan_local or {}).get("objects", [])
                string_java_vars: List[Tuple[str, str]] = []
                for obj in objects:
                    if not isinstance(obj, dict):
                        continue
                    jvm_type = obj.get("type")
                    var_plan = obj.get("variable")
                    if jvm_type != "Ljava/lang/String;":
                        continue
                    if not isinstance(var_plan, str):
                        continue
                    var_java = var_plan.replace("(ref)", "")
                    string_java_vars.append((var_plan, var_java))

                # Global fix: new String() / new String("") as expressions
                java_code = re.sub(r"\bnew\s+String\s*\(\s*\)", default_literal, java_code)
                java_code = re.sub(r"\bnew\s+String\s*\(\s*\"\"\s*\)", default_literal, java_code)

                # Per-variable fix for `String x = "";`
                for var_plan, var_java in string_java_vars:
                    if _constraints_require_empty_string_for_var(constraints_list, var_plan, var_java):
                        continue
                    # String p0 = "";
                    java_code = re.sub(
                        rf"(\bString\s+{re.escape(var_java)}\s*=\s*)\"\"\s*;",
                        rf"\1{default_literal};",
                        java_code,
                    )
                    # p0 = "";
                    java_code = re.sub(
                        rf"(\b{re.escape(var_java)}\s*=\s*)\"\"\s*;",
                        rf"\1{default_literal};",
                        java_code,
                    )
                return java_code

            # Enforce string defaults to reduce flaky LLM outputs (e.g., `new String()`)
            if code_block:
                code_block = _enforce_string_defaults(code_block, init_plan, constraints)

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
