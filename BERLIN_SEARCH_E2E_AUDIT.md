# Berlin Search E2E Audit

Date: 2026-03-07

## Environment

- Frontend: `http://localhost:3000`
- Backend API: `http://127.0.0.1:8000`
- User session was re-authenticated before the audit

## Scenarios checked

1. `/services -> category -> /search?category=...`
2. Auto-search on category deep-link
3. Manual location input via `Berlin`
4. Open slots modal from search results

## Confirmed findings

### 1. Search page sends duplicate requests on category deep-link

On entering `/search?category=grooming`, the frontend sent the same request multiple times:

- `GET /api/v1/booking/search/?pet_id=18&category_id=38`
- repeated 4 times in a row

This confirms a real duplicate-request bug, not just a code smell.

### 2. Location and service search are mixed into one field

When `Berlin` was entered via the location picker and applied:

- the main search input became `Berlin`
- the booking search request became:
  - `GET /api/v1/booking/search/?pet_id=18&q=Berlin&category_id=38`
- the public service autocomplete also fired:
  - `GET /api/v1/public/services/search/?q=Berlin`

This means location text is still treated as service search text.

### 3. Search page transition is visually delayed

After clicking a category on `/services`, the URL switched to `/search?...` first, while the old `/services` UI remained visible for a short time before the search screen appeared.

This creates a broken-feeling navigation transition and needs a loading or route-transition state.

### 4. Slots modal opens, but slot list contains massive duplicates

For the Berlin location:

- slots endpoint was requested successfully:
  - `GET /api/v1/booking/locations/8/slots/?service_id=20&pet_id=18&date_start=2026-03-07&date_end=2026-03-14`
- the modal showed many repeated identical times:
  - dozens of `01:00 PM`
  - dozens of `01:30 PM`
  - dozens of `02:00 PM`
  - dozens of `02:30 PM`
  - dozens of `03:00 PM`

This looks like slot duplication at backend generation level, frontend rendering level, or both.

### 5. No visible search-loading/result-state around transitions

During the route and search transitions:

- the page can show stale content briefly
- there is no explicit list/map loading state
- user feedback is weak during auto-search

## What worked

- Login worked after backend startup
- `/services -> /search?category=grooming` eventually opened the booking search page
- Category-based search returned at least one Berlin location
- Slots modal opened for the found Berlin location

## Priority fixes suggested by audit

1. Stop duplicate auto-search calls on search page boot.
2. Separate `serviceQuery` from `locationQuery`.
3. Prevent `Berlin` from triggering service suggestions.
4. Add explicit loading states for route/search transitions.
5. Fix duplicate slot generation/rendering.
