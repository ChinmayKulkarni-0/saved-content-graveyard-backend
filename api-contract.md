# API Contract — Saved Content Graveyard

Shared contract between `saved-content-graveyard-backend` and `saved-content-graveyard-mobile`.
The backend is the source of truth. The mobile app implements this exactly.

Base URL: `http://localhost:8000` (dev) — always versioned under `/v1`.

---

## Endpoints

### Health

`GET /health`

```json
{
  "status": "healthy",
  "version": "0.1.0"
}
```

### Auth

`POST /v1/auth/token` — OAuth2 password flow.

Request (form-urlencoded):
- `username`: string
- `password`: string

Response `200`:

```json
{
  "access_token": "string",
  "token_type": "bearer"
}
```

---

### Analyze Screenshot

`POST /v1/analyze/` — multipart form. Requires `Authorization: Bearer <token>`.

Form field: `file` (image: png/jpg/webp, max 10MB)

Response `200`:

```json
{
  "id": "string",
  "description": "Dr. Martens 1460 Pascal Virginia Boots",
  "confidence": 0.92,
  "category": "product",
  "raw_text": "optional extracted OCR text",
  "product_links": [
    {
      "title": "string",
      "price": "$149.00",
      "url": "https://...",
      "source": "Amazon",
      "confidence": 0.95
    }
  ],
  "streaming_links": [
    {
      "title": "string",
      "platform": "Netflix",
      "url": "https://...",
      "type": "subscription",
      "confidence": 0.88
    }
  ],
  "tags": ["boots", "fashion"],
  "processing_time_ms": 1200
}
```

`category` enum: `product | movie | show | restaurant | location | unknown`

`streaming_links.type` enum: `subscription | rent | buy`

Errors:
- `400` — not an image / too large
- `401` — invalid token
- `429` — rate limit exceeded (free tier: 10/min)
- `500` — processing failure

---

### Analyze Batch

`POST /v1/analyze/batch` — multipart form, up to 5 files.

Response `200`: array of the same `AnalysisResult` objects above.

---

### Library

`GET /v1/library/` — list saved items (auth required):

```json
[
  {
    "id": "string",
    "description": "string",
    "category": "product",
    "confidence": 0.92,
    "raw_text": null,
    "product_links": [],
    "streaming_links": [],
    "tags": [],
    "is_deleted": false
  }
]
```

`DELETE /v1/library/{item_id}` — delete a saved item.

`POST` save from a result is not yet implemented; mobile should treat "Save" as a future call to a `/v1/library/` POST endpoint (planned, `201` + body = the saved item).

---

## Field Conventions

- All responses are structured JSON.
- **Confidence is always present** as a float 0.0–1.0.
- Timestamps: ISO 8601 with timezone.
- Unknown/empty lists are `[]`, never `null`.
- Errors use `detail`:

```json
{
  "detail": "Rate limit exceeded. Please try again later."
}
```

## Privacy Rules (backend)

- Image is deleted immediately after analysis completes (`finally` block).
- Never persisted unless the user explicitly saves the result.
- Temp files retained max 30s.

## Mobile Implementation Notes

- Send via `dio` MultipartFile as field `file`.
- Show loading → then Result Card mapping the JSON fields above 1:1.
- Handle `429` by showing a "try again later" state.
- Auth token stored client-side; attach as `Bearer` header.