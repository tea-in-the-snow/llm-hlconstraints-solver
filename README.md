LLM HL-Constraints Solver
=========================

FastAPI service that drives a LangChain-powered multi-agent workflow to solve Java high-level constraints (type + heap) using an OpenAI-compatible LLM.

Overview
--------
- Pipeline: type_solver → type_solver_verifier → heap_solver → heap_solver_verifier, with refiner retries (max 2) on verifier failures.
- Inputs: constraints, optional type hierarchy, variable static types, heap state, and source context. Reference text from ctx.md is auto-injected if present.
- Outputs: SAT/UNSAT/UNKNOWN plus valuations from the heap solver.
- Logging: every request/response and agent conversation is written to log/YYYY-MM-DD-n/*.md.

Setup
-----
1) Python 3.10+, create env and install deps:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
2) Configure .env (required):
```
OPENAI_API_KEY=sk-...
```
Optional overrides in config.py: LLM_MODEL (default deepseek-chat), BASE_URL (default https://api.deepseek.com/v1).

Run
---
```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

API
---
- POST /solve
- Request fields:
  - constraints: list[str] (required)
  - type_hierarchy: dict[str,str] (optional)
  - variable_static_type: dict[str,str] (optional)
  - heap_state: {aliases, objects} (optional)
  - source_context: method/class source info (optional)
  - max_tokens (default 512), temperature (default 0.0)
- Response fields:
  - result: SAT | UNSAT | UNKNOWN
  - valuation: list[dict] when SAT (heap-level valuation aligned to type solver output)
  - error: string on failures

Logging
-------
- Files are grouped per session under log/DATE-INDEX/ with request, response, and agent prompts/responses.

Notes
-----
- Type solver decides variable types; heap solver must respect them and augments with reference info.
- If OPENAI_API_KEY is missing, the service returns UNKNOWN with an error.
