"""
Vercel Serverless Function - BaseHTTPRequestHandler approach
"""

from http.server import BaseHTTPRequestHandler
import json
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime
import re

async def scrape_craigslist(location, make, model, max_price, max_mileage):
    """Scrape Craigslist for vehicles"""
    results = []
    base_url = f"https://{location}.craigslist.org/search/cta"
    
    params = {
        'query': f"{make} {model}",
        'max_price': max_price,
        'max_auto_miles': max_mileage,
        'auto_title_status': 1,
    }
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(base_url, params=params, headers=headers, timeout=15) as response:
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
                                
                                listing_id = url.split('/')[-1].replace('.html', '')
                                
                                # Extract price
                                price = 0
                                if price_elem:
                                    price_match = re.search(r'[\$]?([0-9,]+)', price_elem.text)
                                    if price_match:
                                        price = int(price_match.group(1).replace(',', ''))
                                
                                # Extract mileage
                                mileage = None
                                mileage_match = re.search(r'(\d{1,3}(?:,\d{3})*)\s*(?:mi|miles|k)', title_elem.text.lower())
                                if mileage_match:
                                    mileage = int(mileage_match.group(1).replace(',', ''))
                                
                                # Extract year
                                year = None
                                year_match = re.search(r'(19|20)\d{2}', title_elem.text)
                                if year_match:
                                    year = int(year_match.group(0))
                                
                                results.append({
                                    'id': f"cl_{listing_id}",
                                    'title': title_elem.text.strip(),
                                    'price': price,
                                    'url': url,
                                    'source': 'Craigslist',
                                    'location': location,
                                    'mileage': mileage,
                                    'year': year,
                                    'scraped_at': datetime.now().isoformat()
                                })
                        except Exception as e:
                            continue
    except Exception as e:
        print(f"Scraping error: {e}")
    
    return results

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        response = {
            'success': True,
            'message': 'Vehicle Search API v3.0',
            'status': 'operational'
        }
        self.wfile.write(json.dumps(response).encode())
    
    def do_POST(self):
        try:
            # Parse request body
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else '{}'
            data = json.loads(body)
            
            # Extract parameters
            make = data.get('make', 'Toyota')
            model = data.get('model', 'Camry')
            max_price = int(data.get('max_price', 15000))
            max_mileage = int(data.get('max_mileage', 200000))
            location = data.get('location', 'milwaukee')
            
            # Run async scraping
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            vehicles = loop.run_until_complete(
                scrape_craigslist(location, make, model, max_price, max_mileage)
            )
            loop.close()
            
            # Sort by price
            vehicles.sort(key=lambda x: x.get('price', 999999))
            
            # Calculate stats
            total_count = len(vehicles)
            avg_price = sum(v.get('price', 0) for v in vehicles) / total_count if total_count > 0 else 0
            
            # Send response
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            response = {
                'success': True,
                'count': total_count,
                'vehicles': vehicles,
                'stats': {
                    'total_count': total_count,
                    'avg_price': round(avg_price, 2)
                },
                'search_params': {
                    'make': make,
                    'model': model,
                    'max_price': max_price,
                    'max_mileage': max_mileage,
                    'location': location
                },
                'timestamp': datetime.now().isoformat()
            }
            
            self.wfile.write(json.dumps(response).encode())
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            error_response = {
                'success': False,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
            self.wfile.write(json.dumps(error_response).encode())
