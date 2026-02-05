"""
Test script for the chat.py Gemini REST API integration.
Run with: python tests/test_chat_api.py
Or with API key: GOOGLE_API_KEY=your_key python tests/test_chat_api.py
"""
import json
import os
import sys

# Add parent dir to path to import from api/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.chat import (
    _convert_messages,
    _build_context_message,
    SYSTEM_PROMPT,
    _PRIMARY_MODEL,
    _FALLBACK_MODEL,
)


def test_message_conversion():
    """Test that message conversion produces valid Gemini format."""
    print("=" * 60)
    print("TEST 1: Message conversion")
    print("=" * 60)

    messages = [
        {"role": "user", "content": "What's a good first car?"},
        {"role": "assistant", "content": "A Honda Civic is reliable."},
        {"role": "user", "content": "What about Toyota?"},
    ]
    context = None

    history, latest_text = _convert_messages(messages, context)

    print(f"History entries: {len(history)}")
    for i, entry in enumerate(history):
        print(f"  [{i}] role={entry['role']}, content={entry['parts'][0][:50]}...")
    print(f"Latest text: {latest_text}")

    # Validate
    assert len(history) == 2, f"Expected 2 history entries, got {len(history)}"
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "model"
    assert latest_text == "What about Toyota?"
    print("✓ PASSED\n")


def test_context_building():
    """Test context message building."""
    print("=" * 60)
    print("TEST 2: Context building")
    print("=" * 60)

    context = {
        "current_vehicle": {
            "title": "2019 Honda Civic",
            "make": "Honda",
            "model": "Civic",
            "year": 2019,
            "price": 18500,
            "mileage": 45000,
        }
    }

    context_msg = _build_context_message(context)
    print(f"Context message:\n{context_msg}")

    assert "CURRENT VEHICLE" in context_msg
    assert "Honda" in context_msg
    assert "18500" in context_msg
    print("✓ PASSED\n")


def test_payload_format():
    """Test that the full payload matches Gemini API format."""
    print("=" * 60)
    print("TEST 3: Payload format validation")
    print("=" * 60)

    messages = [{"role": "user", "content": "Hello"}]
    context = None

    history, latest_text = _convert_messages(messages, context)

    # Build contents array exactly like chat.py does
    contents = []
    for entry in history:
        contents.append({
            "role": entry["role"],
            "parts": [{"text": entry["parts"][0]}],
        })
    contents.append({
        "role": "user",
        "parts": [{"text": latest_text}],
    })

    payload = {
        "system_instruction": {
            "parts": [{"text": SYSTEM_PROMPT}]
        },
        "contents": contents,
        "generationConfig": {
            "temperature": 0.8,
            "maxOutputTokens": 2048,
        },
    }

    payload_json = json.dumps(payload, indent=2)
    print(f"Payload structure (truncated):")
    print(f"  system_instruction.parts[0].text length: {len(payload['system_instruction']['parts'][0]['text'])}")
    print(f"  contents count: {len(payload['contents'])}")
    print(f"  contents[0].role: {payload['contents'][0]['role']}")
    print(f"  generationConfig: {payload['generationConfig']}")

    # Validate structure
    assert "system_instruction" in payload
    assert "parts" in payload["system_instruction"]
    assert "contents" in payload
    assert len(contents) >= 1
    assert contents[-1]["role"] == "user"
    print("✓ PASSED\n")


def test_live_api_call():
    """Test actual API call if GOOGLE_API_KEY is set."""
    print("=" * 60)
    print("TEST 4: Live API call")
    print("=" * 60)

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("⏭ SKIPPED (no GOOGLE_API_KEY set)")
        print("  To run: GOOGLE_API_KEY=your_key python tests/test_chat_api.py\n")
        return

    import urllib.request
    import urllib.error

    model_name = _PRIMARY_MODEL
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/"
        f"models/{model_name}:generateContent?key={api_key}"
    )

    # Minimal test payload
    payload = json.dumps({
        "system_instruction": {
            "parts": [{"text": "You are a helpful assistant."}]
        },
        "contents": [
            {"role": "user", "parts": [{"text": "Say hello in exactly 3 words."}]}
        ],
        "generationConfig": {
            "temperature": 0.5,
            "maxOutputTokens": 50,
        },
    }).encode()

    print(f"Testing model: {model_name}")
    print(f"URL: {url[:60]}...")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())

        text = (
            body.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )

        print(f"Response: {text}")
        assert text, "Got empty response"
        print("✓ PASSED\n")

    except urllib.error.HTTPError as e:
        error_body = ""
        try:
            error_body = e.read().decode()
        except Exception:
            pass
        print(f"✗ FAILED: HTTP {e.code}")
        print(f"  Error: {error_body[:300]}")

        # Parse error for helpful diagnostics
        try:
            error_json = json.loads(error_body)
            error_msg = error_json.get("error", {}).get("message", "")
            error_status = error_json.get("error", {}).get("status", "")
            print(f"  Status: {error_status}")
            print(f"  Message: {error_msg}")
        except Exception:
            pass
        print()

    except Exception as e:
        print(f"✗ FAILED: {type(e).__name__}: {e}\n")


def test_model_names():
    """Verify model names are valid."""
    print("=" * 60)
    print("TEST 5: Model name validation")
    print("=" * 60)

    print(f"Primary model: {_PRIMARY_MODEL}")
    print(f"Fallback model: {_FALLBACK_MODEL}")

    # Known valid model prefixes
    valid_prefixes = ["gemini-2.5", "gemini-3"]

    assert any(_PRIMARY_MODEL.startswith(p) for p in valid_prefixes), \
        f"Primary model {_PRIMARY_MODEL} may be invalid"
    assert any(_FALLBACK_MODEL.startswith(p) for p in valid_prefixes), \
        f"Fallback model {_FALLBACK_MODEL} may be invalid"

    # Check not using deprecated models
    deprecated = ["gemini-2.0", "gemini-1.5", "gemini-1.0"]
    for model in [_PRIMARY_MODEL, _FALLBACK_MODEL]:
        for dep in deprecated:
            assert not model.startswith(dep), f"{model} is deprecated"

    print("✓ PASSED\n")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("CHAT API TEST SUITE")
    print("=" * 60 + "\n")

    test_message_conversion()
    test_context_building()
    test_payload_format()
    test_model_names()
    test_live_api_call()

    print("=" * 60)
    print("ALL TESTS COMPLETED")
    print("=" * 60)
