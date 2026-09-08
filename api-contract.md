# API Contract — Saved Content Graveyard

Shared contract between `saved-content-graveyard-backend` and `saved-content-graveyard-mobile`.
The backend (FastAPI + OpenAPI at `/openapi.json`) is the source of truth.

Base URL: `http://localhost:8000` (dev) — always versioned under `/v1`.

## Authentication

JWT Bearer token. `POST /v1/auth/token` is the OAuth2 password flow
(`tokenUrl = /v1/auth/token`), but the primary flows are JSON signup/login below.

- `POST /v1/auth/signup` — create account → `201` with `{access_token, token_type, user}`
- `POST /v1/auth/login` — JSON credentials → `200` with `{access_token, token_type, user}`
- `GET /v1/auth/me` — current user → `200` with `{user}`, `401` if invalid/missing
  token, `404` if the token references a nonexistent user, `403` if inactive user
- `DELETE /v1/auth/me` — permanently deletes the account and all saved result
  cards in one transaction → `200 {"message": "Account deleted successfully"}`;
  `404` if the token's user no longer exists. The token becomes invalid.
- `POST /v1/auth/logout` — invalidates the token (stored in a deny list) → `200`
- `POST /v1/auth/token` — OAuth2 form flow → `{access_token, token_type}`

Credentials validation: `email` must be a valid address, `password` 6–128 chars.
Signup errors: `400` (bad payload), `409` (email already registered).
Login errors: `401` (invalid credentials). Tokens expire after `ACCESS_TOKEN_EXPIRE_MINUTES`.

`UserPublic` / `user` object:

```json
{
  "id": "uuid",
  "email": "string",
  "full_name": "string|null",
  "is_active": true,
  "is_pro": false,
  "created_at": "ISO 8601"
}
```

## Analyze Screenshot

`POST /v1/analyze/` — multipart form. Requires `Authorization: Bearer <token>`.

Form field: `file` (image, max 10MB). Accepted real image formats (validated by
magic bytes, not just the declared content type): `png`, `jpeg`, `webp`.

Response `200`:

```json
{
  "saved_id": "uuid",
  "type": "product",
  "title": "Dr. Martens 1460 Pascal",
  "description": "A black leather boot from Dr. Martens shown in an Instagram ad.",
  "confidence": 0.92,
  "links": [
    {"label": "Buy on Amazon", "url": "https://...", "type": "buy"},
    {"label": "Search for 'Dr. Martens'", "url": "https://google.com/search?q=...", "type": "info"}
  ],
  "metadata": {
    "raw_text": "...",
    "detected_items": ["..."],
    "processing_time_ms": 1200
  }
}
```

The result card is persisted automatically to the user's library on success;
`saved_id` references it (retrievable/deletable via `/v1/library/{saved_id}`).

`type` enum: `product | movie | tv | unknown`

`links[].type` enum: `buy | stream | info`

Errors:
- `400` — not an allowed image type / exceeds 10MB / not a valid image
- `401` — invalid token
- `403` — admin access required (cleanup endpoint only)
- `429` — rate limit exceeded (free tier: 10/min, pro tier: 100/min in production)
- `500` — processing failure

The original image is deleted server-side immediately after processing (finally block).

## Analyze Batch

`POST /v1/analyze/batch` — multipart form, up to 5 files.

Response `200`: array of up to 5 `AnalyzeResponse` objects (i.e. each includes a
`saved_id` — same shape as the single `/v1/analyze/` response). Invalid files are
skipped, not fatal. Each successful card is auto-persisted to the user's library;
if persisting a card fails, that file is skipped and logged, and the rest continue.

## Library (result cards)

Auth required (`Bearer` token). Ownership enforced: users can only read/delete
their own saved cards. Auth errors follow the shared convention: `401` invalid/missing
token, `404` token references a nonexistent user, `403` inactive user.

- `GET /v1/library/?offset=0&limit=50` — newest first; `limit` max 100.
  Response: array of `SavedResult` (see below). `X-Total-Count` header carries
  the full count for pagination.
- `POST /v1/library/` — save a result card; body is a `PipelineResult`.
  → `201` with the created `SavedResult`.
- `GET /v1/library/{item_id}` — single card → `200`, `404` if not owned/exists.
- `DELETE /v1/library/{item_id}` — hard delete → `200 {"status": "deleted"}`.

`SavedResult`:

```json
{
  "id": "uuid",
  "user_id": "uuid",
  "type": "product",
  "title": "string",
  "description": "string",
  "confidence": 0.92,
  "links": [],
  "metadata": {},
  "thumbnail_url": null,
  "created_at": "ISO 8601",
  "updated_at": "ISO 8601"
}
```

## Admin

- `POST /v1/analyze/cleanup` — trigger orphan temp-file cleanup. Requires admin
  token (`user.email == ADMIN_USERNAME`). → `{"removed": int, "active": int}`,
  `403` for non-admins.

## Health

`GET /health` → `{"status": "healthy", "version": "0.1.0", "database": "ok"}`
(canary: the database is pinged; `503` with `status: "degraded"` when it is down).

`GET /health/auth` — protected probe (`Bearer` token required, active user only)
→ `{"status": "ok", "user_id": "...", "email": "..."}`. `401` missing/invalid
token, `403` inactive user, `404` token references a nonexistent user.

## Field Conventions

- All responses are structured JSON.
- Confidence is always present as a float 0.0–1.0.
- Timestamps: ISO 8601 with timezone.
- Unknown/empty lists are `[]`, never `null`.
- Empty result type is `"unknown"` with low confidence — a real fallback, not an error.
- Errors use `detail`:

```json
{"detail": "Rate limit exceeded. Please try again later."}
```

## Privacy Rules (backend, non-negotiable)

- Image deleted immediately after analysis completes (finally block).
- Never persisted unless the user explicitly saves the result (library POST).
- Orphan temp files swept after 30s; cleanup endpoint triggers it manually.
- No user screenshots stored permanently.

## Mobile Implementation Notes

- Send via multipart as field `file` (png/jpeg/webp only).
- Attach JWT as `Authorization: Bearer <token>` for all endpoints except health/signup/login.
- Show loading → then Result Card mapping the JSON fields 1:1 (`type`, `title`,
  `description`, `confidence`, `links`).
- Handle `429` with a "try again later" state.
- Image deletion is server-side and automatic — no client action needed.