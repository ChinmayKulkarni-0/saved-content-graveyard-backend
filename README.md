# Saved Content Graveyard - Backend

A FastAPI backend that processes screenshots to identify content and return relevant links for purchasing products or streaming media.

## Features

- Screenshot analysis via AI vision APIs
- Product identification and buy links
- Movie/show identification and streaming links
- User library for saved results
- Rate limiting on free tier
- Privacy-first: images deleted immediately after processing

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
uvicorn app.main:app --reload
```

## API Docs

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
