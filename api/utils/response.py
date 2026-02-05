import json

def cors_headers():
    """Return standard CORS headers dict."""
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
    }

def send_json(handler, status, data):
    """Send a JSON response with CORS headers."""
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    for k, v in cors_headers().items():
        handler.send_header(k, v)
    handler.end_headers()
    handler.wfile.write(json.dumps(data).encode())

def send_options(handler):
    """Handle CORS preflight OPTIONS request."""
    handler.send_response(204)
    for k, v in cors_headers().items():
        handler.send_header(k, v)
    handler.end_headers()

def error_response(message, hint=None):
    """Create standardized error response dict."""
    resp = {"success": False, "error": message}
    if hint:
        resp["hint"] = hint
    return resp
