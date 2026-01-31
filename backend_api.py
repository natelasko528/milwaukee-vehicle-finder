"""
Milwaukee Vehicle Finder - Backend API
Real-time vehicle scraping with advanced filtering
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime
import re
from typing import List, Dict, Optional
import json

app = Flask(__name__)
CORS(app)

class VehicleScraper:
    """Multi-platform vehicle scraper with image extraction"""
    
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
            'auto_title_status': 1,  # clean title
        }
        
        try:
            async with session.get(base_url, params=params, headers=self.headers, timeout=10) as response:
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
                                
                                # Get detailed listing for images
                                images = await self._get_craigslist_images(session, url)
                                
                                # Extract mileage from title
                                mileage = self._extract_mileage(title_elem.text)
                                
                                results.append({
                                    'title': title_elem.text.strip(),
                                    'price': self._extract_price(price_elem.text if price_elem else '0'),
                                    'url': url,
                                    'source': 'Craigslist',
                                    'location': location,
                                    'images': images,
                                    'mileage': mileage,
                                    'scraped_at': datetime.now().isoformat()
                                })
                        except Exception as e:
                            print(f"Error parsing Craigslist listing: {e}")
                            continue
        except Exception as e:
            print(f"Craigslist scraping error: {e}")
        
        return results
    
    async def _get_craigslist_images(self, session, url):
        """Extract images from Craigslist listing"""
        images = []
        try:
            async with session.get(url, headers=self.headers, timeout=10) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Find image gallery
                    for img in soup.find_all('img', class_='slide')[:5]:
                        img_url = img.get('src')
                        if img_url:
                            images.append(img_url)
                    
                    # Fallback to thumbnails
                    if not images:
                        for img in soup.find_all('img'):
                            img_url = img.get('src', '')
                            if '600x450' in img_url or 'images.craigslist.org' in img_url:
                                images.append(img_url)
        except:
            pass
        
        return images[:5]  # Limit to 5 images
    
    async def scrape_facebook_marketplace(self, session, location, make, model, max_price, max_mileage):
        """Scrape Facebook Marketplace (requires selenium for dynamic content)"""
        # Facebook Marketplace requires browser automation due to React/dynamic loading
        # This is a placeholder for the architecture - would need Playwright/Selenium
        return []
    
    async def scrape_cargurus(self, session, make, model, max_price, max_mileage, zip_code):
        """Scrape CarGurus with filters"""
        results = []
        base_url = "https://www.cargurus.com/Cars/inventorylisting/viewDetailsFilterViewInventoryListing.action"
        
        params = {
            'sourceContext': 'carGurusHomePageModel',
            'entitySelectingHelper.selectedEntity': 'm11',
            'zip': zip_code,
            'distance': 50,
            'maxPrice': max_price,
            'maxMileage': max_mileage,
        }
        
        # Add make/model specific search
        search_path = f"/Cars/{make}-{model}"
        
        try:
            async with session.get(f"https://www.cargurus.com{search_path}", params=params, headers=self.headers, timeout=10) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Parse listings (CarGurus uses complex structure)
                    for listing in soup.find_all('div', class_='_listing-row')[:15]:
                        try:
                            # Extract data from listing
                            title = listing.find('h4', class_='_title')
                            price = listing.find('span', class_='_price')
                            link = listing.find('a', href=True)
                            img = listing.find('img', class_='_image')
                            
                            if title and link:
                                results.append({
                                    'title': title.text.strip(),
                                    'price': self._extract_price(price.text if price else '0'),
                                    'url': f"https://www.cargurus.com{link['href']}",
                                    'source': 'CarGurus',
                                    'images': [img['src']] if img and img.get('src') else [],
                                    'mileage': self._extract_mileage(listing.text),
                                    'scraped_at': datetime.now().isoformat()
                                })
                        except Exception as e:
                            print(f"Error parsing CarGurus listing: {e}")
                            continue
        except Exception as e:
            print(f"CarGurus scraping error: {e}")
        
        return results
    
    async def scrape_cars_com(self, session, make, model, max_price, max_mileage, zip_code):
        """Scrape Cars.com with filters"""
        results = []
        base_url = "https://www.cars.com/shopping/results/"
        
        params = {
            'makes[]': make.lower(),
            'models[]': f"{make.lower()}-{model.lower()}",
            'maximum_distance': 50,
            'zip': zip_code,
            'price_max': max_price,
            'maximum_mileage': max_mileage,
            'stock_type': 'used',
        }
        
        try:
            async with session.get(base_url, params=params, headers=self.headers, timeout=10) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    for listing in soup.find_all('div', class_='vehicle-card')[:15]:
                        try:
                            title = listing.find('h2', class_='title')
                            price = listing.find('span', class_='primary-price')
                            link = listing.find('a', class_='vehicle-card-link')
                            img = listing.find('img', class_='vehicle-image')
                            mileage_elem = listing.find('div', class_='mileage')
                            
                            if title and link:
                                results.append({
                                    'title': title.text.strip(),
                                    'price': self._extract_price(price.text if price else '0'),
                                    'url': link['href'] if link['href'].startswith('http') else f"https://www.cars.com{link['href']}",
                                    'source': 'Cars.com',
                                    'images': [img['src']] if img and img.get('src') else [],
                                    'mileage': self._extract_mileage(mileage_elem.text if mileage_elem else ''),
                                    'scraped_at': datetime.now().isoformat()
                                })
                        except Exception as e:
                            print(f"Error parsing Cars.com listing: {e}")
                            continue
        except Exception as e:
            print(f"Cars.com scraping error: {e}")
        
        return results
    
    async def scrape_autotrader(self, session, make, model, max_price, max_mileage, zip_code):
        """Scrape AutoTrader with filters"""
        results = []
        base_url = "https://www.autotrader.com/cars-for-sale/all-cars"
        
        params = {
            'makeCodeList': make.upper(),
            'modelCodeList': model.upper(),
            'zip': zip_code,
            'maxPrice': max_price,
            'maxMileage': max_mileage,
            'searchRadius': 50,
        }
        
        try:
            async with session.get(base_url, params=params, headers=self.headers, timeout=10) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    for listing in soup.find_all('div', {'data-cmp': 'inventoryListing'})[:15]:
                        try:
                            title = listing.find('h3')
                            price = listing.find('span', {'data-cmp': 'price'})
                            link = listing.find('a', {'data-cmp': 'listingTitle'})
                            img = listing.find('img', {'data-cmp': 'image'})
                            
                            if title and link:
                                results.append({
                                    'title': title.text.strip(),
                                    'price': self._extract_price(price.text if price else '0'),
                                    'url': f"https://www.autotrader.com{link['href']}",
                                    'source': 'AutoTrader',
                                    'images': [img['src']] if img and img.get('src') else [],
                                    'mileage': self._extract_mileage(listing.text),
                                    'scraped_at': datetime.now().isoformat()
                                })
                        except Exception as e:
                            print(f"Error parsing AutoTrader listing: {e}")
                            continue
        except Exception as e:
            print(f"AutoTrader scraping error: {e}")
        
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
            tasks = [
                self.scrape_craigslist(session, location, make, model, max_price, max_mileage),
                self.scrape_cargurus(session, make, model, max_price, max_mileage, zip_code),
                self.scrape_cars_com(session, make, model, max_price, max_mileage, zip_code),
                self.scrape_autotrader(session, make, model, max_price, max_mileage, zip_code),
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Flatten results
            all_vehicles = []
            for result in results:
                if isinstance(result, list):
                    all_vehicles.extend(result)
            
            return all_vehicles


# Global scraper instance
scraper = VehicleScraper()

@app.route('/api/search', methods=['POST'])
def search_vehicles():
    """
    Real-time vehicle search endpoint
    
    POST /api/search
    {
        "make": "Toyota",
        "model": "Camry",
        "max_price": 8000,
        "max_mileage": 150000,
        "location": "milwaukee",
        "zip_code": "53202"
    }
    """
    try:
        data = request.get_json()
        
        make = data.get('make', 'Toyota')
        model = data.get('model', 'Camry')
        max_price = int(data.get('max_price', 15000))
        max_mileage = int(data.get('max_mileage', 200000))
        location = data.get('location', 'milwaukee')
        zip_code = data.get('zip_code', '53202')
        
        # Run async scraping
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        vehicles = loop.run_until_complete(
            scraper.search_all_platforms(make, model, max_price, max_mileage, location, zip_code)
        )
        loop.close()
        
        # Sort by price
        vehicles.sort(key=lambda x: x.get('price', 999999))
        
        return jsonify({
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
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
