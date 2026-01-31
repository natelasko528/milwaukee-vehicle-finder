"""
Last updated: 1769856004
"""
Vercel Serverless Function - Multi-platform vehicle scraper
Searches: Craigslist, CarGurus, Cars.com, AutoTrader
"""

from http.server import BaseHTTPRequestHandler
import json
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime
import re
from urllib.parse import quote

# Alphabetized makes and models
VEHICLE_DATA = {
    "Acura": ["ILX", "Integra", "MDX", "RDX", "TLX"],
    "BMW": ["2 Series", "3 Series", "4 Series", "5 Series", "7 Series", "X1", "X3", "X5", "X7"],
    "Chevrolet": ["Blazer", "Camaro", "Colorado", "Corvette", "Cruze", "Equinox", "Impala", "Malibu", "Silverado", "Suburban", "Tahoe", "Traverse"],
    "Dodge": ["Challenger", "Charger", "Durango", "Grand Caravan", "Journey", "Ram 1500"],
    "Ford": ["Bronco", "Edge", "Escape", "Expedition", "Explorer", "F-150", "Fusion", "Mustang", "Ranger"],
    "GMC": ["Acadia", "Canyon", "Sierra", "Terrain", "Yukon"],
    "Honda": ["Accord", "Civic", "CR-V", "Fit", "HR-V", "Insight", "Odyssey", "Passport", "Pilot", "Ridgeline"],
    "Hyundai": ["Accent", "Elantra", "Kona", "Palisade", "Santa Fe", "Sonata", "Tucson", "Veloster"],
    "Jeep": ["Cherokee", "Compass", "Gladiator", "Grand Cherokee", "Renegade", "Wrangler"],
    "Kia": ["Forte", "K5", "Optima", "Rio", "Seltos", "Sorento", "Soul", "Sportage", "Stinger", "Telluride"],
    "Lexus": ["ES", "GX", "IS", "LS", "LX", "NX", "RC", "RX", "UX"],
    "Mazda": ["CX-3", "CX-30", "CX-5", "CX-9", "Mazda3", "Mazda6", "MX-5 Miata"],
    "Mercedes-Benz": ["A-Class", "C-Class", "CLA", "E-Class", "G-Class", "GLA", "GLB", "GLC", "GLE", "GLS", "S-Class"],
    "Nissan": ["Altima", "Armada", "Frontier", "Kicks", "Maxima", "Murano", "Pathfinder", "Rogue", "Sentra", "Titan", "Versa"],
    "Ram": ["1500", "2500", "3500", "ProMaster"],
    "Subaru": ["Ascent", "BRZ", "Crosstrek", "Forester", "Impreza", "Legacy", "Outback", "WRX"],
    "Tesla": ["Model 3", "Model S", "Model X", "Model Y"],
    "Toyota": ["4Runner", "Avalon", "Camry", "Corolla", "Highlander", "Prius", "RAV4", "Sequoia", "Sienna", "Tacoma", "Tundra"],
    "Volkswagen": ["Atlas", "Golf", "ID.4", "Jetta", "Passat", "Tiguan"]
}

async def scrape_craigslist(location, make, model, max_price, max_mileage):
    """Scrape Craigslist for vehicles"""
    results = []
    base_url = f"https://{location}.craigslist.org/search/cta"
    
    params = {
        'query': f"{make} {model}",
        'max_price': max_price,
        'auto_miles': f'1-{max_mileage}',
        'sort': 'date'
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{base_url}?{'&'.join([f'{k}={v}' for k,v in params.items()])}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    listings = soup.find_all('li', class_='cl-static-search-result')
                    
                    for listing in listings[:20]:
                        try:
                            title_elem = listing.find('div', class_='title')
                            price_elem = listing.find('div', class_='price')
                            link_elem = listing.find('a')
                            
                            if title_elem and price_elem and link_elem:
                                title = title_elem.text.strip()
                                price_text = price_elem.text.strip()
                                price = int(re.sub(r'[^\d]', '', price_text)) if price_text else 0
                                url = link_elem['href'] if link_elem.get('href', '').startswith('http') else f"https://{location}.craigslist.org{link_elem['href']}"
                                
                                results.append({
                                    'title': title,
                                    'price': price,
                                    'mileage': 'N/A',
                                    'url': url,
                                    'source': 'Craigslist',
                                    'location': location.title()
                                })
                        except Exception as e:
                            continue
    except Exception as e:
        print(f"Craigslist error: {e}")
    
    return results

async def scrape_cargurus(location, make, model, max_price, max_mileage):
    """Scrape CarGurus for vehicles"""
    results = []
    
    # Map location to zip code (Milwaukee area)
    location_map = {
        'milwaukee': '53202',
        'madison': '53703',
        'chicago': '60601'
    }
    zip_code = location_map.get(location.lower(), '53202')
    
    base_url = "https://www.cargurus.com/Cars/inventorylisting/viewDetailsFilterViewInventoryListing.action"
    
    params = {
        'zip': zip_code,
        'maxPrice': max_price,
        'maxMileage': max_mileage,
        'distance': 50,
        'entitySelectingHelper.selectedEntity': f"{make}_{model}".replace(' ', '_')
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            url = base_url + '?' + '&'.join([f'{k}={v}' for k, v in params.items()])
            
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # CarGurus uses various class names, try multiple selectors
                    listings = soup.find_all(['div', 'article'], class_=re.compile('listing|result|car-blade'))
                    
                    for listing in listings[:15]:
                        try:
                            title = listing.find(['h4', 'h3', 'a'], class_=re.compile('title|name'))
                            price = listing.find(['span', 'div'], class_=re.compile('price'))
                            mileage = listing.find(['span', 'div'], class_=re.compile('mileage'))
                            link = listing.find('a', href=True)
                            
                            if title and price:
                                price_val = int(re.sub(r'[^\d]', '', price.text)) if price.text else 0
                                mileage_val = mileage.text.strip() if mileage else 'N/A'
                                url = f"https://www.cargurus.com{link['href']}" if link and not link['href'].startswith('http') else (link['href'] if link else '#')
                                
                                results.append({
                                    'title': title.text.strip(),
                                    'price': price_val,
                                    'mileage': mileage_val,
                                    'url': url,
                                    'source': 'CarGurus',
                                    'location': location.title()
                                })
                        except Exception as e:
                            continue
    except Exception as e:
        print(f"CarGurus error: {e}")
    
    return results

async def scrape_cars_com(location, make, model, max_price, max_mileage):
    """Scrape Cars.com for vehicles"""
    results = []
    
    location_map = {
        'milwaukee': '53202',
        'madison': '53703',
        'chicago': '60601'
    }
    zip_code = location_map.get(location.lower(), '53202')
    
    make_slug = make.lower().replace(' ', '-')
    model_slug = model.lower().replace(' ', '-')
    
    base_url = f"https://www.cars.com/shopping/results/"
    params = {
        'stock_type': 'used',
        'makes[]': make.lower(),
        'models[]': f"{make.lower()}-{model_slug}",
        'maximum_distance': 50,
        'zip': zip_code,
        'price_max': max_price,
        'maximum_miles': max_mileage
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            url = base_url + '?' + '&'.join([f'{k}={v}' for k, v in params.items()])
            
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    listings = soup.find_all('div', class_=re.compile('vehicle-card'))
                    
                    for listing in listings[:15]:
                        try:
                            title = listing.find(['h2', 'h3'], class_=re.compile('title'))
                            price = listing.find('span', class_=re.compile('primary-price'))
                            mileage = listing.find('div', class_=re.compile('mileage'))
                            link = listing.find('a', href=True)
                            
                            if title and price:
                                price_val = int(re.sub(r'[^\d]', '', price.text)) if price.text else 0
                                mileage_val = mileage.text.strip() if mileage else 'N/A'
                                url = f"https://www.cars.com{link['href']}" if link and not link['href'].startswith('http') else (link['href'] if link else '#')
                                
                                results.append({
                                    'title': title.text.strip(),
                                    'price': price_val,
                                    'mileage': mileage_val,
                                    'url': url,
                                    'source': 'Cars.com',
                                    'location': location.title()
                                })
                        except Exception as e:
                            continue
    except Exception as e:
        print(f"Cars.com error: {e}")
    
    return results

async def scrape_autotrader(location, make, model, max_price, max_mileage):
    """Scrape AutoTrader for vehicles"""
    results = []
    
    location_map = {
        'milwaukee': '53202',
        'madison': '53703',
        'chicago': '60601'
    }
    zip_code = location_map.get(location.lower(), '53202')
    
    base_url = "https://www.autotrader.com/cars-for-sale/all-cars"
    
    params = {
        'zip': zip_code,
        'searchRadius': 50,
        'priceRange': f'0-{max_price}',
        'maxMileage': max_mileage,
        'makeCodeList': make.upper(),
        'modelCodeList': model.upper().replace(' ', '')
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            url = base_url + '?' + '&'.join([f'{k}={v}' for k, v in params.items()])
            
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    listings = soup.find_all('div', {'data-cmp': 'inventoryListing'})
                    
                    for listing in listings[:15]:
                        try:
                            title = listing.find('h2', class_=re.compile('heading'))
                            price = listing.find('span', class_=re.compile('first-price'))
                            mileage = listing.find('div', class_=re.compile('mileage'))
                            link = listing.find('a', {'data-cmp': 'subheading'})
                            
                            if title and price:
                                price_val = int(re.sub(r'[^\d]', '', price.text)) if price.text else 0
                                mileage_val = mileage.text.strip() if mileage else 'N/A'
                                url = f"https://www.autotrader.com{link['href']}" if link and link.get('href') and not link['href'].startswith('http') else (link['href'] if link and link.get('href') else '#')
                                
                                results.append({
                                    'title': title.text.strip(),
                                    'price': price_val,
                                    'mileage': mileage_val,
                                    'url': url,
                                    'source': 'AutoTrader',
                                    'location': location.title()
                                })
                        except Exception as e:
                            continue
    except Exception as e:
        print(f"AutoTrader error: {e}")
    
    return results

async def search_all_platforms(location, make, model, max_price, max_mileage):
    """Search all platforms in parallel"""
    tasks = [
        scrape_craigslist(location, make, model, max_price, max_mileage),
        scrape_cargurus(location, make, model, max_price, max_mileage),
        scrape_cars_com(location, make, model, max_price, max_mileage),
        scrape_autotrader(location, make, model, max_price, max_mileage)
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Flatten results
    all_results = []
    for result in results:
        if isinstance(result, list):
            all_results.extend(result)
    
    # Sort by price
    all_results.sort(key=lambda x: x.get('price', 999999))
    
    return all_results

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            make = data.get('make', 'Honda')
            model = data.get('model', 'Civic')
            max_price = int(data.get('max_price', 15000))
            max_mileage = int(data.get('max_mileage', 150000))
            location = data.get('location', 'milwaukee')
            
            # Run async search
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            results = loop.run_until_complete(
                search_all_platforms(location, make, model, max_price, max_mileage)
            )
            loop.close()
            
            response_data = {
                'success': True,
                'count': len(results),
                'results': results,
                'search_params': {
                    'make': make,
                    'model': model,
                    'max_price': max_price,
                    'max_mileage': max_mileage,
                    'location': location
                },
                'platforms': ['Craigslist', 'CarGurus', 'Cars.com', 'AutoTrader']
            }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode('utf-8'))
            
        except Exception as e:
            error_response = {
                'success': False,
                'error': str(e),
                'message': 'Search failed'
            }
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(error_response).encode('utf-8'))
    
    def do_GET(self):
        """Return available makes and models"""
        try:
            response_data = {
                'success': True,
                'vehicle_data': VEHICLE_DATA,
                'platforms': ['Craigslist', 'CarGurus', 'Cars.com', 'AutoTrader']
            }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode('utf-8'))
            
        except Exception as e:
            self.send_response(500)
            self.end_headers()
