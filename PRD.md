# Milwaukee Vehicle Finder - Product Requirements Document

## Current State Assessment

### What Exists Today

**Working features:**
- Vehicle search across 4 platforms (Craigslist, CarGurus, Cars.com, AutoTrader) via concurrent web scraping
- Vehicle detail modal with image gallery, specs, and description (fetched from `/api/details`)
- Doom-themed UI with Three.js 3D effects, sound effects, animations, achievement system
- Source filtering (All / Craigslist / CarGurus / etc.) and sorting (price, mileage, year)
- Responsive single-page Alpine.js frontend, Python serverless backend on Vercel

**AI features that exist but are broken or incomplete:**

| Feature | Status | Issue |
|---------|--------|-------|
| AI Chat Drawer (`/api/chat`) | UI renders, backend exists | **Not functional.** Gemini model ID `gemini-2.5-flash-preview-05-20` may be expired/invalid. No error feedback shown to user when API fails. No fallback. Chat drawer has no welcome message - user sees empty panel with no guidance. |
| AI Vehicle Review (`/api/review`) | UI renders in modal tab, backend exists | **Partially functional.** Same Gemini model issue. Frontend reads `data.review` correctly. Triggered only on manual tab click. No auto-fetch. |
| NHTSA Safety Data (`/api/safety`) | UI renders in modal tab, backend exists | **Likely functional** - uses free NHTSA gov API (no key needed). But only triggered on manual tab click. Safety star rating reads `currentSafety.safety.overall_rating` which matches the API response structure. |
| AI "Reviewed" badge on cards | Not implemented | The feature branch had this but it was not carried over. `hasReviewCache()` method is missing. |

### Architecture (Current)

```
Frontend (index.html)
  |
  |-- POST /api/search         --> Scrapes 4 platforms concurrently
  |-- GET  /api/details?url=   --> Fetches listing details/images
  |-- POST /api/chat           --> Gemini AI chat (broken)
  |-- POST /api/review         --> Gemini AI vehicle review (broken)
  |-- GET  /api/safety          --> NHTSA safety data (works)
```

All AI features use Google Gemini via the `google-generativeai` Python SDK. The `GOOGLE_API_KEY` environment variable is configured in Vercel secrets.

---

## Requirements: Enhanced AI Integration

### 1. Fix the AI Chat Assistant (P0 - Critical)

**Problem:** The chat button appears but nothing happens when users interact with it. The Gemini model ID may be outdated, there's no error handling visible to the user, and the empty chat panel provides no onboarding.

**Requirements:**

1.1. **Update Gemini model to a stable version.** Replace `gemini-2.5-flash-preview-05-20` with the current stable model (e.g., `gemini-2.0-flash` or whatever is current). Apply this change across all three AI endpoints (`chat.py`, `review.py`, `safety.py` - note: safety.py doesn't use Gemini).

1.2. **Add a welcome message.** When the chat drawer opens, display an initial AI message:
> "I'm your Vehicle Intelligence AI. I can analyze deals, check reliability, estimate costs, and research any vehicle you're looking at. Select a vehicle or ask me anything about cars in the Milwaukee area."

1.3. **Show error states clearly.** When the API returns an error (missing API key, rate limit, Gemini failure), display the error in the chat as a styled error message - not a silent failure.

1.4. **Add loading/connection indicator.** Show a brief "Connecting..." state when the chat first sends a message, so users know the system is attempting to respond.

1.5. **Chat should persist across modal opens/closes.** Currently `chatHistory` and `chatMessages` survive modal interactions (they're not reset in `closeModal`), but the chat should also show a contextual message when the user selects a new vehicle: "Now viewing: 2019 Honda Civic - $15,500 | 45,000 mi".

---

### 2. Automatic AI Analysis on Search (P0 - Critical)

**Problem:** The AI only activates when a user manually clicks the "AI Intel" tab inside a modal. The user wants the AI to proactively analyze search results.

**Requirements:**

2.1. **Post-search AI summary.** After search results load, automatically call a new endpoint (`/api/analyze`) or reuse `/api/chat` with a structured prompt that includes:
- The full list of vehicles found (make, model, year, price, mileage, source)
- Ask the AI to identify: best deals, overpriced listings, red flags, market trends
- Display the AI summary in a collapsible panel above the vehicle grid

2.2. **Per-vehicle AI badges.** After search completes, run background AI analysis on the top ~10 results to generate quick verdict badges shown directly on vehicle cards:
- "Great Deal" / "Good Deal" / "Fair" / "Above Market" / "Overpriced"
- These should load progressively (show a shimmer/skeleton while loading)
- Cache results in `reviewCache` so the modal "AI Intel" tab loads instantly

2.3. **AI research scope per vehicle.** When AI reviews a vehicle (either via background analysis or modal tab click), the prompt should instruct Gemini to research and comment on:
- Common problems and reliability issues for that specific make/model/year
- What real owners say about the vehicle (Consumer Reports, Reddit, forums sentiment)
- Estimated true cost of ownership (maintenance, insurance, fuel)
- Whether the listed price is fair vs. KBB/Edmunds market data
- Any active recalls (cross-reference with NHTSA data if available)
- Dealership/seller reputation notes (if source is CarGurus or Cars.com where dealer info is available)

2.4. **Batched API calls.** To avoid hitting Gemini rate limits, batch vehicle analyses:
- Analyze vehicles in groups of 3-5 with a slight delay between batches
- Prioritize the cheapest/best-value vehicles first
- Show a progress indicator: "AI analyzing 1 of 10..."

---

### 3. AI Chat Present on All Views (P1 - High)

**Problem:** The chat FAB and drawer exist globally on the page, but the AI has no awareness of what the user is doing unless they've opened a specific vehicle modal. The app is a single-page app so there are no separate "pages" - but there are distinct states: landing/search form, search results, and vehicle detail modal.

**Requirements:**

3.1. **Context-aware chat.** The chat should automatically know the user's current state and adjust its context:
- **Search form state:** AI can help pick vehicles ("What's a reliable SUV under $15k?"), explain search parameters, suggest makes/models
- **Results state:** AI knows the full result set, can compare vehicles, identify best deals, answer "which of these has the best reliability?"
- **Modal state:** AI knows the specific vehicle being viewed, its details, price relative to others in the search

3.2. **Dynamic quick-action chips.** The preset chips ("Is this a good deal?", "Known issues?", etc.) should change based on context:
- **No search yet:** "Reliable SUVs under $20k?", "Best value sedans?", "What should I look for?"
- **Viewing results:** "Which is the best deal?", "Compare top 3", "Any red flags?", "Sort by reliability"
- **Viewing a vehicle:** "Is this a good deal?", "Known issues?", "Reliability?", "Negotiate tips"

3.3. **Auto-populate context on search.** When a search completes, automatically update the chat's context with the full search summary so subsequent questions reference real data.

---

### 4. Enhanced Vehicle Detail AI Experience (P1 - High)

**Problem:** The AI Intel and Safety tabs in the modal are passive - they only load on click and have no connection to each other.

**Requirements:**

4.1. **Auto-fetch AI review on modal open.** When a user opens a vehicle modal, automatically start fetching the AI review and NHTSA safety data in the background (don't wait for tab click). The data should be ready by the time the user clicks the tab.

4.2. **Combined intelligence view.** The AI review should incorporate NHTSA data when available:
- If there are active recalls, mention them in the AI summary
- If the safety rating is low, factor that into the price verdict
- Show a single "Intelligence Report" that combines AI analysis + hard safety data

4.3. **Research links.** After the AI review loads, show clickable reference links:
- Edmunds review for that make/model/year
- KBB fair market value
- Consumer Reports (if available)
- CarComplaints.com for known issues
- NHTSA recall lookup

These links already exist in the `_build_sources()` function in `review.py` but are not displayed in the frontend.

4.4. **"Ask about this car" shortcut.** Add a button in the modal that opens the chat drawer with the vehicle pre-loaded as context and sends an automatic first message like "Tell me everything I should know about this [year] [make] [model]."

---

### 5. Error Handling and Resilience (P1 - High)

**Requirements:**

5.1. **Gemini model fallback chain.** If the primary model fails, try a fallback:
- Primary: `gemini-2.0-flash` (or current stable)
- Fallback: `gemini-1.5-flash`
- If both fail, show a meaningful error message

5.2. **Missing API key handling.** If `GOOGLE_API_KEY` is not set:
- Chat drawer should show a banner: "AI features require configuration. The NHTSA safety data is still available."
- Safety tab should still work (it doesn't use Gemini)
- Review tab should show a clear message instead of a silent failure

5.3. **Rate limit feedback.** The chat endpoint has rate limiting (30/min). When hit:
- Show "Rate limit reached. Please wait a moment." in the chat
- Disable the send button temporarily with a countdown

5.4. **Timeout handling.** If Gemini takes >10 seconds:
- Show "This is taking longer than usual..."
- After 20 seconds, show "AI service is slow. Try again later." and allow retry

---

### 6. Search-Time AI Insights (P2 - Medium)

**Requirements:**

6.1. **Market insights panel.** After search results load, show an AI-generated panel:
```
+--------------------------------------------------+
|  AI MARKET INTEL - Honda Civic (2018-2024)       |
|  Milwaukee Area                                   |
|                                                   |
|  Average asking price: $17,450                    |
|  Fair market range: $14,000 - $19,500             |
|  Best deal found: 2019 Civic LX - $12,900 (CL)   |
|  Vehicles below market: 4 of 12                   |
|                                                   |
|  Key insight: 2019-2020 Civic models have the     |
|  best value-to-reliability ratio. Avoid 2016      |
|  models with turbo engine oil dilution issues.    |
+--------------------------------------------------+
```

6.2. **Vehicle card annotations.** On each vehicle card, show small AI-generated tags:
- Price verdict badge (color-coded)
- Reliability indicator (1-5 dots or mini bar)
- Warning icon if the make/model/year has known recall issues

---

### 7. Dealership/Seller Intelligence (P2 - Medium)

**Requirements:**

7.1. **Seller context in AI prompts.** When a vehicle is from a dealership platform (CarGurus, Cars.com, AutoTrader), include the seller/dealer info in the AI prompt so Gemini can comment on dealer reputation.

7.2. **Source quality notes.** The AI should note differences between sources:
- Craigslist = private sellers, potentially lower prices but more risk
- CarGurus/Cars.com/AutoTrader = usually dealerships, may have dealer fees not shown in price
- Mention this context in deal assessments

---

## Technical Implementation Notes

### Gemini Model Selection
The current code uses `gemini-2.5-flash-preview-05-20` which is a preview model and may have been deprecated. Update to the latest stable flash model. Check the Google AI docs for the current model ID.

### Environment Variables
| Variable | Required | Used By |
|----------|----------|---------|
| `GOOGLE_API_KEY` | Yes (for AI features) | `api/chat.py`, `api/review.py` |

### New/Modified API Endpoints

| Endpoint | Method | Description | Status |
|----------|--------|-------------|--------|
| `/api/search` | POST | Vehicle search | Existing - no changes |
| `/api/details` | GET | Listing details | Existing - no changes |
| `/api/chat` | POST | AI chat | Existing - needs model fix |
| `/api/review` | POST | AI vehicle review | Existing - needs model fix + enhanced prompt |
| `/api/safety` | GET | NHTSA data | Existing - works |
| `/api/analyze` | POST | Batch search analysis | **New** - AI summary of full search results |

### Rate Limiting Considerations
- Gemini Flash has generous rate limits but the app makes multiple calls per search
- Background analysis of 10 vehicles = 10 API calls
- Search summary = 1 API call
- Chat messages = 1 call each
- Consider implementing a queue or debouncing strategy

### Caching Strategy
- Vehicle reviews: Cache by `make_model_year` (already implemented server-side in `_review_cache`)
- Safety data: Cache by `make_model_year` (already implemented in `_cache`)
- Search analysis: Cache by search params hash
- Chat: No caching (conversational)
- Frontend: `reviewCache` and `safetyCache` objects already exist in Alpine.js state

---

## Priority Summary

| Priority | Feature | Impact |
|----------|---------|--------|
| P0 | Fix AI chat (model ID, error handling, welcome message) | Unblocks all AI features |
| P0 | Automatic AI analysis on search | Core value proposition |
| P1 | Context-aware chat with dynamic chips | Makes chat actually useful |
| P1 | Auto-fetch AI review on modal open | Removes friction |
| P1 | Error handling and resilience | Production readiness |
| P2 | Market insights panel | Enhanced search experience |
| P2 | Vehicle card annotations | At-a-glance value |
| P2 | Dealership/seller intelligence | Trust and transparency |
