#!/usr/bin/env python3
"""
CLI tool for generating initial values for method parameters.

Usage:
    python generate_initial_values_cli.py <parameter_types_json>

Example:
    python generate_initial_values_cli.py '[{"name": "p0", "type": "java.lang.Appendable"}]'

Or read from stdin:
    echo '[{"name": "p0", "type": "java.lang.Appendable"}]' | python generate_initial_values_cli.py

Output:
    JSON object with "initialization_code" field containing Java code.
"""

import sys
import json
import os
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from langchain_openai import ChatOpenAI
from config import OPENAI_API_KEY, LLM_MODEL, BASE_URL, CLASS_PATH
from agents.initial_value_agent import InitialValueAgent


def main():
    if len(sys.argv) > 1:
        # Read from command line argument
        param_json = sys.argv[1]
    else:
        # Read from stdin
        param_json = sys.stdin.read()
    
    try:
        parameter_types = json.loads(param_json)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)
    
    if not isinstance(parameter_types, list):
        print("Error: Expected a JSON array of parameter types", file=sys.stderr)
        sys.exit(1)
    
    # Validate parameter_types structure
    for param in parameter_types:
        if not isinstance(param, dict) or "name" not in param or "type" not in param:
            print("Error: Each parameter must have 'name' and 'type' fields", file=sys.stderr)
            sys.exit(1)
    
    # Validate API key
    if not OPENAI_API_KEY:
        print("Error: OPENAI_API_KEY not configured", file=sys.stderr)
        sys.exit(1)
    
    # Initialize LLM
    llm_kwargs = {
        "temperature": 0.0,
        "max_tokens": 512,
        "model": LLM_MODEL,
        "api_key": OPENAI_API_KEY,
    }
    if BASE_URL:
        llm_kwargs["base_url"] = BASE_URL
    
    llm = ChatOpenAI(**llm_kwargs)
    
    # Initialize agent
    agent = InitialValueAgent(llm, classpath=CLASS_PATH)
    
    # Generate initialization code
    try:
        result, raw_output, log_entry = agent.generate(parameter_types)
        
        # Output result as JSON
        output_json = json.dumps(result, indent=2, ensure_ascii=False)
        print(output_json)
        
    except Exception as e:
        error_result = {
            "initialization_code": "",
            "variable_assignments": {},
            "error": str(e)
        }
        print(json.dumps(error_result, indent=2), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

