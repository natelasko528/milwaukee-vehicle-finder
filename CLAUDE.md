# CLAUDE.md

## Project Overview

Milwaukee Vehicle Finder is a web app that searches for used vehicles across the Milwaukee area by scraping multiple automotive listing platforms in real-time. It uses a vanilla JS frontend (Alpine.js) and Python serverless functions deployed on Vercel.

## Architecture

- **Frontend**: Single-page app (`index.html`) using Alpine.js for reactivity, no build step
- **Backend**: Python serverless functions in `api/` deployed on Vercel
- **No database**: All data is fetched fresh on each search request
- **No auth**: Public-facing, no user accounts

```
├── index.html                 # Main frontend SPA (Alpine.js)
├── enhanced_dashboard.html    # Alternative UI variant
├── backend_api.py             # Legacy Flask API (not deployed)
├── api/
│   ├── search/
│   │   └── index.py           # Main search endpoint (Vercel serverless)
│   ├── search.py              # Alternative search implementation
│   └── details.py             # Vehicle detail/image extraction endpoint
├── requirements.txt           # Python dependencies
└── vercel.json                # Vercel config (minimal, auto-detect)
```

## Tech Stack

- **Frontend**: HTML5, CSS3, JavaScript, Alpine.js v3
- **Backend**: Python 3, aiohttp, BeautifulSoup4, lxml
- **Deployment**: Vercel (serverless Python runtime)
- **No Node.js**: No package.json, no JS build pipeline

## API Endpoints

### POST `/api/search`
Search for vehicles across platforms (Craigslist, CarGurus, Cars.com, AutoTrader).

Request body:
```json
{
  "make": "Honda",
  "model": "Civic",
  "min_year": 2015,
  "max_year": 2024,
  "max_price": 20000,
  "max_mileage": 150000,
  "location": "milwaukee"
}
```

### GET `/api/search`
Health check. Returns API version and status.

### GET `/api/details?url=<listing_url>`
Extract full details and images from a specific vehicle listing URL.

## Development

### Local Setup
```bash
pip install -r requirements.txt
python backend_api.py  # runs legacy Flask server locally
```

### Deployment
Push to the repo; Vercel auto-deploys. The `vercel.json` is intentionally minimal to let Vercel auto-detect the Python runtime and route `api/` functions.

### No Tests
There is currently no test suite.

## Key Conventions

### Python
- Snake_case for functions and variables
- Class-based scrapers (`VehicleScraper`, `DetailsFetcher`)
- `BaseHTTPRequestHandler` subclasses for Vercel serverless handlers (not Flask)
- Heavy use of `asyncio` / `aiohttp` for concurrent scraping with `asyncio.gather()`
- CORS headers added manually to all responses
- Try-catch around each scraper; failures are silently skipped so other sources still return results

### Frontend
- All state lives in Alpine.js `x-data` objects
- Glassmorphism design (backdrop blur, gradients: `#667eea` → `#764ba2`)
- Built-in debug console (bottom-right toggle) with logging/copy/download
- Model dropdown auto-populates based on selected make
- Default search runs on page load (Honda Civic)

### Vercel / Deployment
- Serverless functions live under `api/` — Vercel maps `api/search/index.py` → `/api/search`
- `vercel.json` should stay minimal; previous issues arose from over-configuring it
- `requirements.txt` at repo root is picked up automatically by Vercel

## Important Notes

- **Scrapers are fragile**: They depend on the current HTML structure of target sites and will break when those sites change their markup.
- **`backend_api.py` is legacy**: The active API lives in `api/search/index.py` and `api/details.py`. The Flask-based `backend_api.py` is kept for local dev reference but is not deployed.
- **No environment variables** are required for basic operation.
- **Rate limiting**: No rate limiting is implemented; each search triggers live HTTP requests to external sites.
