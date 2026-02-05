# PRD: AI Functionality Testing & Enhancement

## 1. Overview

The Milwaukee Vehicle Finder uses Google Gemini across 3 AI endpoints (review, analyze, chat) plus NHTSA safety data. While the plumbing works, the AI output quality, accuracy, and user experience have not been validated end-to-end. This PRD defines work to test AI features with real searches and improve the intelligence layer that drives deal badges, market analysis, and vehicle advice.

## 2. Current AI Architecture

| Endpoint | Purpose | Model | Cache | Rate Limit |
|----------|---------|-------|-------|------------|
| POST `/api/review` | Vehicle review + price verdict + owner sentiment | gemini-2.5-flash (fallback: 2.0-flash) | In-memory + localStorage | None (Gemini quota) |
| POST `/api/analyze` | Market analysis, best deals, red flags | gemini-2.5-flash (fallback: 2.0-flash) | In-memory, 10-min TTL | 20/min/IP |
| POST `/api/chat` | Conversational advisor with vehicle/search context | gemini-2.5-flash (fallback: 2.0-flash) | Session only | 30/min/IP |
| GET `/api/safety` | NHTSA safety ratings + recalls + complaints | No AI (NHTSA API) | In-memory + localStorage | None |

### How AI Integrates with Search Results

1. User submits search (make, model, year range, price, mileage)
2. `/api/search` scrapes 4 platforms, returns up to 80 vehicles
3. Frontend auto-triggers two AI calls in parallel:
   - `fetchMarketSummary()` → POST `/api/analyze` with top 20 vehicles → displays market intel panel
   - `fetchDealBadges()` → POST `/api/review` for top 10 cheapest vehicles (batched 3 at a time, 1s delay) → maps `price_verdict` to badge on each card
4. When user clicks a vehicle card:
   - `fetchReview()` → POST `/api/review` → populates AI Intel tab with full review
   - `fetchSafety()` → GET `/api/safety` → populates safety ratings, recalls, complaints
5. Chat context auto-injects current vehicle + search summary into every message

## 3. Problems to Solve

### P1: AI Output Quality is Unverified
- No one has validated whether Gemini returns accurate pricing assessments
- `price_verdict` (great_deal, good_deal, fair, above_market, overpriced) may be unreliable for Milwaukee market
- Owner sentiment and recall info may be hallucinated
- Research source URLs are generated statically (not validated as live links)

### P2: Deal Badges Are Slow
- Top 10 badges require 10 individual `/api/review` calls (batched 3 at a time)
- At ~3-5s per Gemini call, full badge generation takes 12-20 seconds
- Users see empty badge slots during this period

### P3: Market Analysis Doesn't Reference Actual Prices
- The analyze prompt sends vehicle listings to Gemini, but Gemini's "fair_price_range" may not align with actual scraped data
- `avg_market_price` from Gemini may differ from the computed `stats.avg_price` from scraping
- No validation that "best_deals" and "overpriced" labels reference real listings

### P4: Chat Context Could Be Richer
- Only top 5 vehicles sent as context (could send more metadata)
- No price history or trend context (expected given no DB, but could reference scraped averages)
- Chat doesn't know about user's favorites or saved searches

### P5: Safety Data May Be Stale or Missing
- NHTSA API returns data for make/model/year but some years have no data
- No fallback when NHTSA returns empty results
- Recall data shown without indicating whether recalls are open vs. completed

### P6: No Structured Testing of AI Responses
- Zero tests validate AI response structure
- No tests verify JSON schema compliance from Gemini
- No tests verify fallback behavior when primary model fails

## 4. User Stories

### Phase A: AI Response Validation & Testing

#### US-A1: Validate Review Response Schema
**Description:** Ensure `/api/review` returns all expected fields with correct types, regardless of vehicle input.

**Acceptance Criteria:**
- [ ] Test with 5+ different make/model/year combinations
- [ ] Verify all 13 JSON fields present: summary, pros, cons, reliability_rating, reliability_summary, owner_sentiment, fair_price_assessment, price_verdict, known_issues, recall_info, insurance_estimate, cost_to_own_notes, platform_notes
- [ ] `reliability_rating` is 1-5 integer
- [ ] `price_verdict` is one of: great_deal, good_deal, fair, above_market, overpriced
- [ ] `pros` and `cons` are non-empty arrays of strings
- [ ] `known_issues` is an array
- [ ] Test with edge cases: very old car (2000), very new car (2025), unknown make, missing fields

#### US-A2: Validate Market Analysis Response Schema
**Description:** Ensure `/api/analyze` returns structurally valid analysis that references actual vehicle listings.

**Acceptance Criteria:**
- [ ] `best_deals` titles match actual vehicle titles from input
- [ ] `overpriced` titles match actual vehicle titles from input
- [ ] `avg_market_price` is within reasonable range of computed average from input data
- [ ] `fair_price_range` parses to two numeric values
- [ ] `red_flags` is an array (may be empty)
- [ ] Test with varying input sizes: 3 vehicles, 10 vehicles, 20 vehicles

#### US-A3: Validate Chat Context Injection
**Description:** Verify chat responses use provided vehicle context and search results, not generic advice.

**Acceptance Criteria:**
- [ ] When vehicle context provided, chat mentions specific price/mileage/year from context
- [ ] When search summary provided, chat references average price and total count
- [ ] Response is concise (under 4 paragraphs per system prompt rules)
- [ ] Chat handles follow-up questions with maintained history
- [ ] Chat handles missing context gracefully (no vehicle selected)

#### US-A4: Test Model Fallback Behavior
**Description:** Verify that when primary Gemini model fails, fallback model is used seamlessly.

**Acceptance Criteria:**
- [ ] Unit test: mock primary model exception, verify fallback called
- [ ] Unit test: mock both models failing, verify 502/500 returned with error details
- [ ] Verify user sees no indication of which model was used (transparent fallback)
- [ ] Test JSON parsing fallback (markdown-fenced response, bare JSON, malformed)

#### US-A5: Test Safety Data Completeness
**Description:** Verify NHTSA safety endpoint handles all vehicle types and missing data gracefully.

**Acceptance Criteria:**
- [ ] Test with vehicle that has full NHTSA data (e.g., 2020 Toyota Camry)
- [ ] Test with vehicle that has no NHTSA data (e.g., rare/imported model)
- [ ] Test with very old vehicle (pre-2000)
- [ ] Empty results show "No safety data available" (not error)
- [ ] Recall data distinguishes open vs. completed recalls if NHTSA provides that info

### Phase B: AI Quality Improvements

#### US-B1: Add Price Validation to Deal Badges
**Description:** Cross-check Gemini's `price_verdict` against actual scraped price statistics before displaying badge.

**Acceptance Criteria:**
- [ ] Compare vehicle price to search `stats.avg_price`
- [ ] If vehicle price < 80% of avg → bias toward "great_deal"/"good_deal"
- [ ] If vehicle price > 120% of avg → bias toward "above_market"/"overpriced"
- [ ] If Gemini verdict conflicts with math by >1 tier, use computed tier instead
- [ ] Badge tooltip shows both AI assessment and price-vs-average comparison

#### US-B2: Batch Deal Badge Generation via Single Analyze Call
**Description:** Instead of 10 individual review calls for badges, extend the analyze endpoint to return per-vehicle verdicts.

**Acceptance Criteria:**
- [ ] Add `per_vehicle_verdicts` field to analyze prompt requesting price_verdict for each input vehicle
- [ ] Single API call replaces 10 individual calls
- [ ] Badge generation time reduced from 12-20s to 3-5s
- [ ] Fallback to individual review calls if analyze doesn't return verdicts
- [ ] Deal badges still display correctly on cards

#### US-B3: Validate and Fix Research Source URLs
**Description:** Ensure source URLs in review response actually resolve to valid pages.

**Acceptance Criteria:**
- [ ] Source URLs are constructed from actual site URL patterns (not hallucinated)
- [ ] URLs use correct make/model/year in path segments
- [ ] Links that return 404 are filtered out before display
- [ ] Add year-specific NHTSA recall link: `https://www.nhtsa.gov/vehicle/{year}/{make}/{model}`
- [ ] Add year-specific Edmunds link: `https://www.edmunds.com/{make}/{model}/{year}/review/`

#### US-B4: Enrich Chat Context with Favorites and Comparison
**Description:** Include user's favorited vehicles and saved searches in chat context so AI can provide comparative advice.

**Acceptance Criteria:**
- [ ] Chat context includes `favorites` array (from localStorage) when available
- [ ] Chat context includes `saved_searches` when available
- [ ] Chat can answer "How does this compare to my favorites?"
- [ ] Chat can answer "Which of my saved searches has the best options?"
- [ ] Context size stays under Gemini token limits (truncate if needed)

#### US-B5: Add Confidence Indicators to AI Responses
**Description:** Show users how confident the AI assessment is, based on data availability.

**Acceptance Criteria:**
- [ ] Market analysis shows "Based on N listings" count
- [ ] Review shows data freshness indicator (cached vs. fresh)
- [ ] Price verdict shows comparison methodology (AI estimate vs. scraped average)
- [ ] Disclaimer text added: "AI assessments are estimates. Verify pricing on KBB.com"

### Phase C: Performance & Reliability

#### US-C1: Reduce Gemini Cold Start Impact
**Description:** Handle Gemini cold starts gracefully with progressive loading states.

**Acceptance Criteria:**
- [ ] Market panel shows "Analyzing N vehicles..." with count
- [ ] Deal badges show shimmer/skeleton while loading (not empty space)
- [ ] Review tab shows section-by-section loading (summary first, then details)
- [ ] If first Gemini call takes >5s, show "AI is warming up..." message
- [ ] Subsequent calls in same session should be faster (warm instance)

#### US-C2: Add Retry Logic for Transient Gemini Failures
**Description:** Retry failed Gemini calls once before showing error to user.

**Acceptance Criteria:**
- [ ] On Gemini 500/503, retry once after 2-second delay
- [ ] On timeout, retry once with extended timeout (+10s)
- [ ] Max 2 attempts total (1 retry)
- [ ] User sees "Retrying..." state during retry
- [ ] If retry also fails, show final error message
- [ ] Track retry success rate in response metadata

#### US-C3: Implement Response Streaming for Chat
**Description:** Stream chat responses for better perceived performance instead of waiting for full response.

**Acceptance Criteria:**
- [ ] Use Gemini streaming API (`generate_content` with `stream=True`)
- [ ] Frontend receives chunks via Server-Sent Events or chunked response
- [ ] Text appears progressively (current typewriter effect kept but fed from stream)
- [ ] Reduces perceived latency from 3-5s (full response) to <500ms (first token)
- [ ] Fallback to non-streaming if SSE not supported

## 5. Task Breakdown

| ID | Title | Phase | Priority | Effort |
|----|-------|-------|----------|--------|
| AI-001 | Write review response schema validation tests | A | 1 | Small |
| AI-002 | Write market analysis validation tests | A | 2 | Small |
| AI-003 | Write chat context injection tests | A | 3 | Small |
| AI-004 | Write model fallback + JSON parsing tests | A | 4 | Small |
| AI-005 | Write safety data completeness tests | A | 5 | Small |
| AI-006 | Add price math validation to deal badges | B | 6 | Medium |
| AI-007 | Batch badge generation via single analyze call | B | 7 | Medium |
| AI-008 | Fix research source URL construction | B | 8 | Small |
| AI-009 | Enrich chat context with favorites/searches | B | 9 | Small |
| AI-010 | Add confidence indicators to AI responses | B | 10 | Small |
| AI-011 | Progressive loading states for AI features | C | 11 | Medium |
| AI-012 | Add retry logic for Gemini failures | C | 12 | Medium |
| AI-013 | Implement streaming for chat responses | C | 13 | Large |

## 6. Success Metrics

- All AI response schema tests pass (AI-001 through AI-005)
- Deal badge accuracy: computed price tier matches Gemini verdict within 1 tier on >80% of vehicles
- Badge generation time reduced from 12-20s to <5s (via batch approach)
- Chat responses reference actual vehicle data from context on >90% of queries
- Zero unhandled Gemini errors visible to user (all caught, retried, or shown gracefully)
- Research source URLs resolve to valid pages on >90% of links

## 7. Non-Goals

- Replacing Gemini with another AI provider
- Adding persistent storage for AI responses (beyond localStorage)
- Fine-tuning or training custom models
- Real-time price tracking or historical price data
- Integrating additional data sources (Carfax, AutoCheck)

## 8. Dependencies

- `GOOGLE_API_KEY` must be set in Vercel for any AI testing against live Gemini
- NHTSA API must be accessible (public, no key required)
- Tests in Phase A can mock Gemini responses for schema validation
- Tests in Phase B require live Gemini calls or recorded fixtures
