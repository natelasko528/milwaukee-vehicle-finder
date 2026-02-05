"""
Test to verify the HTTP server fixture works correctly.
This test doesn't require a browser.
"""
import urllib.request


def test_base_url_fixture_serves_html(base_url):
    """Test that the base_url fixture serves the index.html file."""
    response = urllib.request.urlopen(base_url)
    content = response.read().decode('utf-8')

    # Verify we got HTML content
    assert '<!DOCTYPE html>' in content, "Should serve HTML content"
    assert '<title>Milwaukee Vehicle Finder</title>' in content, "Should serve index.html"
    assert 'Alpine.js' in content or 'alpinejs' in content, "Should contain Alpine.js reference"

    print(f"✓ HTTP server at {base_url} is serving index.html correctly")


def test_base_url_is_valid(base_url):
    """Test that base_url is a valid URL."""
    assert base_url.startswith('http://127.0.0.1:'), f"base_url should be localhost, got: {base_url}"

    # Extract port
    port = int(base_url.split(':')[-1])
    assert 1024 < port < 65535, f"Port should be in valid range, got: {port}"

    print(f"✓ base_url {base_url} is valid")
