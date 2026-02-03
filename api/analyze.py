"""
API Endpoint: AI-Powered Market Analysis
Uses Google Gemini to analyze vehicle search results and provide
pricing insights, best deals, red flags, and recommendations.
Deployed as a Vercel serverless function.
"""

from http.server import BaseHTTPRequestHandler
import json
import os
import hashlib
import time
import urllib.request
import urllib.error

# ---------------------------------------------------------------------------
# In-memory caches (persist across warm invocations on the same Vercel instance)
# ---------------------------------------------------------------------------
_analysis_cache = {}          # key: hash -> {"result": ..., "ts": ...}
_CACHE_TTL = 600              # 10 minutes

_rate_limit_store = {}        # key: ip -> [timestamp, ...]
_RATE_LIMIT_WINDOW = 60       # 1 minute
_RATE_LIMIT_MAX = 20          # max requests per window

GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash"]
MAX_VEHICLES = 20


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cors_headers(handler):
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")


def _json_response(handler, status, data):
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    _cors_headers(handler)
    handler.end_headers()
    handler.wfile.write(json.dumps(data).encode())


def _cache_key(params, vehicle_count):
    """Create a deterministic hash from search params + vehicle count."""
    raw = json.dumps({
        "make": params.get("make", ""),
        "model": params.get("model", ""),
        "min_year": params.get("min_year"),
        "max_year": params.get("max_year"),
        "vehicle_count": vehicle_count,
    }, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def _check_rate_limit(ip):
    """Return True if the IP is within the rate limit, False otherwise."""
    now = time.time()
    if ip not in _rate_limit_store:
        _rate_limit_store[ip] = []

    # Prune timestamps outside the window
    _rate_limit_store[ip] = [
        ts for ts in _rate_limit_store[ip]
        if now - ts < _RATE_LIMIT_WINDOW
    ]

    if len(_rate_limit_store[ip]) >= _RATE_LIMIT_MAX:
        return False

    _rate_limit_store[ip].append(now)
    return True


def _get_client_ip(handler):
    """Best-effort client IP from headers (Vercel sets x-forwarded-for)."""
    forwarded = handler.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return handler.headers.get("x-real-ip", "unknown")


def _build_prompt(make, model, min_year, max_year, vehicles):
    """Build the Gemini prompt for market analysis."""
    vehicle_list = "\n".join(
        f"  {i+1}. {v.get('title', 'Unknown')} | "
        f"Price: ${v.get('price', 0):,} | "
        f"Mileage: {v.get('mileage', 'N/A'):,} mi | "
        f"Year: {v.get('year', 'N/A')} | "
        f"Source: {v.get('source', 'Unknown')}"
        for i, v in enumerate(vehicles)
    )

    year_range = ""
    if min_year and max_year:
        year_range = f"{min_year}-{max_year}"
    elif min_year:
        year_range = f"{min_year}+"
    elif max_year:
        year_range = f"up to {max_year}"

    return f"""You are an automotive market analyst. Analyze the following used vehicle search results for a {make} {model} ({year_range}) in the Milwaukee, WI area.

Listings:
{vehicle_list}

Provide a detailed market analysis as valid JSON only (no markdown, no code fences, no extra text). Use this exact structure:

{{
  "summary": "A 2-3 sentence market overview paragraph covering supply, typical pricing, and overall value in this segment.",
  "avg_market_price": <integer, your estimated fair average market price based on these listings>,
  "fair_price_range": "<formatted string like '$14,000 - $19,500'>",
  "best_deals": [
    {{"title": "<vehicle title from listings>", "reason": "<why this is a good deal>"}}
  ],
  "overpriced": [
    {{"title": "<vehicle title from listings>", "reason": "<why this is overpriced>"}}
  ],
  "red_flags": ["<any suspicious listings: unusually low price, very high mileage, potential scam indicators, etc.>"],
  "recommendations": "1-2 paragraph recommendation for a buyer in this market segment. Include negotiation tips and what to look for during inspection.",
  "model_year_notes": "Notes about which model years to prefer or avoid for the {make} {model}, including any known issues (e.g., recalls, common mechanical problems, redesign years)."
}}

Important:
- Identify the 1-3 best deals from the listings and explain why.
- Identify any overpriced listings and explain why.
- Flag any red flags such as suspiciously low prices relative to year/mileage, extremely high mileage, or listings that look like potential scams.
- Provide model-year specific advice relevant to the {make} {model}.
- Return ONLY the JSON object, nothing else."""


def _call_gemini(prompt, api_key):
    """Call the Gemini API, trying primary model then fallback."""
    last_error = None

    for model_name in GEMINI_MODELS:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"models/{model_name}:generateContent?key={api_key}"
        )
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 2048,
            },
        }).encode()

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode())

            # Extract the text from Gemini's response
            text = (
                body.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )

            if not text:
                last_error = f"Empty response from {model_name}"
                continue

            # Strip markdown code fences if present
            cleaned = text.strip()
            if cleaned.startswith("```"):
                # Remove opening fence (with optional language tag)
                cleaned = cleaned.split("\n", 1)[-1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            analysis = json.loads(cleaned)
            return analysis

        except (urllib.error.URLError, urllib.error.HTTPError) as e:
            last_error = f"{model_name}: {str(e)}"
            continue
        except json.JSONDecodeError as e:
            last_error = f"{model_name}: Invalid JSON in response - {str(e)}"
            continue

    raise RuntimeError(f"All Gemini models failed. Last error: {last_error}")


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        _cors_headers(self)
        self.end_headers()

    def do_GET(self):
        _json_response(self, 200, {
            "success": True,
            "message": "Market Analysis API",
            "status": "operational",
            "usage": "POST with {make, model, min_year, max_year, vehicles: [...]}",
        })

    def do_POST(self):
        client_ip = _get_client_ip(self)

        # Rate limiting
        if not _check_rate_limit(client_ip):
            _json_response(self, 429, {
                "success": False,
                "error": "Rate limit exceeded. Maximum 20 requests per minute.",
            })
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            _json_response(self, 400, {
                "success": False,
                "error": "Invalid JSON in request body.",
            })
            return

        make = data.get("make", "").strip()
        model = data.get("model", "").strip()
        min_year = data.get("min_year")
        max_year = data.get("max_year")
        vehicles = data.get("vehicles", [])

        if not make or not vehicles:
            _json_response(self, 400, {
                "success": False,
                "error": "Request must include 'make' and a non-empty 'vehicles' array.",
            })
            return

        # Truncate to MAX_VEHICLES
        vehicles = vehicles[:MAX_VEHICLES]

        # Check cache
        key = _cache_key(data, len(vehicles))
        now = time.time()
        if key in _analysis_cache:
            cached = _analysis_cache[key]
            if now - cached["ts"] < _CACHE_TTL:
                _json_response(self, 200, {
                    "success": True,
                    "analysis": cached["result"],
                    "cached": True,
                })
                return

        # Require API key
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            _json_response(self, 500, {
                "success": False,
                "error": "GOOGLE_API_KEY is not configured on the server.",
            })
            return

        # Build prompt and call Gemini
        try:
            prompt = _build_prompt(make, model, min_year, max_year, vehicles)
            analysis = _call_gemini(prompt, api_key)
        except RuntimeError as e:
            _json_response(self, 502, {
                "success": False,
                "error": f"AI analysis failed: {str(e)}",
            })
            return
        except Exception as e:
            _json_response(self, 500, {
                "success": False,
                "error": f"Unexpected error during analysis: {str(e)}",
            })
            return

        # Store in cache
        _analysis_cache[key] = {"result": analysis, "ts": now}

        # Evict stale entries
        stale_keys = [
            k for k, v in _analysis_cache.items()
            if now - v["ts"] >= _CACHE_TTL
        ]
        for k in stale_keys:
            del _analysis_cache[k]

        _json_response(self, 200, {
            "success": True,
            "analysis": analysis,
            "cached": False,
        })
