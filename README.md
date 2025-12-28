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
**Basic (single process, async):**
```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

**Multi-process (recommended for production):**
```bash
# Using start script (auto-detects CPU count)
./start_server.sh

# Or manually with multiple workers
uvicorn app:app --host 0.0.0.0 --port 8000 --workers 4

# Custom configuration
WORKERS=4 PORT=8000 ./start_server.sh
```

**Concurrency Configuration:**
Set environment variables in `.env` or `config.py`:
- `MAX_CONCURRENT_REQUESTS`: Maximum concurrent requests per worker (0 = unlimited, default: 0)
- `THREAD_POOL_SIZE`: Thread pool size for async operations (0 = use default, default: 0)

**API Rate Limiting (Important for preventing 429 errors):**
- `API_RATE_LIMITING_ENABLED`: Enable/disable rate limiting (default: true)
- `API_REQUESTS_PER_MINUTE`: Maximum requests per minute to LLM API (default: 60)
- `API_REQUESTS_PER_SECOND`: Maximum requests per second (0 = no limit, default: 0)
- `API_MAX_RETRIES`: Maximum retries for 429 errors (default: 3)

Example `.env`:
```
OPENAI_API_KEY=sk-...
MAX_CONCURRENT_REQUESTS=10
THREAD_POOL_SIZE=16
API_REQUESTS_PER_MINUTE=60
API_REQUESTS_PER_SECOND=2
API_MAX_RETRIES=3
```

**Performance Tips:**
- For CPU-bound tasks: Use `--workers` equal to CPU count
- For I/O-bound tasks (LLM API calls): Use more workers (CPU count * 2-4)
- **Important**: Set `API_REQUESTS_PER_MINUTE` based on your API provider's limits:
  - OpenAI: 60-3500 req/min (depends on tier)
  - DeepSeek: ~60 req/min (free tier)
  - Other providers: Check their documentation
- Rate limiting automatically retries on 429 errors with exponential backoff
- Limit `MAX_CONCURRENT_REQUESTS` to avoid overwhelming the API
- Adjust `THREAD_POOL_SIZE` based on expected concurrent operations

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
