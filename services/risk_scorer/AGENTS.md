## Risk Scorer Service
- FastAPI app entry point: services/risk_scorer/main.py (port 8003)
- Rules live in: services/risk_scorer/rules/rules.py
- LLM logic lives in: services/risk_scorer/llm/
- Tests live in: tests/risk_scorer/
- Run tests with: pytest tests/risk_scorer/ -v
- POST /score is the main endpoint
- Use Pydantic models for all request/response schemas
- LLM is mocked until API key is provided — check LLM_API_KEY env var