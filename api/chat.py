"""
API Endpoint: AI Chat Assistant (Google Gemini 2.5 Flash)
Provides automotive advice using Gemini AI with vehicle context awareness.
Deployed as a Vercel serverless function.
"""

from http.server import BaseHTTPRequestHandler
import json
import os
import time
import traceback

# ---------------------------------------------------------------------------
# Rate limiter (in-memory, per-instance)
# ---------------------------------------------------------------------------

_rate_limit_store = {}  # {ip: [timestamp, ...]}
_RATE_LIMIT_MAX = 30
_RATE_LIMIT_WINDOW = 60  # seconds


def _check_rate_limit(ip):
    """Return True if request is allowed, False if rate-limited."""
    now = time.time()
    if ip not in _rate_limit_store:
        _rate_limit_store[ip] = []

    # Prune old entries
    _rate_limit_store[ip] = [
        t for t in _rate_limit_store[ip] if now - t < _RATE_LIMIT_WINDOW
    ]

    if len(_rate_limit_store[ip]) >= _RATE_LIMIT_MAX:
        return False

    _rate_limit_store[ip].append(now)
    return True


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are the DOOM SLAYER's Vehicle Intelligence AI, built into Milwaukee Vehicle Finder.\n"
    "You are an expert automotive advisor who helps users evaluate used vehicles in the Milwaukee area.\n"
    "Your knowledge covers vehicle reliability, fair pricing, common issues, maintenance costs, "
    "insurance estimates, safety ratings, and purchase negotiations.\n\n"
    "When the user is viewing a specific vehicle, use the provided context to give targeted advice.\n"
    "When comparing prices, reference the user's actual search results when available.\n"
    "Always mention important safety recalls when relevant.\n\n"
    "Keep responses concise (2-4 paragraphs max). Use bullet points for lists.\n"
    "Be direct, practical, and honest - if a vehicle is overpriced or unreliable, say so clearly.\n"
    "You have a slightly intense, no-nonsense personality fitting the Doom theme, but remain helpful and informative."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
    }


def _build_context_message(context):
    """Build a context string from the optional context object."""
    parts = []

    vehicle = context.get("current_vehicle") if context else None
    if vehicle:
        parts.append("--- CURRENT VEHICLE THE USER IS VIEWING ---")
        for key in ("title", "make", "model", "year", "price", "mileage"):
            if key in vehicle and vehicle[key] is not None:
                parts.append(f"  {key}: {vehicle[key]}")
        # Include any extra fields
        for key, val in vehicle.items():
            if key not in ("title", "make", "model", "year", "price", "mileage") and val is not None:
                parts.append(f"  {key}: {val}")
        parts.append("--- END VEHICLE ---")

    summary = context.get("search_results_summary") if context else None
    if summary:
        parts.append("--- USER'S SEARCH RESULTS SUMMARY ---")
        for key, val in summary.items():
            parts.append(f"  {key}: {val}")
        parts.append("--- END SUMMARY ---")

    return "\n".join(parts) if parts else None


def _convert_messages(messages, context):
    """
    Convert OpenAI-style messages to Gemini chat history + latest message.
    Returns (history, latest_user_text).
    history is a list of {"role": "user"|"model", "parts": [str]} dicts.
    """
    gemini_history = []

    # If context is available, inject it as the first user+model exchange
    context_text = _build_context_message(context)
    if context_text:
        gemini_history.append({
            "role": "user",
            "parts": [f"[System context — do not repeat this verbatim, just use it to inform your answers]\n{context_text}"]
        })
        gemini_history.append({
            "role": "model",
            "parts": ["Understood. I have the vehicle context loaded and ready to assist."]
        })

    # Convert all messages except the last user message into history
    if not messages:
        return gemini_history, ""

    # Build history from all but the last message
    for msg in messages[:-1]:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        gemini_role = "model" if role == "assistant" else "user"
        gemini_history.append({
            "role": gemini_role,
            "parts": [content],
        })

    # The last message should be the user's latest query
    latest = messages[-1]
    latest_text = latest.get("content", "")

    return gemini_history, latest_text


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

class handler(BaseHTTPRequestHandler):

    def _send_json(self, status_code, data):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        for key, val in _cors_headers().items():
            self.send_header(key, val)
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    # -- OPTIONS (CORS preflight) ------------------------------------------

    def do_OPTIONS(self):
        self.send_response(204)
        for key, val in _cors_headers().items():
            self.send_header(key, val)
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    # -- GET (health check) ------------------------------------------------

    def do_GET(self):
        self._send_json(200, {
            "status": "ok",
            "endpoint": "chat",
            "model": "gemini-2.5-flash-preview-05-20",
            "version": "1.0.0",
        })

    # -- POST (chat) -------------------------------------------------------

    def do_POST(self):
        # Rate limiting
        client_ip = self.client_address[0] if self.client_address else "unknown"
        if not _check_rate_limit(client_ip):
            self._send_json(429, {
                "success": False,
                "error": "Rate limit exceeded. Max 30 requests per minute.",
            })
            return

        # Read request body
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length) if content_length else b""
            body = json.loads(raw_body) if raw_body else {}
        except (json.JSONDecodeError, ValueError):
            self._send_json(400, {
                "success": False,
                "error": "Invalid JSON in request body.",
            })
            return

        messages = body.get("messages")
        if not messages or not isinstance(messages, list):
            self._send_json(400, {
                "success": False,
                "error": "Request must include a 'messages' array.",
            })
            return

        context = body.get("context")

        # Check API key
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            self._send_json(500, {
                "success": False,
                "error": "GOOGLE_API_KEY is not configured on the server.",
            })
            return

        # Call Gemini
        try:
            import google.generativeai as genai

            genai.configure(api_key=api_key)

            model = genai.GenerativeModel(
                model_name="gemini-2.5-flash-preview-05-20",
                system_instruction=SYSTEM_PROMPT,
            )

            history, latest_text = _convert_messages(messages, context)

            chat = model.start_chat(history=history)
            response = chat.send_message(latest_text)

            self._send_json(200, {
                "success": True,
                "response": response.text,
                "model": "gemini-2.5-flash-preview-05-20",
            })

        except ImportError:
            self._send_json(500, {
                "success": False,
                "error": "google-generativeai package is not installed.",
            })
        except Exception as e:
            traceback.print_exc()
            self._send_json(500, {
                "success": False,
                "error": f"Gemini API error: {str(e)}",
            })
