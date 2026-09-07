# Backend Rules

- Stack: Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2.0 (or Supabase)
- Core feature: Receive screenshot → process with vision → return description + buy/stream links
- Privacy: Process image → generate result → delete original image as fast as possible
- Never store user screenshots permanently unless user explicitly saves the result
- Use structured JSON responses
- Always include confidence score
- Rate limit heavily on free tier
- Follow `api-contract.md` — it is the source of truth for the mobile app. Do not change response shapes without updating it.

# Code Standards

- Type hints on all functions
- Pydantic models for all request/response schemas
- Async/await for all I/O operations
- Proper error handling with HTTPException
- Environment variables via pydantic-settings
- Tests for all endpoints

# Architecture

- Clean separation: endpoints → services → models
- Services handle external API calls (vision, product search, streaming)
- Endpoints handle HTTP concerns only
- Use dependency injection for auth and rate limiting
