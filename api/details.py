"""
API Endpoint: Vehicle Details with Image Extraction
Fetches full details from original listing including all photos
"""

from http.server import BaseHTTPRequestHandler
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, urljoin
import re
import ipaddress
import socket

from api.utils.response import cors_headers, send_json, send_options, error_response

ALLOWED_DOMAINS = {
    'craigslist.org',
    'cargurus.com',
    'cars.com',
    'autotrader.com',
}


def _is_url_allowed(url):
    """Validate that a URL points to an allowed domain and not a private IP."""
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    # Check scheme
    if parsed.scheme not in ('http', 'https'):
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    # Only allow http for craigslist; all others must be https
    if parsed.scheme == 'http':
        if not hostname.endswith('craigslist.org'):
            return False

    # Check hostname against allowed domains (supports subdomains)
    domain_ok = any(
        hostname == domain or hostname.endswith('.' + domain)
        for domain in ALLOWED_DOMAINS
    )
    if not domain_ok:
        return False

    # Block private/internal IPs
    try:
        addr = ipaddress.ip_address(hostname)
        if addr.is_private or addr.is_loopback or addr.is_reserved:
            return False
    except ValueError:
        # hostname is not a raw IP, resolve it
        try:
            resolved = socket.getaddrinfo(hostname, None)
            for entry in resolved:
                addr = ipaddress.ip_address(entry[4][0])
                if addr.is_private or addr.is_loopback or addr.is_reserved:
                    return False
        except socket.gaierror:
            return False

    return True

class DetailsFetcher:
    """Fetch detailed vehicle information from listing URLs"""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    
    async def fetch_craigslist_details(self, url, session):
        """Extract all images and details from Craigslist listing"""
        try:
            async with session.get(url, headers=self.headers, timeout=10) as response:
                if response.status != 200:
                    return None
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                details = {}
                
                # Extract all images
                images = []
                
                # Method 1: Gallery images
                gallery = soup.find('div', {'class': 'gallery'})
                if gallery:
                    for img in gallery.find_all('img'):
                        src = img.get('src')
                        if src:
                            # Convert thumbnail to full size
                            full_src = re.sub(r'_\d+x\d+', '_600x450', src)
                            images.append(full_src)
                
                # Method 2: Thumbnail container
                thumbs = soup.find('div', {'id': 'thumbs'})
                if thumbs:
                    for link in thumbs.find_all('a'):
                        href = link.get('href')
                        if href:
                            images.append(href)
                
                # Method 3: Image swipe container
                swipe = soup.find('div', {'class': 'swipe'})
                if swipe:
                    for img in swipe.find_all('img'):
                        src = img.get('src')
                        if src and src not in images:
                            images.append(src)
                
                details['images'] = list(set(images))  # Remove duplicates
                details['image_url'] = images[0] if images else None
                
                # Extract description
                desc_section = soup.find('section', {'id': 'postingbody'})
                if desc_section:
                    # Remove "QR Code Link to This Post" text
                    for qr in desc_section.find_all('div', {'class': 'print-qrcode-container'}):
                        qr.decompose()
                    details['description'] = desc_section.get_text(strip=True)
                
                # Extract attributes
                attrs = soup.find('div', {'class': 'mapAndAttrs'})
                if attrs:
                    attr_groups = attrs.find_all('p', {'class': 'attrgroup'})
                    for group in attr_groups:
                        for span in group.find_all('span'):
                            text = span.get_text(strip=True)
                            
                            # Parse specific attributes
                            if 'VIN:' in text:
                                details['vin'] = text.replace('VIN:', '').strip()
                            elif 'condition:' in text:
                                details['condition'] = text.replace('condition:', '').strip()
                            elif 'cylinders:' in text:
                                details['cylinders'] = text.replace('cylinders:', '').strip()
                            elif 'drive:' in text:
                                details['drive'] = text.replace('drive:', '').strip()
                            elif 'fuel:' in text:
                                details['fuel'] = text.replace('fuel:', '').strip()
                            elif 'title status:' in text:
                                details['title_status'] = text.replace('title status:', '').strip()
                            elif 'transmission:' in text:
                                details['transmission'] = text.replace('transmission:', '').strip()
                            elif 'type:' in text:
                                details['type'] = text.replace('type:', '').strip()
                            elif 'paint color:' in text:
                                details['color'] = text.replace('paint color:', '').strip()
                
                return details
                
        except Exception as e:
            print(f"Craigslist details error: {e}")
            return None
    
    async def fetch_cargurus_details(self, url, session):
        """Extract all images and details from CarGurus listing"""
        try:
            async with session.get(url, headers=self.headers, timeout=10) as response:
                if response.status != 200:
                    return None
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                details = {}
                images = []
                
                # Extract images from gallery
                gallery = soup.find('div', {'class': 'photoGallery'})
                if gallery:
                    for img in gallery.find_all('img'):
                        src = img.get('src') or img.get('data-src')
                        if src and 'cargurus' in src:
                            # Get high-res version
                            high_res = re.sub(r'/\d+x\d+/', '/640x480/', src)
                            images.append(high_res)
                
                # Alternative: Look for picture elements
                for picture in soup.find_all('picture'):
                    for source in picture.find_all('source'):
                        srcset = source.get('srcset')
                        if srcset:
                            # Get largest image from srcset
                            urls = [url.strip().split(' ')[0] for url in srcset.split(',')]
                            images.extend(urls)
                
                details['images'] = list(set(images))[:20]  # Limit to 20 images
                details['image_url'] = images[0] if images else None
                
                # Extract description
                desc = soup.find('div', {'class': 'dealerDescription'})
                if not desc:
                    desc = soup.find('div', {'class': 'sellerComments'})
                if desc:
                    details['description'] = desc.get_text(strip=True)
                
                # Extract specs
                specs = soup.find('dl', {'class': 'listingDetails'})
                if specs:
                    dts = specs.find_all('dt')
                    dds = specs.find_all('dd')
                    for dt, dd in zip(dts, dds):
                        key = dt.get_text(strip=True).lower()
                        value = dd.get_text(strip=True)
                        
                        if 'transmission' in key:
                            details['transmission'] = value
                        elif 'fuel' in key:
                            details['fuel'] = value
                        elif 'drive' in key:
                            details['drive'] = value
                        elif 'color' in key or 'exterior' in key:
                            details['color'] = value
                        elif 'interior' in key:
                            details['interior_color'] = value
                        elif 'mpg' in key:
                            details['mpg'] = value
                
                return details
                
        except Exception as e:
            print(f"CarGurus details error: {e}")
            return None
    
    async def fetch_cars_com_details(self, url, session):
        """Extract all images and details from Cars.com listing"""
        try:
            async with session.get(url, headers=self.headers, timeout=10) as response:
                if response.status != 200:
                    return None
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                details = {}
                images = []
                
                # Extract images from media gallery
                gallery = soup.find('div', {'class': 'media-gallery'})
                if gallery:
                    for img in gallery.find_all('img'):
                        src = img.get('src') or img.get('data-src')
                        if src and 'cars.com' in src:
                            images.append(src)
                
                # Look for picture carousel
                carousel = soup.find('div', {'class': 'image-carousel'})
                if carousel:
                    for img in carousel.find_all('img'):
                        src = img.get('src') or img.get('data-src')
                        if src:
                            images.append(src)
                
                details['images'] = list(set(images))[:20]
                details['image_url'] = images[0] if images else None
                
                # Extract description
                desc = soup.find('div', {'class': 'seller-description'})
                if desc:
                    details['description'] = desc.get_text(strip=True)
                
                # Extract key specs
                specs = soup.find('dl', {'class': 'fancy-description-list'})
                if specs:
                    dts = specs.find_all('dt')
                    dds = specs.find_all('dd')
                    for dt, dd in zip(dts, dds):
                        key = dt.get_text(strip=True).lower()
                        value = dd.get_text(strip=True)
                        
                        if 'transmission' in key:
                            details['transmission'] = value
                        elif 'drivetrain' in key:
                            details['drive'] = value
                        elif 'fuel' in key:
                            details['fuel'] = value
                        elif 'exterior color' in key:
                            details['color'] = value
                        elif 'interior color' in key:
                            details['interior_color'] = value
                        elif 'mpg' in key:
                            details['mpg'] = value
                
                return details
                
        except Exception as e:
            print(f"Cars.com details error: {e}")
            return None
    
    async def fetch_autotrader_details(self, url, session):
        """Extract all images and details from AutoTrader listing"""
        try:
            async with session.get(url, headers=self.headers, timeout=10) as response:
                if response.status != 200:
                    return None
                
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                details = {}
                images = []
                
                # Extract images
                for img in soup.find_all('img'):
                    src = img.get('src') or img.get('data-src')
                    if src and ('autotrader' in src or 'atcdn' in src):
                        # Get full-size image
                        if '?w=' in src:
                            src = re.sub(r'\?w=\d+', '?w=1920', src)
                        images.append(src)
                
                details['images'] = list(set(images))[:20]
                details['image_url'] = images[0] if images else None
                
                # Extract description
                desc = soup.find('div', {'class': 'comments'})
                if desc:
                    details['description'] = desc.get_text(strip=True)
                
                return details
                
        except Exception as e:
            print(f"AutoTrader details error: {e}")
            return None
    
    async def fetch_details(self, url):
        """Route to appropriate fetcher based on URL"""
        async with aiohttp.ClientSession() as session:
            if 'craigslist.org' in url:
                return await self.fetch_craigslist_details(url, session)
            elif 'cargurus.com' in url:
                return await self.fetch_cargurus_details(url, session)
            elif 'cars.com' in url:
                return await self.fetch_cars_com_details(url, session)
            elif 'autotrader.com' in url:
                return await self.fetch_autotrader_details(url, session)
            else:
                return None


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            # Parse query parameters
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            
            url = params.get('url', [None])[0]
            
            if not url:
                send_json(self, 400, error_response('Missing url parameter'))
                return

            # SSRF protection: validate URL before fetching
            if not _is_url_allowed(url):
                send_json(self, 400, error_response('URL not allowed. Only Craigslist, CarGurus, Cars.com, and AutoTrader URLs are supported.'))
                return

            # Fetch details
            fetcher = DetailsFetcher()
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            details = loop.run_until_complete(fetcher.fetch_details(url))
            loop.close()
            
            if details:
                send_json(self, 200, {
                    'success': True,
                    'details': details
                })
            else:
                send_json(self, 500, error_response('Failed to fetch details'))
                
        except Exception as e:
            send_json(self, 500, error_response(str(e)))

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        send_options(self)
