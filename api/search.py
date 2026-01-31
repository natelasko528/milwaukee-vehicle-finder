"""
Vercel Serverless Function for Vehicle Search
"""

from http.server import BaseHTTPRequestHandler
import json
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime
import re
import urllib.parse

class VehicleScraper:
    """Multi-platform vehicle scraper"""
    
    def __init__(self):
        self.user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        self.headers = {'User-Agent': self.user_agent}
    
    async def scrape_craigslist(self, session, location, make, model, max_price, max_mileage):
        """Scrape Craigslist with filters"""
        results = []
        base_url = f"https://{location}.craigslist.org/search/cta"
        
        params = {
            'query': f"{make} {model}",
            'max_price': max_price,
            'max_auto_miles': max_mileage,
            'auto_title_status': 1,
        }
        
        try:
            async with session.get(base_url, params=params, headers=self.headers, timeout=15) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    for listing in soup.find_all('li', class_='cl-static-search-result')[:20]:
                        try:
                            title_elem = listing.find('div', class_='title')
                            price_elem = listing.find('div', class_='price')
                            link_elem = listing.find('a')
                            
                            if title_elem and link_elem:
                                url = link_elem.get('href')
                                if not url.startswith('http'):
                                    url = f"https://{location}.craigslist.org{url}"
                                
                                mileage = self._extract_mileage(title_elem.text)
                                
                                results.append({
                                    'title': title_elem.text.strip(),
                                    'price': self._extract_price(price_elem.text if price_elem else '0'),
                                    'url': url,
                                    'source': 'Craigslist',
                                    'location': location,
                                    'mileage': mileage,
                                    'scraped_at': datetime.now().isoformat()
                                })
                        except Exception:
                            continue
        except Exception as e:
            print(f"Craigslist error: {e}")
        
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
        mileage_match = re.search(r'(\d{1,3}(?:,\d{3})*)\s*(?:mi|miles|k)', text.lower())
        if mileage_match:
            mileage_str = mileage_match.group(1).replace(',', '')
            return int(mileage_str)
        return None
    
    async def search_all_platforms(self, make, model, max_price, max_mileage, location='milwaukee', zip_code='53202'):
        """Search all platforms concurrently"""
        async with aiohttp.ClientSession() as session:
            results = await self.scrape_craigslist(session, location, make, model, max_price, max_mileage)
            return results

class handler(BaseHTTPRequestHandler):
    """Vercel serverless handler"""
    
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_GET(self):
        """Handle GET requests"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        
        response = {
            'success': True,
            'message': 'Vehicle Search API is running',
            'endpoints': {
                'search': 'POST /api/search'
            }
        }
        
        self.wfile.write(json.dumps(response).encode())
    
    def do_POST(self):
        """Handle POST requests"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body) if body else {}
            
            make = data.get('make', 'Toyota')
            model = data.get('model', 'Camry')
            max_price = int(data.get('max_price', 15000))
            max_mileage = int(data.get('max_mileage', 200000))
            location = data.get('location', 'milwaukee')
            zip_code = data.get('zip_code', '53202')
            
            # Run async scraping
            scraper = VehicleScraper()
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            vehicles = loop.run_until_complete(
                scraper.search_all_platforms(make, model, max_price, max_mileage, location, zip_code)
            )
            loop.close()
            
            vehicles.sort(key=lambda x: x.get('price', 999999))
            
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            response = {
                'success': True,
                'count': len(vehicles),
                'vehicles': vehicles,
                'search_params': {
                    'make': make,
                    'model': model,
                    'max_price': max_price,
                    'max_mileage': max_mileage,
                    'location': location
                }
            }
            
            self.wfile.write(json.dumps(response).encode())
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            error_response = {
                'success': False,
                'error': str(e)
            }
            
            self.wfile.write(json.dumps(error_response).encode())
