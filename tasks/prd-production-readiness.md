# PRD: Milwaukee Vehicle Finder - Production Readiness

## 1. Introduction/Overview

The Milwaukee Vehicle Finder is a DOOM-themed vehicle search app that scrapes 4 platforms concurrently and provides AI-powered analysis via Google Gemini. While core search works, a comprehensive 5-agent analysis revealed the app is **54% PRD-compliant** with critical gaps in security, accessibility, reliability, and AI feature orchestration.

This PRD defines the work needed to take the app from MVP to production-ready. It synthesizes findings from:
- **Frontend Analysis**: 4.5/10 (WCAG violations, monolithic architecture, performance issues)
- **Backend Analysis**: B+ (solid async patterns, SSRF vulnerability, DRY violations)
- **DevOps Analysis**: 5/10 (no CI/CD, no tests, unpinned dependencies)
- **Product Gap Analysis**: 54% compliance (AI endpoints built but never triggered)
- **QA Analysis**: 5.2/10 (zero tests, unvalidated inputs crash handlers)

## 2. Goals

- Achieve WCAG AA accessibility compliance (currently 42/100)
- Fix all critical security vulnerabilities (SSRF, input validation, prompt injection)
- Wire up AI features that exist but aren't triggered (market analysis, deal badges, auto-fetch)
- Establish CI/CD with test coverage >50% for backend
- Improve frontend performance (defer Three.js, batch DOM operations)
- Production-ready error handling (no silent failures, no crashes on bad input)

## 3. User Stories

### Phase 1: Critical Security & Stability

#### US-001: Input Validation on Backend
**Description:** As a user, I want the API to handle invalid inputs gracefully so that malformed requests don't crash the server.

**Acceptance Criteria:**
- [ ] All `int()` conversions in search/index.py (lines 397-400) wrapped in try/except
- [ ] All `int()` conversions in review.py (line 214), safety.py (line 168) wrapped
- [ ] Invalid year/price/mileage returns HTTP 400 with descriptive error
- [ ] Negative years rejected; year range validated (1990-2030)
- [ ] Empty make/model accepted but documented as "broad search"
- [ ] Non-numeric ZIP code returns 400

#### US-002: SSRF Protection on Details Endpoint
**Description:** As an operator, I want the details endpoint to only fetch from known automotive sites so that attackers can't use it as a proxy.

**Acceptance Criteria:**
- [ ] URL domain whitelist enforced in details.py (line 282-290): only craigslist.org, cargurus.com, cars.com, autotrader.com
- [ ] Scheme restricted to https:// only
- [ ] Invalid URLs return HTTP 400
- [ ] Internal/private IP ranges blocked

#### US-003: Fix Accessibility Violations
**Description:** As a user with disabilities, I want the app to meet WCAG AA standards so I can use it with assistive technology.

**Acceptance Criteria:**
- [ ] Color contrast updated to 4.5:1 minimum on all interactive elements (lines 15-62, 430, 517-521)
- [ ] `aria-label` added to all icon buttons (sound toggle, theme toggle, close buttons, chat FAB)
- [ ] Modal has `role="dialog"`, `aria-labelledby`, focus trap
- [ ] Form labels have `for` attributes linked to input IDs
- [ ] `prefers-reduced-motion` media query disables animations
- [ ] Verify in browser with axe DevTools

### Phase 2: AI Feature Wiring

#### US-004: Auto-Trigger Market Analysis After Search
**Description:** As a user, I want market intelligence to appear automatically after searching so I can see deal quality without extra clicks.

**Acceptance Criteria:**
- [ ] `fetchMarketSummary()` called automatically after search results load
- [ ] Market panel populates with summary, best_deals, overpriced, recommendations
- [ ] Loading state shown during analysis ("Analyzing market...")
- [ ] Timeout after 30 seconds with error message (not infinite spinner)
- [ ] If analysis fails, panel shows "Analysis unavailable" (not empty)
- [ ] Verify in browser

#### US-005: Auto-Fetch Review & Safety on Modal Open
**Description:** As a user, I want AI reviews and safety data to load automatically when I open a vehicle so I don't have to click tabs manually.

**Acceptance Criteria:**
- [ ] `fetchReview()` and `fetchSafety()` called in `openModal()` (not on tab click)
- [ ] Data populates before user switches to AI Intel tab
- [ ] Loading indicators visible while fetching
- [ ] If either fails, show error in respective section
- [ ] Verify in browser

#### US-006: Background Deal Badge Generation
**Description:** As a user, I want deal quality badges on vehicle cards so I can quickly identify good deals without opening each listing.

**Acceptance Criteria:**
- [ ] After search completes, batch-fetch reviews for top 10 vehicles
- [ ] Fetch in batches of 3 (not all at once) to avoid rate limits
- [ ] Deal badges (great_deal, good_deal, fair, above_market, overpriced) appear on cards
- [ ] Shimmer loading state while badges generate
- [ ] If badge fetch fails for a vehicle, no badge shown (not error)
- [ ] Verify in browser

#### US-007: Dynamic Chat Context & Chips
**Description:** As a user, I want the chat to be context-aware so it knows what I'm searching for and looking at.

**Acceptance Criteria:**
- [ ] Chat chips change based on state: landing ("Reliable SUVs?"), results ("Which is best deal?"), modal ("Is this fair?")
- [ ] Search results summary auto-injected into chat context after search
- [ ] Current vehicle context injected when modal is open
- [ ] "Ask about this car" button added to vehicle modal
- [ ] Verify in browser

#### US-008: Display Research Links
**Description:** As a user, I want to see reference links (Edmunds, KBB, NHTSA, Consumer Reports) in the AI review so I can verify the information.

**Acceptance Criteria:**
- [ ] `sources` array from /api/review response rendered in modal AI tab
- [ ] Links open in new tab
- [ ] Links truncated with tooltip on hover if URL is long
- [ ] Verify in browser

### Phase 3: Reliability & Error Handling

#### US-009: Prevent Duplicate API Requests
**Description:** As a user, I want the app to prevent double-clicks from sending duplicate searches.

**Acceptance Criteria:**
- [ ] Search button disabled during request (already done via `loading` flag)
- [ ] `search()` returns early if `this.loading` is true
- [ ] `sendChat()` returns early if `this.chatTyping` is true
- [ ] `openModal()` prevents re-opening while loading

#### US-010: Add Timeouts to All Frontend API Calls
**Description:** As a user, I want API calls to timeout gracefully instead of hanging forever.

**Acceptance Criteria:**
- [ ] Market analysis has 30-second timeout with AbortController
- [ ] Details fetch has 15-second timeout
- [ ] Review fetch has 20-second timeout
- [ ] Safety fetch has 15-second timeout
- [ ] All timeouts show user-friendly message

#### US-011: Backend Rate Limiting on Search
**Description:** As an operator, I want the search endpoint rate-limited so scrapers aren't overwhelmed.

**Acceptance Criteria:**
- [ ] Rate limit: 10 searches/minute per IP
- [ ] HTTP 429 returned when exceeded with `Retry-After` header
- [ ] Frontend shows rate limit message to user

### Phase 4: DevOps & Testing

#### US-012: Expand .gitignore
**Description:** As a developer, I want a comprehensive .gitignore so sensitive files are never accidentally committed.

**Acceptance Criteria:**
- [ ] .env, .env.local, .env.* patterns added
- [ ] .vscode/, .idea/ added
- [ ] *.pyc, *.pyo, __pycache__/ covered
- [ ] .DS_Store, Thumbs.db added
- [ ] .pytest_cache/, .coverage, htmlcov/ added

#### US-013: Pin Dependencies
**Description:** As a developer, I want all dependencies pinned to specific versions so builds are reproducible.

**Acceptance Criteria:**
- [ ] google-generativeai pinned to exact version (not >=0.8.0)
- [ ] All packages in requirements.txt have exact version pins
- [ ] .env.example created documenting GOOGLE_API_KEY requirement

#### US-014: Add Backend Unit Tests
**Description:** As a developer, I want unit tests for critical backend functions so regressions are caught before deployment.

**Acceptance Criteria:**
- [ ] pytest added to requirements.txt (dev section or separate file)
- [ ] Tests for `_extract_price()`, `_extract_mileage()`, `_extract_year()`, `_year_ok()`
- [ ] Tests for input validation (invalid types, empty strings, edge values)
- [ ] Tests for CORS headers
- [ ] Tests for URL whitelist validation
- [ ] All tests pass

#### US-015: Add CI/CD Pipeline
**Description:** As a developer, I want automated linting and testing on every push so code quality is maintained.

**Acceptance Criteria:**
- [ ] `.github/workflows/ci.yml` created
- [ ] Runs flake8 linting on api/ directory
- [ ] Runs pytest test suite
- [ ] Runs on push and pull request events
- [ ] Pipeline passes on current codebase

### Phase 5: Performance & UX Polish

#### US-016: Defer Three.js Initialization
**Description:** As a mobile user, I want the app to not drain my battery when I'm just reading results.

**Acceptance Criteria:**
- [ ] Three.js renderers only initialized on first weapon fire (not page load)
- [ ] requestAnimationFrame loop starts only when effects active
- [ ] Loop pauses when no active particles
- [ ] No visual regression when weapons fire

#### US-017: Batch DOM Operations for Particle Effects
**Description:** As a user, I want smooth weapon effects without UI jank.

**Acceptance Criteria:**
- [ ] Particle creation uses DocumentFragment for batch appendChild
- [ ] Reduces reflows from 30-42 per weapon fire to 1
- [ ] No visual regression in weapon effects

#### US-018: Add Tablet Breakpoint
**Description:** As a tablet user, I want the layout optimized for my screen size.

**Acceptance Criteria:**
- [ ] New breakpoint at 768px-1024px
- [ ] Vehicle grid: 2 columns on tablet (currently 3 = cramped)
- [ ] Form: 3 columns on tablet
- [ ] HUD text readable (minimum 12px)
- [ ] Verify in browser at iPad dimensions

#### US-019: Fix Mobile HUD Readability
**Description:** As a mobile user, I want to read the HUD stats without squinting.

**Acceptance Criteria:**
- [ ] HUD label minimum font-size 0.7rem (currently 0.55rem = 8.8px)
- [ ] HUD values minimum 1.1rem on mobile
- [ ] Verify in browser at 390px width

#### US-020: Scrollable Modal Content
**Description:** As a user, I want to scroll long vehicle descriptions in the modal without the page scrolling behind it.

**Acceptance Criteria:**
- [ ] Modal body has `max-height: 85vh` and `overflow-y: auto`
- [ ] Background scroll locked when modal open
- [ ] Description expansion doesn't cause layout shift
- [ ] Verify in browser

## 4. Functional Requirements

- FR-1: All API endpoints must validate input types before processing
- FR-2: Details endpoint must whitelist URLs to automotive domains only
- FR-3: All interactive elements must have WCAG AA compliant contrast (4.5:1)
- FR-4: All icon buttons must have aria-label attributes
- FR-5: Market analysis must auto-trigger after search completes
- FR-6: AI review and safety data must auto-fetch on modal open
- FR-7: Deal badges must batch-generate for top 10 results after search
- FR-8: Chat chips must be dynamic based on app state
- FR-9: All frontend API calls must have explicit timeouts
- FR-10: Search endpoint must be rate-limited (10/min/IP)
- FR-11: Three.js must lazy-initialize on first weapon fire
- FR-12: All dependencies must be version-pinned
- FR-13: CI pipeline must run linting and tests on every push

## 5. Non-Goals (Out of Scope)

- Full TypeScript/framework migration (too large for this phase)
- Splitting index.html into separate component files (follow-up work)
- PWA / offline support
- User accounts / authentication
- Saved searches / favorites / comparison features
- Redis/persistent caching (in-memory acceptable for now)
- Switching to official automotive APIs (scraping approach maintained)

## 6. Technical Considerations

- **Vercel Limits**: Functions have 60s max duration (Pro). Search with 4 scrapers at 12s each fits within limits but leaves no margin.
- **Gemini Model Stability**: `gemini-2.5-flash` may be preview. Verify stable model availability and update if needed.
- **Scraper Fragility**: HTML selectors break when target sites change. Tests should verify scraper output structure, not exact values.
- **Single-File Frontend**: 176KB index.html is large but functional. Splitting is out of scope but should be next phase.

## 7. Success Metrics

- Zero unhandled exceptions on invalid API input
- WCAG AA accessibility score >90 (axe DevTools)
- Market analysis panel populated on 100% of searches
- Deal badges visible on cards within 15 seconds of search
- CI pipeline green on all pushes
- Backend test coverage >50%
- No SSRF possible via details endpoint

## 8. Open Questions

1. Should `gemini-2.5-flash` be replaced with `gemini-2.0-flash` as primary model for stability?
2. Should empty make/model searches be blocked or allowed as "browse all" functionality?
3. What is the acceptable latency for deal badge generation (currently unbounded)?
4. Should rate limiting use persistent storage (Redis) or is in-memory acceptable for current scale?
