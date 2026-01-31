"""
Vercel Serverless Function for Vehicle Search
"""
from http.server import BaseHTTPRequestHandler
import json
import urllib.request
import urllib.parse
from bs4 import BeautifulSoup
import re

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            # Read request body
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
            
            # Extract search parameters
            make = data.get('make', 'Toyota')
            model = data.get('model', 'Camry')
            max_price = int(data.get('max_price', 15000))
            max_mileage = int(data.get('max_mileage', 200000))
            location = data.get('location', 'milwaukee')
            
            # Perform search
            vehicles = self.search_vehicles(make, model, max_price, max_mileage, location)
            
            # Return results
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
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
            
            self.wfile.write(json.dumps(response).encode('utf-8'))
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            
            error_response = {
                'success': False,
                'error': str(e)
            }
            
            self.wfile.write(json.dumps(error_response).encode('utf-8'))
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def search_vehicles(self, make, model, max_price, max_mileage, location):
        """Search Craigslist for vehicles"""
        vehicles = []
        
        try:
            # Build Craigslist URL
            base_url = f"https://{location}.craigslist.org/search/cta"
            params = {
                'query': f"{make} {model}",
                'max_price': max_price,
                'max_auto_miles': max_mileage,
                'auto_title_status': 1,
            }
            
            url = f"{base_url}?{urllib.parse.urlencode(params)}"
            
            # Make request
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            req = urllib.request.Request(url, headers=headers)
            
            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read().decode('utf-8')
                soup = BeautifulSoup(html, 'html.parser')
                
                # Parse listings
                for listing in soup.find_all('li', class_='cl-static-search-result')[:20]:
                    try:
                        title_elem = listing.find('div', class_='title')
                        price_elem = listing.find('div', class_='price')
                        link_elem = listing.find('a')
                        
                        if title_elem and link_elem:
                            url = link_elem.get('href')
                            if not url.startswith('http'):
                                url = f"https://{location}.craigslist.org{url}"
                            
                            price = self._extract_price(price_elem.text if price_elem else '0')
                            mileage = self._extract_mileage(title_elem.text)
                            
                            vehicles.append({
                                'title': title_elem.text.strip(),
                                'price': price,
                                'url': url,
                                'source': 'Craigslist',
                                'location': location,
                                'images': [],
                                'mileage': mileage,
                            })
                    except:
                        continue
                        
        except Exception as e:
            print(f"Craigslist error: {e}")
        
        return vehicles
    
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
