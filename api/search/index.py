"""
Milwaukee Vehicle Finder - Search API
Scrapes Craigslist, CarGurus, Cars.com, and AutoTrader concurrently.
Deployed as a Vercel serverless function.
"""

from http.server import BaseHTTPRequestHandler
import json
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime
from urllib.parse import quote_plus
import re
import hashlib
import time


_rate_limit_store = {}
_RATE_LIMIT = 10  # requests per minute
_RATE_WINDOW = 60  # seconds

def _check_rate_limit(ip):
    """Returns True if rate limit exceeded."""
    now = time.time()
    if ip not in _rate_limit_store:
        _rate_limit_store[ip] = []
    # Clean old entries
    _rate_limit_store[ip] = [t for t in _rate_limit_store[ip] if now - t < _RATE_WINDOW]
    if len(_rate_limit_store[ip]) >= _RATE_LIMIT:
        return True
    _rate_limit_store[ip].append(now)
    return False


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": USER_AGENT}
TIMEOUT = aiohttp.ClientTimeout(total=12)


def _extract_price(text):
    if not text:
        return 0
    m = re.search(r"\$?\s?([\d,]+)", text)
    return int(m.group(1).replace(",", "")) if m else 0


def _extract_mileage(text):
    if not text:
        return None
    m = re.search(r"([\d,]+)\s*(?:mi|miles|k\b)", text, re.IGNORECASE)
    if m:
        val = int(m.group(1).replace(",", ""))
        return val if val < 900000 else None
    return None


def _extract_year(text):
    if not text:
        return None
    m = re.search(r"\b(19[89]\d|20[0-2]\d)\b", text)
    return int(m.group(0)) if m else None


def _make_id(source, url):
    h = hashlib.md5(url.encode()).hexdigest()[:10]
    return f"{source}_{h}"


def _year_ok(year, min_year, max_year):
    if year is None:
        return True
    if min_year and year < min_year:
        return False
    if max_year and year > max_year:
        return False
    return True


# ---------------------------------------------------------------------------
# Scrapers
# ---------------------------------------------------------------------------

async def _fetch_cl_listing_image(session, url, semaphore):
    """Fetch a single Craigslist listing page and extract the first image URL."""
    async with semaphore:
        try:
            async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as resp:
                if resp.status != 200:
                    return None
                html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")

                # Method 1: gallery div with data-ids attribute
                for el in soup.find_all(attrs={"data-ids": True}):
                    data_ids = el.get("data-ids", "")
                    if data_ids:
                        first_id = data_ids.split(",")[0].strip()
                        img_id = first_id.split(":")[-1].strip()
                        if img_id:
                            return f"https://images.craigslist.org/{img_id}_600x450.jpg"

                # Method 2: swipe container images
                swipe = soup.find("div", class_="swipe")
                if swipe:
                    img = swipe.find("img")
                    if img:
                        src = img.get("src")
                        if src:
                            return src

                # Method 3: gallery images
                gallery = soup.find("div", class_="gallery")
                if gallery:
                    img = gallery.find("img")
                    if img:
                        src = img.get("src")
                        if src:
                            return re.sub(r'_\d+x\d+', '_600x450', src)

                # Method 4: thumbs
                thumbs = soup.find("div", id="thumbs")
                if thumbs:
                    link = thumbs.find("a")
                    if link:
                        href = link.get("href")
                        if href:
                            return href

                return None
        except Exception:
            return None


async def scrape_craigslist(session, location, make, model, max_price, max_mileage, min_year, max_year):
    results = []
    query = f"{make} {model}".strip()
    base_url = f"https://{location}.craigslist.org/search/cta"
    params = {
        "query": query,
        "max_price": max_price,
        "max_auto_miles": max_mileage,
        "auto_title_status": 1,
    }
    if min_year:
        params["min_auto_year"] = min_year
    if max_year:
        params["max_auto_year"] = max_year

    try:
        async with session.get(base_url, params=params, headers=HEADERS, timeout=TIMEOUT) as resp:
            if resp.status != 200:
                return results
            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")

            for li in soup.find_all("li", class_="cl-static-search-result")[:20]:
                try:
                    title_el = li.find("div", class_="title")
                    price_el = li.find("div", class_="price")
                    link_el = li.find("a")
                    if not (title_el and link_el):
                        continue

                    url = link_el.get("href", "")
                    if not url.startswith("http"):
                        url = f"https://{location}.craigslist.org{url}"

                    title = title_el.text.strip()
                    price = _extract_price(price_el.text if price_el else "")
                    mileage = _extract_mileage(title)
                    year = _extract_year(title)

                    if not _year_ok(year, min_year, max_year):
                        continue

                    results.append({
                        "id": _make_id("cl", url),
                        "title": title,
                        "price": price,
                        "url": url,
                        "source": "Craigslist",
                        "location": location,
                        "mileage": mileage,
                        "year": year,
                        "image_url": None,
                        "scraped_at": datetime.now().isoformat(),
                    })
                except Exception:
                    continue

        # Fetch images from individual listing pages concurrently
        if results:
            semaphore = asyncio.Semaphore(5)
            image_tasks = [
                _fetch_cl_listing_image(session, r["url"], semaphore)
                for r in results
            ]
            images = await asyncio.gather(*image_tasks, return_exceptions=True)
            for i, img in enumerate(images):
                if isinstance(img, str) and img:
                    results[i]["image_url"] = img

    except Exception as e:
        print(f"[craigslist] error: {e}")

    return results


async def scrape_cargurus(session, make, model, max_price, max_mileage, min_year, max_year, zip_code):
    results = []
    search_term = f"{make}-{model}".replace(" ", "-")
    url = f"https://www.cargurus.com/Cars/l-Used-{search_term}-t{zip_code}"
    params = {
        "maxPrice": max_price,
        "maxMileage": max_mileage,
        "searchRadius": 50,
    }
    if min_year:
        params["minYear"] = min_year
    if max_year:
        params["maxYear"] = max_year

    try:
        async with session.get(url, params=params, headers=HEADERS, timeout=TIMEOUT) as resp:
            if resp.status != 200:
                return results
            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")

            for card in soup.select('[data-cg-ft="car-blade"]')[:15]:
                try:
                    title_el = card.find("h4") or card.find("a", class_=re.compile(r"title", re.I))
                    price_el = card.find("span", class_=re.compile(r"price", re.I))
                    link_el = card.find("a", href=True)
                    img_el = card.find("img")

                    if not (title_el and link_el):
                        continue

                    title = title_el.get_text(strip=True)
                    href = link_el["href"]
                    if not href.startswith("http"):
                        href = f"https://www.cargurus.com{href}"

                    price = _extract_price(price_el.get_text() if price_el else "")
                    year = _extract_year(title)
                    mileage = _extract_mileage(card.get_text())
                    image_url = img_el.get("src") or img_el.get("data-src") if img_el else None

                    if not _year_ok(year, min_year, max_year):
                        continue

                    results.append({
                        "id": _make_id("cg", href),
                        "title": title,
                        "price": price,
                        "url": href,
                        "source": "CarGurus",
                        "location": "Milwaukee",
                        "mileage": mileage,
                        "year": year,
                        "image_url": image_url,
                        "scraped_at": datetime.now().isoformat(),
                    })
                except Exception:
                    continue
    except Exception as e:
        print(f"[cargurus] error: {e}")

    return results


async def scrape_cars_com(session, make, model, max_price, max_mileage, min_year, max_year, zip_code):
    results = []
    base_url = "https://www.cars.com/shopping/results/"
    params = {
        "makes[]": make.lower(),
        "models[]": f"{make.lower()}-{model.lower().replace(' ', '_')}",
        "maximum_distance": 50,
        "zip": zip_code,
        "price_max": max_price,
        "maximum_mileage": max_mileage,
        "stock_type": "used",
    }
    if min_year:
        params["year_min"] = min_year
    if max_year:
        params["year_max"] = max_year

    try:
        async with session.get(base_url, params=params, headers=HEADERS, timeout=TIMEOUT) as resp:
            if resp.status != 200:
                return results
            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")

            for card in soup.find_all("div", class_="vehicle-card")[:15]:
                try:
                    title_el = card.find("h2", class_="title") or card.find("h2")
                    price_el = card.find("span", class_="primary-price")
                    link_el = card.find("a", class_="vehicle-card-link") or card.find("a", href=True)
                    img_el = card.find("img", class_="vehicle-image") or card.find("img")
                    mileage_el = card.find("div", class_="mileage")

                    if not (title_el and link_el):
                        continue

                    title = title_el.get_text(strip=True)
                    href = link_el.get("href", "")
                    if not href.startswith("http"):
                        href = f"https://www.cars.com{href}"

                    price = _extract_price(price_el.get_text() if price_el else "")
                    year = _extract_year(title)
                    mileage = _extract_mileage(mileage_el.get_text() if mileage_el else "")
                    image_url = img_el.get("src") or img_el.get("data-src") if img_el else None

                    if not _year_ok(year, min_year, max_year):
                        continue

                    results.append({
                        "id": _make_id("cc", href),
                        "title": title,
                        "price": price,
                        "url": href,
                        "source": "Cars.com",
                        "location": "Milwaukee",
                        "mileage": mileage,
                        "year": year,
                        "image_url": image_url,
                        "scraped_at": datetime.now().isoformat(),
                    })
                except Exception:
                    continue
    except Exception as e:
        print(f"[cars.com] error: {e}")

    return results


async def scrape_autotrader(session, make, model, max_price, max_mileage, min_year, max_year, zip_code):
    results = []
    base_url = "https://www.autotrader.com/cars-for-sale/all-cars"
    params = {
        "makeCodeList": make.upper(),
        "modelCodeList": model.upper().replace(" ", ""),
        "zip": zip_code,
        "maxPrice": max_price,
        "maxMileage": max_mileage,
        "searchRadius": 50,
    }
    if min_year:
        params["startYear"] = min_year
    if max_year:
        params["endYear"] = max_year

    try:
        async with session.get(base_url, params=params, headers=HEADERS, timeout=TIMEOUT) as resp:
            if resp.status != 200:
                return results
            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")

            for card in soup.find_all("div", attrs={"data-cmp": "inventoryListing"})[:15]:
                try:
                    title_el = card.find("h3") or card.find("h2")
                    price_el = card.find("span", attrs={"data-cmp": "price"}) or card.find("div", class_=re.compile(r"price", re.I))
                    link_el = card.find("a", attrs={"data-cmp": "listingTitle"}) or card.find("a", href=True)
                    img_el = card.find("img")

                    if not (title_el and link_el):
                        continue

                    title = title_el.get_text(strip=True)
                    href = link_el.get("href", "")
                    if not href.startswith("http"):
                        href = f"https://www.autotrader.com{href}"

                    price = _extract_price(price_el.get_text() if price_el else "")
                    year = _extract_year(title)
                    mileage = _extract_mileage(card.get_text())
                    image_url = img_el.get("src") or img_el.get("data-src") if img_el else None

                    if not _year_ok(year, min_year, max_year):
                        continue

                    results.append({
                        "id": _make_id("at", href),
                        "title": title,
                        "price": price,
                        "url": href,
                        "source": "AutoTrader",
                        "location": "Milwaukee",
                        "mileage": mileage,
                        "year": year,
                        "image_url": image_url,
                        "scraped_at": datetime.now().isoformat(),
                    })
                except Exception:
                    continue
    except Exception as e:
        print(f"[autotrader] error: {e}")

    return results


def validate_params(params):
    """Validate search parameters. Returns (cleaned_params, error_message).
    If error_message is not None, validation failed."""
    errors = []

    # --- int conversions with try/except ---
    try:
        max_price = int(params.get("max_price", 30000))
    except (ValueError, TypeError):
        errors.append("max_price must be a valid integer")
        max_price = None

    try:
        max_mileage = int(params.get("max_mileage", 200000))
    except (ValueError, TypeError):
        errors.append("max_mileage must be a valid integer")
        max_mileage = None

    min_year = None
    if params.get("min_year"):
        try:
            min_year = int(params["min_year"])
        except (ValueError, TypeError):
            errors.append("min_year must be a valid integer")

    max_year = None
    if params.get("max_year"):
        try:
            max_year = int(params["max_year"])
        except (ValueError, TypeError):
            errors.append("max_year must be a valid integer")

    # --- Negative value checks ---
    if max_price is not None and max_price < 0:
        errors.append("max_price cannot be negative")
    if max_mileage is not None and max_mileage < 0:
        errors.append("max_mileage cannot be negative")

    # --- Year range checks ---
    if min_year is not None and (min_year < 1990 or min_year > 2030):
        errors.append("min_year must be between 1990 and 2030")
    if max_year is not None and (max_year < 1990 or max_year > 2030):
        errors.append("max_year must be between 1990 and 2030")

    # --- ZIP code validation ---
    zip_code = str(params.get("zip_code", "53202")).strip()
    if not zip_code.isdigit():
        errors.append("zip_code must be numeric")

    if errors:
        return None, "; ".join(errors)

    return {
        "make": params.get("make", "").strip(),
        "model": params.get("model", "").strip(),
        "max_price": max_price,
        "max_mileage": max_mileage,
        "min_year": min_year,
        "max_year": max_year,
        "location": params.get("location", "milwaukee"),
        "zip_code": zip_code,
    }, None


async def search_all(params):
    validated, error = validate_params(params)
    if error:
        raise ValueError(error)

    make = validated["make"]
    model = validated["model"]
    max_price = validated["max_price"]
    max_mileage = validated["max_mileage"]
    min_year = validated["min_year"]
    max_year = validated["max_year"]
    location = validated["location"]
    zip_code = validated["zip_code"]

    async with aiohttp.ClientSession() as session:
        tasks = [
            scrape_craigslist(session, location, make, model, max_price, max_mileage, min_year, max_year),
            scrape_cargurus(session, make, model, max_price, max_mileage, min_year, max_year, zip_code),
            scrape_cars_com(session, make, model, max_price, max_mileage, min_year, max_year, zip_code),
            scrape_autotrader(session, make, model, max_price, max_mileage, min_year, max_year, zip_code),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    vehicles = []
    sources_searched = []
    source_names = ["Craigslist", "CarGurus", "Cars.com", "AutoTrader"]
    for name, result in zip(source_names, results):
        if isinstance(result, list):
            vehicles.extend(result)
            sources_searched.append({"name": name, "count": len(result)})
        else:
            sources_searched.append({"name": name, "count": 0, "error": str(result)})

    # Filter out $0 price listings
    vehicles = [v for v in vehicles if v.get("price", 0) > 0]

    # Sort by price ascending
    vehicles.sort(key=lambda v: v.get("price", 999999))

    return vehicles, sources_searched


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
            "message": "Milwaukee Vehicle Finder API v4.0",
            "status": "operational",
            "endpoints": {
                "POST /api/search": "Search vehicles across multiple platforms",
                "GET /api/details?url=": "Get details for a specific listing",
            },
        })

    def do_POST(self):
        # Get client IP
        client_ip = self.headers.get('X-Forwarded-For', self.client_address[0] if self.client_address else 'unknown')
        if isinstance(client_ip, str) and ',' in client_ip:
            client_ip = client_ip.split(',')[0].strip()

        if _check_rate_limit(client_ip):
            self._json_response(429, {
                "success": False,
                "error": "Rate limit exceeded. Please wait before searching again.",
            })
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            data = json.loads(body)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            vehicles, sources = loop.run_until_complete(search_all(data))
            loop.close()

            total = len(vehicles)
            avg_price = round(sum(v["price"] for v in vehicles) / total, 2) if total else 0
            prices = [v["price"] for v in vehicles]

            self._json_response(200, {
                "success": True,
                "count": total,
                "vehicles": vehicles,
                "sources": sources,
                "stats": {
                    "total_count": total,
                    "avg_price": avg_price,
                    "min_price": min(prices) if prices else 0,
                    "max_price": max(prices) if prices else 0,
                },
                "search_params": data,
                "timestamp": datetime.now().isoformat(),
            })
        except ValueError as e:
            self._json_response(400, {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            })
        except Exception as e:
            self._json_response(500, {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            })
