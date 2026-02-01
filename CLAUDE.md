# CLAUDE.md

## Project Overview

Milwaukee Vehicle Finder is a web app that searches for used vehicles across the Milwaukee area by scraping multiple automotive listing platforms (Craigslist, CarGurus, Cars.com, AutoTrader) in real-time. It uses an Alpine.js frontend and Python serverless functions deployed on Vercel.

## Architecture

- **Frontend**: Single-page app (`index.html`) using Alpine.js v3 for reactivity, no build step
- **Backend**: Python serverless functions in `api/` deployed on Vercel
- **No database**: All data is fetched fresh on each search request
- **No auth**: Public-facing, no user accounts

```
├── index.html                 # Main frontend SPA (~1,133 lines, Alpine.js)
├── api/
│   ├── search/
│   │   └── index.py           # Search endpoint (~500 lines) - scrapes 4 platforms concurrently
│   └── details.py             # Vehicle detail/image extraction endpoint (~349 lines)
├── requirements.txt           # Python dependencies (aiohttp, beautifulsoup4, lxml)
├── vercel.json                # Vercel config (minimal, auto-detect)
├── README.md                  # Brief project description
└── CLAUDE.md                  # This file
```

## Tech Stack

- **Frontend**: HTML5, CSS3 (OKLCH color system), JavaScript, Alpine.js v3 (CDN)
- **Fonts**: Oxanium (weights 400–800) and Source Code Pro via Google Fonts
- **Backend**: Python 3, aiohttp 3.9.1, BeautifulSoup4 4.12.2, lxml 4.9.3
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

Response:
```json
{
  "success": true,
  "count": 42,
  "vehicles": [
    {
      "id": "cl_abc1234567",
      "title": "2020 Honda Civic EX",
      "price": 15999,
      "url": "https://...",
      "source": "Craigslist",
      "location": "milwaukee",
      "mileage": 45000,
      "year": 2020,
      "image_url": "https://...",
      "scraped_at": "ISO timestamp"
    }
  ],
  "sources": [
    { "name": "Craigslist", "count": 12 },
    { "name": "CarGurus", "count": 15 },
    { "name": "Cars.com", "count": 10 },
    { "name": "AutoTrader", "count": 5 }
  ],
  "stats": {
    "total_count": 42,
    "avg_price": 16123.45,
    "min_price": 8999,
    "max_price": 22500
  },
  "search_params": { ... },
  "timestamp": "ISO timestamp"
}
```

### GET `/api/search`
Health check. Returns API version (`v4.0`) and status.

### GET `/api/details?url=<listing_url>`
Extract full details from a specific vehicle listing URL. Supports Craigslist, CarGurus, Cars.com, and AutoTrader URLs.

Response includes: `images` (array), `description`, `vin`, `transmission`, `fuel`, `drive`, `color`, `interior_color`, `condition`, `cylinders`, `type`, `title_status`, `mpg`.

## Development

### Local Setup
```bash
pip install -r requirements.txt
# No local dev server - use `vercel dev` or deploy to Vercel
```

### Deployment
Push to the repo; Vercel auto-deploys. The `vercel.json` is intentionally minimal (`{"version": 2}`) to let Vercel auto-detect the Python runtime and route `api/` functions.

### No Tests
There is currently no test suite.

## Key Conventions

### Python (Backend)

- **Handler**: `BaseHTTPRequestHandler` subclass with `do_GET`, `do_POST`, `do_OPTIONS`
- **Module-level helpers**: `_extract_price`, `_extract_mileage`, `_extract_year`, `_year_ok`, `_make_id` (MD5 hash of URL for dedup)
- **Concurrency**: All 4 scrapers run via `asyncio.gather(*tasks, return_exceptions=True)`
- **Per-scraper isolation**: Each scraper catches its own exceptions so one failure doesn't block others
- **Craigslist image fetching**: Individual listing pages fetched concurrently with `asyncio.Semaphore(5)` to extract image `data-ids`, with 4 fallback methods
- **CORS**: All responses include CORS headers via `_cors_headers()` helper
- **Timeouts**: 12-second timeout per platform request
- **Filtering**: $0-price listings filtered out server-side; results sorted by price ascending

#### Scraper Selectors (fragile, depend on site markup)
- **Craigslist**: `li.cl-static-search-result`, images via `data-ids` attribute → `https://images.craigslist.org/{id}_600x450.jpg`
- **CarGurus**: `[data-cg-ft="car-blade"]` cards, images resized to `/640x480/`
- **Cars.com**: `div.vehicle-card` elements
- **AutoTrader**: `[data-cmp="inventoryListing"]` cards, images with `?w=1920`

### Frontend

- **Single component**: `app()` function returns all reactive state, mounted on `<body x-data="app()">`
- **Theme**: OKLCH color system with CSS custom properties, dark mode toggle in header
- **Dark mode**: Persisted via `localStorage['mvf-dark']` (`'0'`/`'1'`), auto-detects system preference on first visit
- **Styling**: Industrial aesthetic — Oxanium font, sharp corners (`border-radius: 0px`), high contrast
- **All inline CSS**: No external stylesheets
- **Source filtering**: Clickable chip buttons (All / Craigslist / CarGurus / etc.)
- **Sort options**: Price, mileage, or year (ascending/descending)
- **Modal**: Fetches `/api/details` on card click, shows image gallery with prev/next navigation
- **Description formatting**: `formatDescription()` applies 25+ emoji mappings (AWD → 🔄, Clean Title → 📋✅, Leather → 💺, etc.) and auto-inserts line breaks
- **27 makes** with per-make model dropdowns
- **Responsive**: `@media (max-width: 640px)` — 2-column form, 1-column card grid
- **Image lazy loading**: `loading="lazy"` on card images

#### Key Alpine.js State
```javascript
{
  loading, searched, error,          // Search state
  allResults, filtered,              // Vehicle arrays
  activeSource, sortBy,              // Filter/sort controls
  selected, modalImages, modalImgIdx, // Modal state
  detailLoading, extraDetails,       // Detail fetch state
  darkMode,                          // Theme toggle
  params: { make, model, min_year, max_year, max_price, max_mileage, zip_code }
}
```

#### Key Methods
- `search()` — POST to `/api/search`, populate results
- `applySort()` — Filter by active source, sort by selected field
- `openModal(vehicle)` — Fetch details, populate image gallery
- `formatDescription(text)` — Emoji enrichment and line break insertion
- `toggleDark()` — Toggle dark mode, persist to localStorage

### Vercel / Deployment
- Serverless functions live under `api/` — Vercel maps `api/search/index.py` to `/api/search`
- `vercel.json` should stay minimal; previous issues arose from over-configuring it
- `requirements.txt` at repo root is picked up automatically by Vercel

## Important Notes

- **Scrapers are fragile**: They depend on the current HTML structure of target sites and will break when those sites change their markup. CarGurus, Cars.com, and AutoTrader are JS-heavy and may return limited results from server-side scraping.
- **No environment variables** are required for basic operation.
- **Rate limiting**: No rate limiting is implemented; each search triggers live HTTP requests to external sites.
- **No stale files**: Legacy files (`backend_api.py`, `enhanced_dashboard.html`, duplicate `api/search.py`) have been removed.
- **Vehicle IDs**: MD5 hash of listing URL (prefix + 10 chars, e.g., `cl_abc12345`) for cross-platform deduplication.
- **Error logging**: Scrapers log errors via `print()` (captured by Vercel as stderr).
