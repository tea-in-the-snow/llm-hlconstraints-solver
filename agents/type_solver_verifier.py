"""
Type Solver Verifier - Validates type_solver results (without using LLM).

Responsibilities:
1. Validate JSON format compliance
2. Validate variable name legality (must come from constraints)
"""

from typing import List, Dict, Optional, Any


class TypeSolverVerifier:
    """
    Validates type_solver results (without using LLM).
    
    Input:
    - constraints: List[str]
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
        type_solver_output: Optional[Dict],
    ) -> Dict[str, Any]:
        """
        Verify type_solver output.
        
        Args:
            constraints: List of constraints
            type_solver_output: type_solver output
        
        Returns:
            Verification result dictionary containing is_well_formed and errors
        """
        errors = []
        
        # Check JSON format
        if type_solver_output is None:
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
        if not isinstance(type_solver_output, dict):
            errors.append({
                "error_type": "INVALID_TYPE",
                "location": "root",
                "message": f"Expected object at root, got {type(type_solver_output)}"
            })
            return {
                "is_well_formed": False,
                "errors": errors
            }
        
        # Check result field
        if "result" not in type_solver_output:
            errors.append({
                "error_type": "MISSING_FIELD",
                "location": "result",
                "message": "Missing 'result' field"
            })
        else:
            result = type_solver_output.get("result")
            if result not in ["SAT", "UNSAT", "UNKNOWN"]:
                errors.append({
                    "error_type": "INVALID_VALUE",
                    "location": "result",
                    "message": f"Invalid result value: {result}"
                })
        
        # If SAT, check valuation
        if type_solver_output.get("result") == "SAT":
            if "valuation" not in type_solver_output:
                errors.append({
                    "error_type": "MISSING_FIELD",
                    "location": "valuation",
                    "message": "SAT result missing 'valuation' field"
                })
            else:
                valuation = type_solver_output.get("valuation")
                if not isinstance(valuation, list):
                    errors.append({
                        "error_type": "INVALID_TYPE",
                        "location": "valuation",
                        "message": f"'valuation' should be an array, got {type(valuation)}"
                    })
                else:
                    # Extract variables from constraints
                    base_variables = self._extract_variables_from_constraints(constraints)
                    
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
                        
                        # Check type field
                        if "type" not in entry:
                            errors.append({
                                "error_type": "MISSING_FIELD",
                                "location": f"valuation[{idx}].type",
                                "message": f"Valuation entry {idx} missing 'type' field"
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
        # Handle both quoted and unquoted variable names
        # Pattern 1: Match quoted variables: 'varname(ref)' or 'varname(ref).field(ref)'
        pattern_quoted = r"'([a-zA-Z_][a-zA-Z0-9_]*(?:\(ref\))?(?:\.[a-zA-Z_][a-zA-Z0-9_]*\(ref\))*)'"
        
        # Pattern 2: Match unquoted variables (backward compatibility)
        pattern_unquoted = r"\b([a-zA-Z_][a-zA-Z0-9_]*(?:\(ref\))?(?:\.[a-zA-Z_][a-zA-Z0-9_]*\(ref\))*)"
        
        for constraint in constraints:
            # First, try to match quoted variables
            matches_quoted = re.findall(pattern_quoted, constraint)
            for match in matches_quoted:
                if '(ref)' in match:
                    variables.add(match)
            
            # Then, try to match unquoted variables (avoid duplicates)
            matches_unquoted = re.findall(pattern_unquoted, constraint)
            for match in matches_unquoted:
                if '(ref)' in match and match not in variables:
                    variables.add(match)
        
        return variables
