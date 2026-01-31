"""
Enhanced Vercel Serverless Function for Vehicle Search
Improvements:
- Vercel KV caching for 5-minute result cache
- Background price tracking preparation
- Better error handling and logging
- Multi-platform support ready (CarGurus, Cars.com, AutoTrader)
"""

from http.server import BaseHTTPRequestHandler
import json
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re
import urllib.parse
import hashlib
import os

# Vercel KV integration (will be configured via environment)
REDIS_URL = os.getenv('KV_URL')
REDIS_TOKEN = os.getenv('KV_REST_API_TOKEN')

class CacheManager:
    """Simple cache manager for Vercel KV or in-memory fallback"""
    
    def __init__(self):
        self.use_redis = bool(REDIS_URL and REDIS_TOKEN)
        self.memory_cache = {}
    
    async def get(self, key):
        """Get cached value"""
        if self.use_redis:
            try:
                async with aiohttp.ClientSession() as session:
                    url = f"{REDIS_URL}/get/{key}"
                    headers = {"Authorization": f"Bearer {REDIS_TOKEN}"}
                    async with session.get(url, headers=headers) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            return json.loads(data.get('result')) if data.get('result') else None
            except:
                pass
        
        # Fallback to memory cache
        cached = self.memory_cache.get(key)
        if cached and cached['expires'] > datetime.now().timestamp():
            return cached['data']
        return None
    
    async def set(self, key, value, ttl=300):
        """Set cached value with TTL (default 5 minutes)"""
        if self.use_redis:
            try:
                async with aiohttp.ClientSession() as session:
                    url = f"{REDIS_URL}/set/{key}"
                    headers = {"Authorization": f"Bearer {REDIS_TOKEN}"}
                    body = {"value": json.dumps(value), "ex": ttl}
                    async with session.post(url, headers=headers, json=body) as resp:
                        if resp.status == 200:
                            return True
            except:
                pass
        
        # Fallback to memory cache
        self.memory_cache[key] = {
            'data': value,
            'expires': datetime.now().timestamp() + ttl
        }
        return True

class VehicleScraper:
    """Enhanced multi-platform vehicle scraper"""
    
    def __init__(self):
        self.user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        self.headers = {'User-Agent': self.user_agent}
        self.cache = CacheManager()
    
    async def scrape_craigslist(self, session, location, make, model, max_price, max_mileage, min_year=None, max_year=None):
        """Enhanced Craigslist scraping with year filters"""
        results = []
        base_url = f"https://{location}.craigslist.org/search/cta"
        
        params = {
            'query': f"{make} {model}",
            'max_price': max_price,
            'max_auto_miles': max_mileage,
            'auto_title_status': 1,
        }
        
        if min_year:
            params['min_auto_year'] = min_year
        if max_year:
            params['max_auto_year'] = max_year
        
        print(f"[DEBUG] Craigslist URL: {base_url}")
        print(f"[DEBUG] Craigslist params: {params}")
        
        try:
            async with session.get(base_url, params=params, headers=self.headers, timeout=15) as response:
                print(f"[DEBUG] Craigslist response status: {response.status}")
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    print(f"[DEBUG] Found {len(soup.find_all('li', class_='cl-static-search-result'))} Craigslist listings")
                    
                    for listing in soup.find_all('li', class_='cl-static-search-result')[:20]:
                        try:
                            title_elem = listing.find('div', class_='title')
                            price_elem = listing.find('div', class_='price')
                            link_elem = listing.find('a')
                            meta_elem = listing.find('div', class_='meta')
                            
                            if title_elem and link_elem:
                                url = link_elem.get('href')
                                if not url.startswith('http'):
                                    url = f"https://{location}.craigslist.org{url}"
                                
                                # Extract listing ID for tracking
                                listing_id = url.split('/')[-1].replace('.html', '')
                                
                                mileage = self._extract_mileage(title_elem.text)
                                year = self._extract_year(title_elem.text)
                                
                                price = self._extract_price(price_elem.text if price_elem else '0')
                                
                                results.append({
                                    'id': f"cl_{listing_id}",
                                    'title': title_elem.text.strip(),
                                    'price': price,
                                    'url': url,
                                    'source': 'Craigslist',
                                    'location': location,
                                    'mileage': mileage,
                                    'year': year,
                                    'scraped_at': datetime.now().isoformat(),
                                    'meta': meta_elem.text.strip() if meta_elem else None
                                })
                        except Exception as e:
                            print(f"Error parsing listing: {e}")
                            continue
        except Exception as e:
            print(f"[ERROR] Craigslist error: {e}")
            import traceback
            traceback.print_exc()
        
        print(f"[DEBUG] Returning {len(results)} Craigslist results")
        return results
    
    async def scrape_cargurus(self, session, make, model, max_price, max_mileage, zip_code, min_year=None, max_year=None):
        """CarGurus scraping (simplified - may need adjustment based on actual site)"""
        results = []
        # CarGurus requires more complex scraping with ZIP-based search
        # This is a placeholder for Phase 2 implementation
        return results
    
    def _extract_price(self, price_str):
        """Extract numeric price from string"""
        if not price_str:
            return 0
        price_match = re.search(r'[\$]?([0-9,]+)', price_str)
        if price_match:
            return int(price_match.group(1).replace(',', ''))
        return 0
    
    def _extract_mileage(self, text):
        """Extract mileage from text"""
        if not text:
            return None
        mileage_match = re.search(r'(\d{1,3}(?:,\d{3})*)\\s*(?:mi|miles|k)', text.lower())
        if mileage_match:
            mileage_str = mileage_match.group(1).replace(',', '')
            return int(mileage_str)
        return None
    
    def _extract_year(self, text):
        """Extract year from text"""
        if not text:
            return None
        year_match = re.search(r'(19|20)\d{2}', text)
        if year_match:
            return int(year_match.group(0))
        return None
    
    def _generate_cache_key(self, make, model, max_price, max_mileage, location, min_year, max_year):
        """Generate cache key for search parameters"""
        key_str = f"{make}_{model}_{max_price}_{max_mileage}_{location}_{min_year}_{max_year}"
        return hashlib.md5(key_str.encode()).hexdigest()
    
    async def search_all_platforms(self, make, model, max_price, max_mileage, location='milwaukee', 
                                   zip_code='53202', min_year=None, max_year=None, use_cache=True):
        """Search all platforms with caching"""
        
        # Check cache first
        if use_cache:
            cache_key = self._generate_cache_key(make, model, max_price, max_mileage, location, min_year, max_year)
            cached = await self.cache.get(cache_key)
            if cached:
                print(f"Cache hit for {cache_key}")
                return cached
        
        # Scrape platforms
        async with aiohttp.ClientSession() as session:
            tasks = [
                self.scrape_craigslist(session, location, make, model, max_price, max_mileage, min_year, max_year),
                # Add more platforms in Phase 2
            ]
            
            results_lists = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Flatten and filter successful results
            all_results = []
            for result_list in results_lists:
                if isinstance(result_list, list):
                    all_results.extend(result_list)
            
            # Cache results
            if use_cache and all_results:
                await self.cache.set(cache_key, all_results, ttl=300)  # 5-minute cache
            
            return all_results

class handler(BaseHTTPRequestHandler):
    """Enhanced Vercel serverless handler"""
    
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_GET(self):
        """Handle GET requests - API status"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        
        response = {
            'success': True,
            'message': 'Enhanced Vehicle Search API v2.0',
            'features': [
                'Multi-platform search',
                '5-minute result caching',
                'Year range filtering',
                'Price tracking ready'
            ],
            'endpoints': {
                'search': 'POST /api/search'
            }
        }
        
        self.wfile.write(json.dumps(response).encode())
    
    def do_POST(self):
        """Handle POST requests - vehicle search"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body) if body else {}
            
            print(f"[DEBUG] Received POST request with data: {data}")
            
            # Extract parameters with defaults
            make = data.get('make', 'Toyota')
            model = data.get('model', 'Camry')
            max_price = int(data.get('max_price', 15000))
            max_mileage = int(data.get('max_mileage', 200000))
            location = data.get('location', 'milwaukee')
            zip_code = data.get('zip_code', '53202')
            min_year = int(data.get('min_year')) if data.get('min_year') else None
            max_year = int(data.get('max_year')) if data.get('max_year') else None
            use_cache = data.get('use_cache', True)
            
            print(f"[DEBUG] Searching: {make} {model}, max ${max_price}, location: {location}")
            
            # Run async scraping
            scraper = VehicleScraper()
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            print(f"[DEBUG] Starting search_all_platforms...")
            vehicles = loop.run_until_complete(
                scraper.search_all_platforms(
                    make, model, max_price, max_mileage, location, zip_code, 
                    min_year, max_year, use_cache
                )
            )
            loop.close()
            
            print(f"[DEBUG] Got {len(vehicles)} total vehicles")
            
            # Sort by price
            vehicles.sort(key=lambda x: x.get('price', 999999))
            
            # Calculate stats
            total_count = len(vehicles)
            avg_price = sum(v.get('price', 0) for v in vehicles) / total_count if total_count > 0 else 0
            avg_mileage = sum(v.get('mileage', 0) for v in vehicles if v.get('mileage')) / total_count if total_count > 0 else 0
            
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            response = {
                'success': True,
                'count': total_count,
                'vehicles': vehicles,
                'stats': {
                    'total_count': total_count,
                    'avg_price': round(avg_price, 2),
                    'avg_mileage': round(avg_mileage, 0),
                    'platforms': list(set(v['source'] for v in vehicles))
                },
                'search_params': {
                    'make': make,
                    'model': model,
                    'max_price': max_price,
                    'max_mileage': max_mileage,
                    'location': location,
                    'min_year': min_year,
                    'max_year': max_year
                },
                'cached': use_cache,
                'timestamp': datetime.now().isoformat()
            }
            
            self.wfile.write(json.dumps(response).encode())
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            error_response = {
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
            
            self.wfile.write(json.dumps(error_response).encode())
