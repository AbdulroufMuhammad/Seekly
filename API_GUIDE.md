# Seekly — Developer Guide

Internal API for structured web search, page extraction, and LLM-synthesized
answers. This guide is for the ~16 devs integrating it into their own apps.
For architecture/deployment details, see `README.rst` and `DEPLOY.md`.

## 1. Get an API key

1. Open the dashboard (ask whoever runs it for the URL — see `dashboard/README.md`
   if you're the one setting it up).
2. Sign up with your email (`POST /v1/auth/signup` under the hood) — you get
   your own account, not a shared login.
3. Click **New API key**, give it a name (e.g. `my-app-prod`), optionally set
   a rate limit, and create it.
4. **Copy the key now.** It's shown once (`sk_live_...`) and never again —
   only its hash is stored server-side. If you lose it, revoke it and make a
   new one.

Prefer curl over the dashboard? Same two calls it makes internally:

```bash
curl -X POST https://<api-host>/v1/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "at-least-8-chars"}'
# -> {"access_token": "<jwt>", "token_type": "bearer"}

curl -X POST https://<api-host>/v1/keys \
  -H "Authorization: Bearer <jwt>" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-app-prod"}'
# -> {"id": "...", "key": "sk_live_...", ...}
```

One account can hold multiple keys — make a separate one per app/environment
(`my-app-dev`, `my-app-prod`, ...) rather than sharing a single key, so you
can revoke or resize one app's access without touching another's.

## 2. Authenticate your requests

Every call to `/v1/search` or `/v1/extract` needs your key in **one** of:

```
X-API-Key: sk_live_...
```
or
```
Authorization: Bearer sk_live_...
```

`/v1/health` needs no auth. `/v1/auth/*` and `/v1/keys*` use your **JWT**
(from login/signup), not the API key — those are account-management calls,
not search calls.

Don't hardcode the key in source — read it from an env var / secrets store
in your app, same as any other credential.

## 3. Search

```
GET /v1/search
```

| Param            | Type    | Default | Notes                                                                 |
|-------------------|---------|---------|------------------------------------------------------------------------|
| `q`               | string  | —       | required                                                                |
| `max_results`     | int     | 10      | 1–50                                                                    |
| `categories`      | string  | —       | comma-delimited, upstream SearXNG categories (e.g. `news,science`)     |
| `expand`          | bool    | false   | fan out to `<q> news` + `<q> latest`, merge & re-rank                  |
| `include_answer`  | bool    | false   | LLM-synthesized answer over the top results (costs a DeepSeek call — see §5) |

```bash
curl "https://<api-host>/v1/search?q=rust%20async%20runtimes&max_results=5" \
  -H "X-API-Key: sk_live_..."
```

```json
{
  "query": "rust async runtimes",
  "answer": null,
  "results": [
    {
      "title": "...",
      "url": "https://...",
      "content": "...",
      "published_at": "2025-01-02T12:00:00Z",
      "score": 2.3,
      "relevance_score": 0.87,
      "authority_score": 0.74,
      "freshness_score": 0.61,
      "content_quality_score": 0.91,
      "duplicate_penalty": 0.0,
      "final_score": 0.89
    }
  ],
  "response_time": 0.233
}
```

Results are pre-sorted by `final_score` (highest first) — you generally
don't need to re-rank client-side. `final_score` is deterministic (relevance
+ authority + freshness + content quality, minus a duplicate penalty), not
an LLM judgment, so it's stable and reproducible across calls.

Responses are cached server-side (~5 min by default, see `X-Cache: HIT|MISS`
response header) — identical repeated queries are cheap, so don't build your
own caching layer on top unless you need longer TTLs.

## 4. Extract a page

```
GET /v1/extract?url=<url>&query=<optional>&max_passages=<optional>
```

```bash
curl "https://<api-host>/v1/extract?url=https://example.com/article&query=pricing" \
  -H "X-API-Key: sk_live_..."
```

Returns cleaned page content/metadata. Pass `query` to get keyword-aware,
relevance-ranked passages instead of the raw dump — useful when you only
want the part of a long page relevant to what you're looking for.

## 5. LLM-synthesized answers (`include_answer=true`)

By default `answer` is only populated when SearXNG's own upstream
infobox/instant-answer has something. Set `include_answer=true` to instead
get a real synthesized answer (via DeepSeek) generated from the top results:

```bash
curl "https://<api-host>/v1/search?q=what%20is%20the%20capital%20of%20france&include_answer=true" \
  -H "X-API-Key: sk_live_..."
```

This costs an extra LLM call, so:
- Leave it `false` for anything where you only need the result list.
- It fails soft — if DeepSeek is down or not configured server-side, you
  still get a normal search response with `answer: null`, not an error.
- Identical `(query, include_answer=true)` calls hit the cache like any
  other search, so repeat queries don't re-bill DeepSeek.

## 6. Rate limits

Each key has its own `requests/minute` limit (see it / change it from the
dashboard, or `GET /v1/keys`). Go over it and you get:

```
HTTP 429
Retry-After: <seconds, max 60>
```

There's no penalty box — the next 60-second window resets to full quota
automatically. Handle it like any `429`: back off for `Retry-After` seconds
and retry, don't hammer.

If your app legitimately needs a higher steady-state rate (a batch job,
high-traffic service), set a higher `rate_limit_per_minute` on that key's
own row rather than working around 429s — see the dashboard's "Edit limit"
or `PATCH /v1/keys/{id}`.

## 7. Errors

| Status | Meaning                                              | What to do                                  |
|--------|-------------------------------------------------------|-----------------------------------------------|
| 400    | bad request (e.g. empty `q`)                          | fix the request                               |
| 401    | missing/invalid/revoked API key, or bad JWT            | check your key; re-login for JWT endpoints    |
| 404    | key not found (on `/v1/keys/{id}` — wrong id or not yours) | check the id                               |
| 422    | validation error (bad param shape), or extract found no content | fix input / expected for some URLs |
| 429    | rate limited                                           | back off `Retry-After` seconds, retry         |
| 502    | upstream (SearXNG) unavailable                         | transient — retry with backoff                |

Error bodies are `{"detail": "..."}`.

## 8. Code samples

**Python (`requests`):**

```python
import os
import requests

API_KEY = os.environ["SEEKLY_API_KEY"]
BASE_URL = "https://<api-host>"

resp = requests.get(
    f"{BASE_URL}/v1/search",
    params={"q": "rust async runtimes", "max_results": 5},
    headers={"X-API-Key": API_KEY},
    timeout=30,
)
resp.raise_for_status()
data = resp.json()
for r in data["results"]:
    print(r["final_score"], r["title"], r["url"])
```

**Node / JS (`fetch`):**

```js
const API_KEY = process.env.SEEKLY_API_KEY;
const BASE_URL = "https://<api-host>";

const params = new URLSearchParams({ q: "rust async runtimes", max_results: "5" });
const resp = await fetch(`${BASE_URL}/v1/search?${params}`, {
  headers: { "X-API-Key": API_KEY },
});
if (!resp.ok) {
  if (resp.status === 429) {
    const retryAfter = resp.headers.get("Retry-After");
    // back off and retry
  }
  throw new Error(`search failed: ${resp.status}`);
}
const data = await resp.json();
```

## 9. Good practices

- One key per app/environment, not one shared key for everything — makes
  revocation and quota changes safe and scoped.
- Read the key from config/secrets, never commit it.
- Use `include_answer=true` only where you actually show a synthesized
  answer — it's the one param that costs an external LLM call.
- Treat `429` as expected, not exceptional — handle it, don't alert-page on it.
- If you're decommissioning an app, revoke its key from the dashboard
  rather than leaving it live.

## Questions / issues

Ping whoever's running the instance, or open an issue in this repo.
