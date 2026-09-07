# AGENTS.md – Backend (Python + FastAPI)

## Project Overview
This is the backend for "Saved Content Graveyard" – an app that turns social media screenshots into actionable results.

Core flow:
1. User shares a screenshot (Instagram, TikTok, Facebook, etc.)
2. Backend receives the image
3. AI processes it → short description + relevant links
4. For products → buy links
5. For movies/TV → streaming platform links
6. Original image is deleted as soon as processing is finished (privacy first)

## Tech Stack (Do not change without discussion)
- Python 3.12+
- FastAPI
- Pydantic v2
- SQLAlchemy 2.0 or Supabase
- Google Cloud Vision / Gemini (preferred) or GPT-4o-mini for vision
- Temporary object storage (S3 / Cloudflare R2 / Supabase Storage)

## Critical Rules
- **Privacy is non-negotiable**: Process the image → return result → delete the original image immediately (or within seconds).
- Never store user screenshots permanently unless the user explicitly saves the result card.
- Always return structured JSON.
- Always include a confidence score.
- Rate limit free users aggressively.
- Prefer cheaper models first (Gemini Flash / Flash-Lite). Escalate only when necessary.
- Write clean, typed, well-documented code.
- Use async where it makes sense.
- Every endpoint must have proper error handling and logging.

## Preferred Response Format from AI Pipeline
```json
{
  "type": "product" | "movie" | "tv" | "unknown",
  "title": "string",
  "description": "short natural description (1-2 sentences)",
  "confidence": 0.0-1.0,
  "links": [
    {
      "label": "Buy on Amazon",
      "url": "https://...",
      "type": "buy" | "stream" | "info"
    }
  ],
  "metadata": {}
}
```

## Coding Standards
- Use type hints everywhere
- Prefer Pydantic models for request/response
- Keep services thin and focused
- No giant functions
- Write tests for the AI pipeline and critical paths

## Current Priority Order
1. Secure image upload + auto-delete
2. Working /analyze endpoint
3. Basic vision + description
4. Product matching
5. Movie/TV identification + streaming links