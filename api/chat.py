"""
API Endpoint: AI Chat Assistant (Google Gemini)
Provides automotive advice using Gemini AI with vehicle context awareness.
Deployed as a Vercel serverless function.

Primary model: gemini-2.5-flash
Fallback model: gemini-2.0-flash
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
# Model configuration
# ---------------------------------------------------------------------------

_PRIMARY_MODEL = "gemini-2.5-flash"
_FALLBACK_MODEL = "gemini-2.0-flash"

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are the DOOM SLAYER's Vehicle Intelligence AI, built into Milwaukee Vehicle Finder.\n"
    "You are an expert automotive advisor who helps users evaluate used vehicles in the Milwaukee area.\n\n"

    "Your core knowledge areas:\n"
    "- **Vehicle reliability**: Known mechanical issues, longevity expectations, and maintenance costs "
    "for specific makes, models, and model years.\n"
    "- **Fair pricing & market comparison**: Whether a listing price is competitive compared to "
    "KBB, Edmunds, and current local market conditions. Reference the user's actual search results "
    "when available to compare across listings.\n"
    "- **Safety ratings & recall awareness**: NHTSA safety ratings, IIHS scores, and any known "
    "recalls or technical service bulletins (TSBs) for the vehicle in question. Always flag active "
    "recalls — unfixed recalls are a serious safety and negotiation point.\n"
    "- **Dealership reputation**: General guidance on buying from private sellers vs. dealerships, "
    "red flags in dealer listings (e.g., suspiciously low prices, salvage titles marketed as clean), "
    "and tips for verifying dealer credibility in the Milwaukee area.\n"
    "- **Owner sentiment**: Summarize common owner complaints and praise for specific vehicles based "
    "on widely reported owner feedback (forums, long-term reviews). Mention recurring themes like "
    "transmission issues, rust-prone models, or surprisingly reliable budget picks.\n"
    "- **Insurance & total cost of ownership**: Rough insurance cost factors, fuel economy, typical "
    "repair bills, and depreciation outlook.\n"
    "- **Purchase negotiations**: Practical tactics for negotiating price, what inspections to request, "
    "and when to walk away from a deal.\n\n"

    "When the user is viewing a specific vehicle, use the provided context to give targeted advice.\n"
    "Always mention important safety recalls when relevant.\n\n"

    "Keep responses concise (2-4 paragraphs max). Use bullet points for lists.\n"
    "Be direct, practical, and honest — if a vehicle is overpriced or unreliable, say so clearly.\n"
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


def _try_gemini_model(model_name, api_key, history, latest_text):
    """
    Attempt to chat with a specific Gemini model via REST API.
    Returns the response text on success, raises on failure.
    """
    import urllib.request
    import urllib.error

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/"
        f"models/{model_name}:generateContent?key={api_key}"
    )

    # Build contents array: system instruction + history + latest message
    contents = []

    # Add conversation history
    for entry in history:
        contents.append({
            "role": entry["role"],
            "parts": [{"text": entry["parts"][0]}],
        })

    # Add the latest user message
    contents.append({
        "role": "user",
        "parts": [{"text": latest_text}],
    })

    payload = json.dumps({
        "system_instruction": {
            "parts": [{"text": SYSTEM_PROMPT}]
        },
        "contents": contents,
        "generationConfig": {
            "temperature": 0.8,
            "maxOutputTokens": 2048,
        },
    }).encode()

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=45) as resp:
        body = json.loads(resp.read().decode())

    text = (
        body.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )

    if not text:
        raise ValueError(f"Empty response from {model_name}")

    return text


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
            "primary_model": _PRIMARY_MODEL,
            "fallback_model": _FALLBACK_MODEL,
            "version": "2.0.0",
        })

    # -- POST (chat) -------------------------------------------------------

    def do_POST(self):
        # Rate limiting
        client_ip = self.client_address[0] if self.client_address else "unknown"
        if not _check_rate_limit(client_ip):
            self._send_json(429, {
                "success": False,
                "error": "Rate limit exceeded. Max 30 requests per minute.",
                "hint": "Please wait a moment before sending another message.",
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
                "hint": "Ensure the request body is valid JSON with a 'messages' array.",
            })
            return

        messages = body.get("messages")
        if not messages or not isinstance(messages, list):
            self._send_json(400, {
                "success": False,
                "error": "Request must include a 'messages' array.",
                "hint": "Send {\"messages\": [{\"role\": \"user\", \"content\": \"your question\"}]}.",
            })
            return

        context = body.get("context")

        # Check API key
        api_key = os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            self._send_json(500, {
                "success": False,
                "error": "GOOGLE_API_KEY is not configured on the server.",
                "hint": "The server administrator needs to set the GOOGLE_API_KEY environment variable in Vercel.",
            })
            return

        # Call Gemini with model fallback
        try:
            history, latest_text = _convert_messages(messages, context)

            # Try primary model first, fall back to secondary on failure
            used_model = _PRIMARY_MODEL
            primary_error = None
            try:
                response_text = _try_gemini_model(_PRIMARY_MODEL, api_key, history, latest_text)
            except Exception as primary_exc:
                primary_error = str(primary_exc)
                print(f"[chat] Primary model {_PRIMARY_MODEL} failed: {primary_error}")
                print(f"[chat] Falling back to {_FALLBACK_MODEL}...")
                try:
                    response_text = _try_gemini_model(_FALLBACK_MODEL, api_key, history, latest_text)
                    used_model = _FALLBACK_MODEL
                except Exception as fallback_exc:
                    traceback.print_exc()
                    self._send_json(500, {
                        "success": False,
                        "error": "Both AI models failed to generate a response.",
                        "details": {
                            "primary_model": _PRIMARY_MODEL,
                            "primary_error": primary_error,
                            "fallback_model": _FALLBACK_MODEL,
                            "fallback_error": str(fallback_exc),
                        },
                        "hint": (
                            "This may be a temporary issue with the Gemini API. "
                            "Try again in a few seconds. If the problem persists, "
                            "the API key may be invalid or have exceeded its quota."
                        ),
                    })
                    return

            result = {
                "success": True,
                "response": response_text,
                "model": used_model,
            }
            if primary_error:
                result["fallback_used"] = True
            self._send_json(200, result)

        except Exception as e:
            traceback.print_exc()
            error_msg = str(e)
            hint = "An unexpected error occurred. Try again shortly."

            # Provide more specific hints for common errors
            lower_err = error_msg.lower()
            if "api_key" in lower_err or "authentication" in lower_err or "permission" in lower_err:
                hint = "The API key appears to be invalid or lacks permissions. Check the GOOGLE_API_KEY in Vercel settings."
            elif "quota" in lower_err or "rate" in lower_err or "resource" in lower_err:
                hint = "The Gemini API quota or rate limit has been reached. Wait a minute and try again."
            elif "not found" in lower_err or "404" in lower_err:
                hint = f"The requested model may not be available. The server will attempt fallback models automatically."
            elif "timeout" in lower_err or "deadline" in lower_err:
                hint = "The AI model took too long to respond. Try a shorter or simpler question."

            self._send_json(500, {
                "success": False,
                "error": f"AI service error: {error_msg}",
                "hint": hint,
            })
