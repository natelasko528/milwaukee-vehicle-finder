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


async def search_all(params):
    make = params.get("make", "").strip()
    model = params.get("model", "").strip()
    max_price = int(params.get("max_price", 30000))
    max_mileage = int(params.get("max_mileage", 200000))
    min_year = int(params["min_year"]) if params.get("min_year") else None
    max_year = int(params["max_year"]) if params.get("max_year") else None
    location = params.get("location", "milwaukee")
    zip_code = params.get("zip_code", "53202")

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
        except Exception as e:
            self._json_response(500, {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            })
