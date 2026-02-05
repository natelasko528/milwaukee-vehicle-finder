# CLAUDE.md

## Project Overview

Milwaukee Vehicle Finder is a DOOM-themed web app that searches for used vehicles across the Milwaukee area by scraping multiple automotive listing platforms (Craigslist, CarGurus, Cars.com, AutoTrader) in real-time. It features AI-powered market analysis, deal badges, and vehicle reviews via Google Gemini. Alpine.js frontend with Python serverless functions deployed on Vercel.

## Architecture

- **Frontend**: Single-page app (`index.html`) using Alpine.js v3 for reactivity, no build step
- **Backend**: Python serverless functions in `api/` deployed on Vercel
- **Shared utils**: `api/utils/` provides CORS, JSON response helpers, and rate limiting
- **No database**: All data fetched fresh; localStorage for saved searches, favorites, sort preference
- **No auth**: Public-facing, no user accounts

```
├── index.html                 # Main frontend SPA (Alpine.js, ~180KB)
├── api/
│   ├── search/
│   │   └── index.py           # Search endpoint - scrapes 4 platforms concurrently
│   ├── details.py             # Vehicle detail/image extraction (SSRF-protected)
│   ├── review.py              # AI vehicle review endpoint (Gemini)
│   ├── safety.py              # AI safety analysis endpoint (Gemini)
│   └── utils/
│       ├── __init__.py
│       ├── response.py        # cors_headers(), send_json(), send_options(), error_response()
│       └── rate_limit.py      # RateLimiter class (in-memory, per-IP)
├── tests/
│   ├── test_utils.py          # 35 unit tests (extract, validate, SSRF)
│   └── e2e/
│       ├── conftest.py        # Playwright fixtures (HTTP server, base_url)
│       ├── test_app.py        # 20 E2E tests (page load, a11y, chat, responsive, features)
│       └── test_server_fixture.py
├── tasks/
│   ├── prd-production-readiness.md  # PRD: 20 user stories across 5 phases
│   └── tasks.json                   # 22 task definitions (TASK-001 through TASK-022)
├── .claude/
│   └── skills/
│       └── agent-main.md      # Custom orchestration skill (ULTRATHINK, PRD generation)
├── .github/workflows/ci.yml   # CI: flake8 lint + pytest on push/PR
├── requirements.txt           # Production deps (aiohttp, bs4, lxml)
├── requirements-dev.txt       # Dev deps (pytest, flake8, playwright)
├── .env.example               # Documents GOOGLE_API_KEY requirement
├── .gitignore                 # Comprehensive (Python, IDE, OS, env, test artifacts)
├── pytest.ini                 # Test config
├── vercel.json                # Vercel config (minimal, auto-detect)
└── CLAUDE.md                  # This file
```

## Tech Stack

- **Frontend**: HTML5, CSS3, JavaScript, Alpine.js v3
- **Backend**: Python 3, aiohttp, BeautifulSoup4, lxml (Gemini via REST API, no SDK)
- **AI**: Google Gemini (market analysis, vehicle reviews, safety data, chat)
- **Testing**: pytest + Playwright (unit + E2E)
- **CI/CD**: GitHub Actions (flake8 + pytest)
- **Deployment**: Vercel (serverless Python runtime)
- **No Node.js**: No package.json, no JS build pipeline

## API Endpoints

### POST `/api/search`
Search for vehicles across all 4 platforms concurrently. Rate-limited to 10 req/min/IP. Input validated (year range 1990-2030, no negative values, numeric ZIP).

Request body:
```json
{
  "make": "Honda",
  "model": "Civic",
  "min_year": 2015,
  "max_year": 2024,
  "max_price": 20000,
  "max_mileage": 150000,
  "location": "milwaukee",
  "zip_code": "53202"
}
```

Response includes `vehicles` array, `sources` array (per-platform counts/errors), and `stats`.

### GET `/api/search`
Health check. Returns API version and status.

### GET `/api/details?url=<listing_url>`
Extract full details (images, VIN, transmission, fuel, color, description) from a specific vehicle listing URL. SSRF-protected: only allows craigslist.org, cargurus.com, cars.com, autotrader.com domains. Blocks private IPs.

## Development

### Local Setup
```bash
pip install -r requirements-dev.txt
# No local dev server - use `vercel dev` or deploy to Vercel
```

### Running Tests
```bash
# Unit tests (35 tests, no external deps)
python -m pytest tests/test_utils.py -v

# E2E tests (20 tests, requires Playwright + Chromium)
playwright install chromium
python -m pytest tests/e2e/ -v

# All tests
python -m pytest tests/ -v
```

### Deployment
Push to the repo; Vercel auto-deploys. The `vercel.json` is intentionally minimal to let Vercel auto-detect the Python runtime and route `api/` functions.

## Key Conventions

### Python (Backend)
- Shared utilities in `api/utils/` for CORS headers, JSON responses, rate limiting
- Module-level helper functions (`_extract_price`, `_extract_mileage`, `_extract_year`, `_year_ok`, `_make_id`)
- `BaseHTTPRequestHandler` subclass for the Vercel serverless handler
- All 4 scrapers run concurrently via `asyncio.gather()` with `return_exceptions=True`
- Each scraper catches its own exceptions so failures in one platform don't block others
- Input validation with descriptive HTTP 400 errors on bad input
- SSRF protection via domain whitelist + private IP blocking on details endpoint
- Rate limiting: 10 req/min/IP on search endpoint (in-memory)
- 12-second timeout per platform request
- $0-price listings are filtered out server-side

### Frontend
- Single Alpine.js component `app()` manages all state
- DOOM-themed design with WCAG AA compliant contrast (4.5:1 minimum)
- Source filtering via clickable chip buttons (All / Craigslist / CarGurus / etc.)
- Sort by price, mileage, or year (ascending/descending) with localStorage persistence
- Saved searches (up to 10, localStorage)
- Favorites/watchlist with heart toggle on vehicle cards (localStorage)
- Share button copies listing details to clipboard
- Modal fetches additional details from `/api/details` when a card is clicked
- AI features: market analysis auto-triggers after search, deal badges batch-generated, review/safety auto-fetched on modal open
- AbortController timeouts on all API calls (15-30s depending on endpoint)
- Duplicate request guards on search, chat, and modal
- Image gallery in modal with prev/next navigation
- 27 makes with per-make model dropdowns
- SVG icons (no emoji in UI), inline CSS (no external stylesheets)
- `prefers-reduced-motion` support disables animations
- ARIA labels on all icon buttons, `role="dialog"` on modal
- Responsive: mobile (single-column), tablet (2-column), desktop (3-column)
- Deferred Three.js initialization (lazy on first weapon fire)
- DocumentFragment batching for particle DOM operations

### Vercel / Deployment
- Serverless functions live under `api/` -- Vercel maps `api/search/index.py` to `/api/search`
- `vercel.json` should stay minimal; previous issues arose from over-configuring it
- `requirements.txt` at repo root is picked up automatically by Vercel
- `requirements-dev.txt` is NOT deployed (test/lint deps only)

## Important Notes

- **Scrapers are fragile**: They depend on the current HTML structure of target sites and will break when those sites change their markup. CarGurus, Cars.com, and AutoTrader are JS-heavy and may return limited results from server-side scraping.
- **GOOGLE_API_KEY** required for AI features (chat, reviews, market analysis, safety). See `.env.example`.
- **Rate limiting**: 10 searches/min/IP implemented in-memory; resets on cold start.
- **E2E tests**: Tests requiring Alpine.js CDN access will skip in offline environments (unit tests always work).
- **No stale files**: Legacy files (`backend_api.py`, `enhanced_dashboard.html`, duplicate `api/search.py`) have been removed.
