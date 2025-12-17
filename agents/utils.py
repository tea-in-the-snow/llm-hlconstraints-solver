"""
Utility functions for the multi-agent constraint solving system.

Provides JSON extraction and parsing utilities that handle various
output formats from LLMs, including Markdown code blocks.
"""

import json
import re
from typing import Any, Optional, Tuple, List
from json import JSONDecodeError


def extract_first_json(text: str) -> Tuple[Optional[Any], Optional[str]]:
    """
    Extract the first valid JSON object/array from text.
    
    Safeguards:
    - Prefers content inside Markdown code fences (``` or ```json) to avoid 
      stray braces like `{x}` in prose
    - Falls back to scanning the whole text if no fenced block is present
    - Uses JSONDecoder for non-greedy, position-based decoding
    
    Args:
        text: Raw text that may contain JSON
        
    Returns:
        Tuple of (parsed_json, json_string) or (None, None) if no valid JSON found
        
    Examples:
        >>> extract_first_json("Result: ```json\\n{\"result\": \"SAT\"}\\n```")
        ({'result': 'SAT'}, '{"result": "SAT"}')
        
        >>> extract_first_json("I use {x} in reasoning. Answer: {\"result\": \"SAT\"}")
        ({'result': 'SAT'}, '{"result": "SAT"}')
    """
    
    def _candidate_blocks(src: str) -> List[str]:
        """Extract code fence blocks if present, otherwise return full text.

        Note: We only treat plain fences (``` ... ```) and explicit JSON fences (```json ... ```)
        as candidates. This avoids accidentally parsing Java/Python code fences.
        """
        blocks = re.findall(r"```(?:json)?\s*(.*?)```", src, flags=re.DOTALL | re.IGNORECASE)
        return blocks if blocks else [src]
    
    decoder = json.JSONDecoder()
    
    for block in _candidate_blocks(text):
        # Scan each character looking for JSON start.
        # Important: guard against accidentally treating Java array syntax like `int[]` as JSON `[]`.
        for idx, ch in enumerate(block):
            if ch == "{":
                try:
                    obj, end = decoder.raw_decode(block, idx)
                    return obj, block[idx:end]
                except JSONDecodeError:
                    continue
            if ch == "[":
                # Skip empty arrays that commonly appear in Java type syntax: `int[]`
                if block[idx:idx+2] == "[]":
                    continue
                try:
                    obj, end = decoder.raw_decode(block, idx)
                    # Also skip parsed empty list, which is almost never a full solver response.
                    if obj == []:
                        continue
                    return obj, block[idx:end]
                except JSONDecodeError:
                    continue
    
    return None, None
