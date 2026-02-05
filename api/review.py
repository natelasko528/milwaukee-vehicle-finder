"""
API Endpoint: AI-Powered Vehicle Review
Uses Google Gemini to generate detailed vehicle reviews
with reliability ratings, price assessments, known issues,
owner sentiment, recall info, and insurance estimates.
"""

from http.server import BaseHTTPRequestHandler
import json
import os
import re

# ---------------------------------------------------------------------------
# In-memory cache: keyed by "make_model_year"
# ---------------------------------------------------------------------------
_review_cache = {}

PRIMARY_MODEL = "gemini-2.5-flash"
FALLBACK_MODEL = "gemini-2.5-flash-lite"  # 2.0-flash deprecated March 2026


def _build_prompt(make, model, year, price, mileage, source=None):
    """Build the Gemini prompt requesting a structured JSON vehicle review."""
    source_context = ""
    if source:
        source_context = (
            f"\n\nThe listing is from {source}. Include a brief note about the "
            f"reputation and trustworthiness of buying from {source} as a platform "
            f"(e.g. buyer protections, common scams to watch for, dealer vs private "
            f"seller norms on that platform)."
        )

    return (
        f"You are an expert automotive analyst. Provide a detailed review of a "
        f"{year} {make} {model} that is listed at ${price:,} with {mileage:,} miles.\n\n"
        f"In addition to standard review content, please also incorporate:\n"
        f"- What real owners commonly report about this vehicle based on Consumer Reports, "
        f"Reddit (r/whatcarshouldIbuy, r/MechanicAdvice, r/cars), and enthusiast forums. "
        f"Summarize the general owner sentiment.\n"
        f"- Whether there are any active or recent NHTSA recalls for the {year} {make} {model}. "
        f"List specific recall campaigns if known, otherwise state that the buyer should check "
        f"NHTSA.gov.\n"
        f"- An estimate of annual insurance costs for this vehicle (ballpark range for an "
        f"average driver in the Milwaukee, WI area).\n"
        f"{source_context}\n\n"
        f"Respond ONLY with valid JSON (no markdown fencing, no extra text). "
        f"The JSON object must have exactly these keys:\n\n"
        f"- \"summary\": 2-3 sentence overview of this vehicle\n"
        f"- \"pros\": array of 4-6 strings, each a specific pro with detail\n"
        f"- \"cons\": array of 3-5 strings, each a specific con with detail\n"
        f"- \"reliability_rating\": number from 1 to 5 (5 = most reliable)\n"
        f"- \"reliability_summary\": 1-2 sentences on reliability for this make/model/year\n"
        f"- \"owner_sentiment\": a paragraph summarizing what real owners say on forums, "
        f"Reddit, and Consumer Reports — common praises and complaints\n"
        f"- \"fair_price_assessment\": a paragraph assessing whether ${price:,} with "
        f"{mileage:,} miles is a good deal compared to typical market prices\n"
        f"- \"price_verdict\": exactly one of: \"great_deal\", \"good_deal\", \"fair\", "
        f"\"above_market\", \"overpriced\"\n"
        f"- \"known_issues\": array of common problems for this make/model/year range\n"
        f"- \"recall_info\": a paragraph about any known active NHTSA recalls for the "
        f"{year} {make} {model}, or a note to check NHTSA.gov if uncertain\n"
        f"- \"insurance_estimate\": estimated annual insurance cost range (e.g. \"$1,200 - $1,800/year\") "
        f"with brief explanation of factors\n"
        f"- \"cost_to_own_notes\": brief notes on maintenance, insurance, and fuel costs\n"
        f"- \"platform_notes\": brief note on the listing platform's reputation and tips "
        f"for buying from it (or null if no platform was specified)\n"
    )


def _build_sources(make, model, year):
    """Construct reference links from static URL patterns."""
    make_lower = make.lower().replace(" ", "-")
    model_lower = model.lower().replace(" ", "-")
    make_upper = make.upper().replace(" ", "+")
    model_upper = model.upper().replace(" ", "+")

    return [
        {
            "name": "Edmunds",
            "url": f"https://www.edmunds.com/{make_lower}/{model_lower}/{year}/review/",
        },
        {
            "name": "Kelley Blue Book",
            "url": f"https://www.kbb.com/{make_lower}/{model_lower}/{year}/",
        },
        {
            "name": "Car and Driver",
            "url": f"https://www.caranddriver.com/{make_lower}/{model_lower}/",
        },
        {
            "name": "Consumer Reports",
            "url": f"https://www.consumerreports.org/cars/{make_lower}/{model_lower}/",
        },
        {
            "name": "NHTSA Recalls",
            "url": f"https://www.nhtsa.gov/vehicle/{year}/{make_upper}/{model_upper}",
        },
        {
            "name": "Reddit - r/whatcarshouldIbuy",
            "url": f"https://www.reddit.com/r/whatcarshouldIbuy/search/?q={make}+{model}+{year}",
        },
    ]


def _parse_gemini_response(text):
    """Parse JSON from Gemini response, handling possible markdown fencing."""
    text = text.strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strip markdown code fences if present
    fenced = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try to find first { ... } block
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    raise ValueError("Could not parse JSON from Gemini response")


def _call_gemini(prompt, api_key):
    """Call Gemini REST API with model fallback and return parsed JSON review.

    Uses direct HTTP requests (no SDK dependency). Tries the primary model
    first. If it fails, falls back to the secondary model.
    """
    import urllib.request
    import urllib.error

    models_to_try = [PRIMARY_MODEL, FALLBACK_MODEL]
    last_exception = None

    for model_name in models_to_try:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"models/{model_name}:generateContent?key={api_key}"
        )
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 4096,
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

            text = (
                body.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )

            if not text:
                last_exception = ValueError(f"Empty response from {model_name}")
                continue

            return _parse_gemini_response(text)
        except Exception as e:
            last_exception = e
            continue

    raise last_exception


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------

class handler(BaseHTTPRequestHandler):
    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json_response(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        self._json_response(200, {
            "success": True,
            "message": f"Vehicle Review API ({PRIMARY_MODEL} + {FALLBACK_MODEL} fallback)",
            "status": "operational",
            "endpoints": {
                "POST /api/review": "Get AI-powered vehicle review",
            },
        })

    def do_POST(self):
        try:
            # Parse request body
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            data = json.loads(body)

            make = data.get("make", "").strip()
            model = data.get("model", "").strip()
            year = data.get("year")
            price = data.get("price")
            mileage = data.get("mileage")
            source = data.get("source", "").strip() or None

            # Validate required fields
            if not make or not model or not year:
                self._json_response(400, {
                    "success": False,
                    "error": "Missing required fields: make, model, and year are required.",
                })
                return

            try:
                year = int(year)
            except (ValueError, TypeError):
                self._json_response(400, {
                    "success": False,
                    "error": "Invalid year value. Must be a number.",
                })
                return

            if year < 1990 or year > 2030:
                self._json_response(400, {
                    "success": False,
                    "error": "Invalid year value. Must be between 1990 and 2030.",
                })
                return

            price = int(price) if price else 0
            mileage = int(mileage) if mileage else 0

            # Check for API key
            api_key = os.environ.get("GOOGLE_API_KEY")
            if not api_key:
                self._json_response(500, {
                    "success": False,
                    "error": (
                        "GOOGLE_API_KEY environment variable is not set. "
                        "Please add your Google AI API key to the Vercel project "
                        "environment variables (Settings > Environment Variables)."
                    ),
                })
                return

            # Check cache
            cache_key = f"{make}_{model}_{year}".lower()
            cached = cache_key in _review_cache

            if cached:
                review = _review_cache[cache_key]
            else:
                prompt = _build_prompt(make, model, year, price, mileage, source)
                review = _call_gemini(prompt, api_key)
                _review_cache[cache_key] = review

            sources = _build_sources(make, model, year)

            self._json_response(200, {
                "success": True,
                "review": review,
                "sources": sources,
                "cached": cached,
            })

        except json.JSONDecodeError:
            self._json_response(400, {
                "success": False,
                "error": "Invalid JSON in request body.",
            })
        except ValueError as e:
            self._json_response(502, {
                "success": False,
                "error": f"Failed to parse Gemini response: {str(e)}",
            })
        except Exception as e:
            self._json_response(500, {
                "success": False,
                "error": f"Review generation failed: {str(e)}",
            })
