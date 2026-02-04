"""
API Endpoint: Vehicle Safety Data from NHTSA
Fetches safety ratings, recalls, and complaints from the free NHTSA API.
"""

from http.server import BaseHTTPRequestHandler
import json
import asyncio
import aiohttp
from urllib.parse import urlparse, parse_qs, quote

# In-memory cache keyed by "{make}_{model}_{year}"
_cache = {}

TIMEOUT = aiohttp.ClientTimeout(total=12)


def _cors_headers():
    return {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
    }


async def _fetch_safety_ratings(session, year, make, model):
    """Fetch overall safety ratings from NHTSA SafetyRatings API."""
    url = (
        f"https://api.nhtsa.gov/SafetyRatings/modelyear/{quote(str(year))}"
        f"/make/{quote(make)}/model/{quote(model)}?format=json"
    )
    async with session.get(url, timeout=TIMEOUT) as resp:
        if resp.status != 200:
            return None
        data = await resp.json(content_type=None)
        results = data.get("Results", [])
        if not results:
            return None
        # The first result that has an OverallRating
        for r in results:
            overall = r.get("OverallRating", "Not Rated")
            return {
                "overall_rating": overall,
                "frontal_crash": r.get("FrontalCrashDriversideRating",
                                       r.get("FrontalCrashPicture", "Not Rated")),
                "side_crash": r.get("SideCrashDriversideRating",
                                    r.get("SideCrashPicture", "Not Rated")),
                "rollover": r.get("RolloverRating",
                                  r.get("RolloverPicture", "Not Rated")),
                "ratings_available": overall != "Not Rated",
            }
        return None


async def _fetch_recalls(session, year, make, model):
    """Fetch recall data from NHTSA Recalls API."""
    url = (
        f"https://api.nhtsa.gov/recalls/recallsByVehicle"
        f"?make={quote(make)}&model={quote(model)}&modelYear={quote(str(year))}"
    )
    async with session.get(url, timeout=TIMEOUT) as resp:
        if resp.status != 200:
            return []
        data = await resp.json(content_type=None)
        results = data.get("results", [])
        recalls = []
        for r in results:
            recalls.append({
                "date": r.get("ReportReceivedDate", ""),
                "component": r.get("Component", ""),
                "summary": r.get("Summary", ""),
                "consequence": r.get("Consequence", ""),
                "remedy": r.get("Remedy", ""),
            })
        return recalls


async def _fetch_complaints(session, year, make, model):
    """Fetch consumer complaints from NHTSA Complaints API."""
    url = (
        f"https://api.nhtsa.gov/complaints/complaintsByVehicle"
        f"?make={quote(make)}&model={quote(model)}&modelYear={quote(str(year))}"
    )
    async with session.get(url, timeout=TIMEOUT) as resp:
        if resp.status != 200:
            return []
        data = await resp.json(content_type=None)
        results = data.get("results", [])
        complaints = []
        for r in results[:20]:
            complaints.append({
                "date": r.get("dateOfIncident", r.get("dateComplaintFiled", "")),
                "component": r.get("components", ""),
                "summary": r.get("summary", ""),
                "crash": r.get("crash", "N") == "Y",
                "fire": r.get("fire", "N") == "Y",
            })
        return complaints


async def _get_safety_data(year, make, model):
    """Fetch all three NHTSA endpoints concurrently."""
    async with aiohttp.ClientSession() as session:
        ratings_result, recalls_result, complaints_result = await asyncio.gather(
            _fetch_safety_ratings(session, year, make, model),
            _fetch_recalls(session, year, make, model),
            _fetch_complaints(session, year, make, model),
            return_exceptions=True,
        )

    # Handle individual failures gracefully
    if isinstance(ratings_result, Exception) or ratings_result is None:
        safety = {
            "overall_rating": "Not Rated",
            "frontal_crash": "Not Rated",
            "side_crash": "Not Rated",
            "rollover": "Not Rated",
            "ratings_available": False,
        }
    else:
        safety = ratings_result

    recalls = [] if isinstance(recalls_result, Exception) else recalls_result
    complaints = [] if isinstance(complaints_result, Exception) else complaints_result

    # Total complaint count is the full results length (complaints list is capped at 20)
    complaint_count = len(complaints)

    return {
        "success": True,
        "safety": safety,
        "recalls": recalls,
        "recall_count": len(recalls),
        "complaints": complaints,
        "complaint_count": complaint_count,
        "nhtsa_url": f"https://www.nhtsa.gov/vehicle/{year}/{make.upper()}/{model.upper()}",
    }


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        for k, v in _cors_headers().items():
            self.send_header(k, v)
        self.end_headers()

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)

            make = params.get("make", [None])[0]
            model = params.get("model", [None])[0]
            year = params.get("year", [None])[0]

            if not make or not model or not year:
                self.send_response(400)
                self.send_header("Content-type", "application/json")
                for k, v in _cors_headers().items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(json.dumps({
                    "success": False,
                    "error": "Missing required parameters: make, model, year",
                }).encode())
                return

            try:
                year_int = int(year)
            except (ValueError, TypeError):
                self.send_response(400)
                self.send_header("Content-type", "application/json")
                for k, v in _cors_headers().items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(json.dumps({
                    "success": False,
                    "error": "Invalid year value. Must be a number.",
                }).encode())
                return

            if year_int < 1990 or year_int > 2030:
                self.send_response(400)
                self.send_header("Content-type", "application/json")
                for k, v in _cors_headers().items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(json.dumps({
                    "success": False,
                    "error": "Invalid year value. Must be between 1990 and 2030.",
                }).encode())
                return

            year = str(year_int)

            # Check cache
            cache_key = f"{make.lower()}_{model.lower()}_{year}"
            if cache_key in _cache:
                result = _cache[cache_key]
            else:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(_get_safety_data(year, make, model))
                loop.close()
                _cache[cache_key] = result

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            for k, v in _cors_headers().items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())

        except ValueError:
            self.send_response(400)
            self.send_header("Content-type", "application/json")
            for k, v in _cors_headers().items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": False,
                "error": "Invalid year parameter - must be a number",
            }).encode())

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-type", "application/json")
            for k, v in _cors_headers().items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": False,
                "error": str(e),
            }).encode())
