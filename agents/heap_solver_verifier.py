"""
Heap Solver Verifier - Validates heap_solver results (without using LLM).

Responsibilities:
1. Validate JSON format compliance
2. Validate variable name legality (must come from constraints)
3. Validate compliance with type_solver results
"""

from typing import List, Dict, Optional, Any


class HeapSolverVerifier:
    """
    Validates heap_solver results (without using LLM).
    
    Input:
    - constraints: List[str]
    - heap_solver_output: Dict
    - type_solver_output: Dict
    
    Output:
    {
        "is_well_formed": bool,
        "errors": [
            {
                "error_type": str,
                "location": str,
                "message": str
            }
        ]
    }
    """
    
    def verify(
        self,
        constraints: List[str],
        heap_solver_output: Optional[Dict],
        type_solver_output: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Verify heap_solver output.
        
        Args:
            constraints: List of constraints
            heap_solver_output: heap_solver output
            type_solver_output: type_solver output (for consistency validation)
        
        Returns:
            Verification result dictionary containing is_well_formed and errors
        """
        errors = []
        
        # Check JSON format
        if heap_solver_output is None:
            errors.append({
                "error_type": "INVALID_JSON",
                "location": "root",
                "message": "Cannot parse JSON format"
            })
            return {
                "is_well_formed": False,
                "errors": errors
            }

        # Defensive: the JSON extractor may return a list if it accidentally parsed something.
        # Verifiers must never crash; treat it as malformed output.
        if not isinstance(heap_solver_output, dict):
            errors.append({
                "error_type": "INVALID_TYPE",
                "location": "root",
                "message": f"Expected object at root, got {type(heap_solver_output)}"
            })
            return {
                "is_well_formed": False,
                "errors": errors
            }
        
        # Check result field
        if "result" not in heap_solver_output:
            errors.append({
                "error_type": "MISSING_FIELD",
                "location": "result",
                "message": "Missing 'result' field"
            })
        else:
            result = heap_solver_output.get("result")
            if result not in ["SAT", "UNSAT", "UNKNOWN"]:
                errors.append({
                    "error_type": "INVALID_VALUE",
                    "location": "result",
                    "message": f"Invalid result value: {result}"
                })
        
        # If SAT, check valuation
        if heap_solver_output.get("result") == "SAT":
            if "valuation" not in heap_solver_output:
                errors.append({
                    "error_type": "MISSING_FIELD",
                    "location": "valuation",
                    "message": "SAT result missing 'valuation' field"
                })
            else:
                valuation = heap_solver_output.get("valuation")
                if not isinstance(valuation, list):
                    errors.append({
                        "error_type": "INVALID_TYPE",
                        "location": "valuation",
                        "message": f"'valuation' should be an array, got {type(valuation)}"
                    })
                else:
                    # Extract variables from constraints
                    base_variables = self._extract_variables_from_constraints(constraints)
                    
                    # Build type_solver variable type mapping
                    type_solver_type_map = {}
                    if type_solver_output and type_solver_output.get("result") == "SAT":
                        type_valuation = type_solver_output.get("valuation", [])
                        for entry in type_valuation:
                            if isinstance(entry, dict) and "variable" in entry and "type" in entry:
                                type_solver_type_map[entry["variable"]] = entry["type"]
                    
                    # Check each valuation entry
                    for idx, entry in enumerate(valuation):
                        if not isinstance(entry, dict):
                            errors.append({
                                "error_type": "INVALID_TYPE",
                                "location": f"valuation[{idx}]",
                                "message": f"Valuation entry {idx} is not a dict"
                            })
                            continue
                        
                        # Check variable field
                        if "variable" not in entry:
                            errors.append({
                                "error_type": "MISSING_FIELD",
                                "location": f"valuation[{idx}].variable",
                                "message": f"Valuation entry {idx} missing 'variable' field"
                            })
                        else:
                            var_name = entry.get("variable")
                            # Check if variable name comes from constraints
                            if var_name not in base_variables:
                                errors.append({
                                    "error_type": "INVALID_VARIABLE",
                                    "location": f"valuation[{idx}].variable",
                                    "message": f"Variable '{var_name}' not in constraints"
                                })
                            
                            # Check if type matches type_solver
                            if type_solver_type_map and var_name in type_solver_type_map:
                                expected_type = type_solver_type_map[var_name]
                                actual_type = entry.get("type")
                                if actual_type != expected_type:
                                    errors.append({
                                        "error_type": "TYPE_MISMATCH",
                                        "location": f"valuation[{idx}].type",
                                        "message": f"Type mismatch: expected {expected_type} (from type_solver), got {actual_type}"
                                    })
                        
                        # For reference variables, check required fields
                        if "type" in entry and entry["type"] != "null":
                            required_ref_fields = {"type", "newObject", "trueRef", "reference"}
                            entry_keys = set(entry.keys())
                            missing_fields = required_ref_fields - entry_keys
                            if missing_fields:
                                errors.append({
                                    "error_type": "MISSING_FIELD",
                                    "location": f"valuation[{idx}]",
                                    "message": f"Valuation entry {idx} missing fields: {missing_fields}"
                                })
        
        return {
            "is_well_formed": len(errors) == 0,
            "errors": errors
        }
    
    def _extract_variables_from_constraints(self, constraints: List[str]) -> set:
        """
        Extract all variable names from constraints.
        
        Args:
            constraints: List of constraints
        
        Returns:
            Set of variable names
        """
        import re
        variables = set()
        
        # Match variable references: varname(ref) or varname(ref).field(ref)...
        pattern = r"\b([a-zA-Z_][a-zA-Z0-9_]*(?:\(ref\))?(?:\.[a-zA-Z_][a-zA-Z0-9_]*\(ref\))*)"
        
        for constraint in constraints:
            matches = re.findall(pattern, constraint)
            for match in matches:
                if '(ref)' in match:
                    variables.add(match)
        
        return variables
