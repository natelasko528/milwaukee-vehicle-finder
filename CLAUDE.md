# CLAUDE.md

## Project Overview

Milwaukee Vehicle Finder is a web app that searches for used vehicles across the Milwaukee area by scraping multiple automotive listing platforms (Craigslist, CarGurus, Cars.com, AutoTrader) in real-time. It uses an Alpine.js frontend and Python serverless functions deployed on Vercel.

## Architecture

- **Frontend**: Single-page app (`index.html`) using Alpine.js v3 for reactivity, no build step
- **Backend**: Python serverless functions in `api/` deployed on Vercel
- **No database**: All data is fetched fresh on each search request
- **No auth**: Public-facing, no user accounts

```
├── index.html                 # Main frontend SPA (Alpine.js)
├── api/
│   ├── search/
│   │   └── index.py           # Search endpoint - scrapes 4 platforms concurrently
│   └── details.py             # Vehicle detail/image extraction endpoint
├── requirements.txt           # Python dependencies (aiohttp, beautifulsoup4, lxml)
├── vercel.json                # Vercel config (minimal, auto-detect)
└── CLAUDE.md                  # This file
```

## Tech Stack

- **Frontend**: HTML5, CSS3, JavaScript, Alpine.js v3
- **Backend**: Python 3, aiohttp, BeautifulSoup4, lxml
- **Deployment**: Vercel (serverless Python runtime)
- **No Node.js**: No package.json, no JS build pipeline

## API Endpoints

### POST `/api/search`
Search for vehicles across all 4 platforms concurrently.

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
Extract full details (images, VIN, transmission, fuel, color, description) from a specific vehicle listing URL. Supports Craigslist, CarGurus, Cars.com, and AutoTrader URLs.

## Development

### Local Setup
```bash
pip install -r requirements.txt
# No local dev server - use `vercel dev` or deploy to Vercel
```

### Deployment
Push to the repo; Vercel auto-deploys. The `vercel.json` is intentionally minimal to let Vercel auto-detect the Python runtime and route `api/` functions.

### No Tests
There is currently no test suite.

## Key Conventions

### Python (Backend)
- Module-level helper functions (`_extract_price`, `_extract_mileage`, `_extract_year`, `_year_ok`, `_make_id`)
- `BaseHTTPRequestHandler` subclass for the Vercel serverless handler
- All 4 scrapers run concurrently via `asyncio.gather()` with `return_exceptions=True`
- Each scraper catches its own exceptions so failures in one platform don't block others
- CORS headers on all responses via `_cors_headers()` helper
- 12-second timeout per platform request
- $0-price listings are filtered out server-side

### Frontend
- Single Alpine.js component `app()` manages all state
- Clean, light-themed design with indigo accent (`#4f46e5`)
- Source filtering via clickable chip buttons (All / Craigslist / CarGurus / etc.)
- Sort by price, mileage, or year (ascending/descending)
- Modal fetches additional details from `/api/details` when a card is clicked
- Image gallery in modal with prev/next navigation
- 27 makes with per-make model dropdowns
- SVG icons (no emoji in UI), inline CSS (no external stylesheets)
- Responsive: adapts to mobile with 2-column form and single-column cards

### Vercel / Deployment
- Serverless functions live under `api/` -- Vercel maps `api/search/index.py` to `/api/search`
- `vercel.json` should stay minimal; previous issues arose from over-configuring it
- `requirements.txt` at repo root is picked up automatically by Vercel

## Important Notes

- **Scrapers are fragile**: They depend on the current HTML structure of target sites and will break when those sites change their markup. CarGurus, Cars.com, and AutoTrader are JS-heavy and may return limited results from server-side scraping.
- **No environment variables** are required for basic operation.
- **Rate limiting**: No rate limiting is implemented; each search triggers live HTTP requests to external sites.
- **No stale files**: Legacy files (`backend_api.py`, `enhanced_dashboard.html`, duplicate `api/search.py`) have been removed.
