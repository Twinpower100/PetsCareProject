# Prompt: Redesign Booking Escort Logic, Travel-Time Validation, and Real Slot Availability

**Role:** Senior Django Backend Developer  
**Project:** PetsCare backend (`PetsCare-backend`)  
**Goal:** Redesign the booking domain so that booking availability is calculated not only from provider-side capacity, but also from the real-world feasibility for the pet and its escorting owner.

You must work inside the existing Django/DRF codebase and refactor the current booking flow to support escort assignment, travel-time-aware conflict detection, and truly bookable slot generation.

This is a backend-only task description. Do not implement frontend UX here, but backend APIs and domain rules must support the required UX.

---

## 1. Business Context

Current implementation mostly validates booking conflicts only at employee/provider level. That is not sufficient.

The system must also enforce:

1. A pet cannot physically attend overlapping or logistically impossible bookings.
2. A pet must always have an escorting owner.
3. One escorting owner may accompany multiple pets at the same time to the same location (only!)by default.
4. Travel time between locations must be considered when validating whether sequential bookings are feasible.
5. Search results filtered by date must include only actually bookable locations.

There are already pet co-owners in the system. This must be used in the booking domain.

---

## 2. Mandatory Rules

### 2.1 Escort owner

Add explicit booking responsibility for the escorting person.

- Every booking must have `escort_owner`.
- By default, `escort_owner` must be the user who creates the booking.
- This is not optional for any service. All services require an escort.
- Keep `booked_by` semantics clear. If current code uses `Booking.user` as creator, preserve backward compatibility, but introduce explicit escort semantics in the model/domain.

### 2.2 Multi-owner / multi-pet behavior

When a user creates a booking for a pet, and that booking does **not** intersect with already existing bookings in a way that requires escort disambiguation, default the escort to the creator without extra logic.

When a user creates a booking for the **n-th pet**, and that candidate booking intersects with already existing booking(s), backend logic must support explicit escort assignment per booking.

Important clarification:

- The explicit "who escorts which pet" question is needed only when the newly created booking overlaps with existing booking(s).
- This is especially relevant when pets have co-owners and there is ambiguity in physical accompaniment.
- Backend must provide enough validation and API structure so frontend can request/submit explicit escort assignment when needed.

### 2.3 Same owner escorting multiple pets simultaneously

Default policy: **allow it**.

That means:

- One escort owner may accompany more than one pet at the same time by default but only to the same (!)location.
- This is allowed at least for overlapping bookings in the same time range and the same location.
- The backend must not reject such overlaps solely because the same escort owner is reused. This valid only for the same location.

However:

- This must still remain a configurable business policy in architecture, not hardcoded in a way that blocks future tightening.
- Design the logic so this rule can be changed later by configuration or policy layer.

### 2.4 Pet conflict rule

A single pet must never have:

- overlapping bookings;
- or sequential bookings that are impossible due to travel time between locations.

This rule applies across all providers and all locations.

### 2.5 Occupied duration model

Do **not** separately add technical break during booking validation.

Business decision:

- providers must enter procedure duration already including their technical/internal turnaround time;
- therefore booking availability and conflict logic must use one occupied duration only.

Implications:

- do not double-count `tech_break_minutes`;
- if legacy fields remain in schema, they must not inflate occupied time in booking search, slot generation, or conflict validation.


### 2.6 Travel time

Travel time between two booking locations must be calculated using a routing API.

Rules:

- no straight-line distance logic;
- no geodesic fallback;
- no heuristic fallback;
- no local approximation fallback.

Allowed:

- routing API may return averaged travel time if that is the agreed integration mode.

Not allowed:

- any fallback that silently replaces routing API with coordinate math.

If routing data is unavailable, the system must fail explicitly according to agreed product behavior, not degrade into approximate calculations.

Also: it's needed to have some additional time added to the travel time to account for possible traffic and other factors. It would be better to have some configurable parameter for this. This parameter should be given en percentage of the travel time (5% by default). 

### 2.7 Search result filtering by date

For search results filtered by date/time intent, return **only truly bookable locations**.

Do not use the current permissive fallback behavior where locations are still shown even if no real slots exist for the selected date.

If date filtering is requested:

- include only locations with at least one real available slot for the selected pet/service/date context.

---

## 3. Required Backend Changes

### 3.1 Domain model changes

Review the current booking-related models and add the minimum clean domain changes required.

Expected direction:

1. Extend `Booking` with explicit escort semantics.
2. Preserve compatibility where possible with existing `Booking.user`.
3. Make it impossible to create a booking without escort information.
4. Ensure the booking stores enough immutable scheduling data so historical bookings are interpreted correctly even if service setup changes later.

Important:

- Do not rely only on current live service configuration when validating historical bookings.
- Persist the occupied duration snapshot used at booking time.
- The system must not reinterpret old bookings differently after a provider edits service duration later.

Suggested persisted fields:

- `escort_owner`
- `occupied_duration_minutes` or equivalent immutable snapshot
- optional travel-related metadata if needed for audit/debugging

You may choose exact field names, but the domain intent must be clear.

### 3.2 Centralize booking availability logic

There are currently multiple competing availability implementations in the codebase.

Refactor to a single source of truth for:

- slot generation;
- booking conflict validation;
- final booking creation checks.

Do not leave separate simplified logic in public booking-flow endpoints.

Target architecture:

- one booking availability service;
- one booking creation service;
- API views call those services only.

### 3.3 Real slot generation

Refactor slot generation so it uses actual domain rules.

A slot is available only if all of the following are true:

1. The location offers the service for that pet type/size.
2. The employee is allowed to perform that service in that location.
3. The employee has a working schedule in that location at that time.
4. The location itself is open at that time.
5. The slot does not conflict with employee bookings.
6. The slot does not produce a pet-level conflict.
7. The slot remains feasible with routing-based travel time from neighboring bookings of the same pet.

Notes:

- Treat service duration as full occupied duration.
- Do not add a separate tech break on top.
- If slot stepping/granularity exists, make it explicit and configurable if needed, but keep it independent from the removed tech-break double counting.

### 3.4 Booking creation validation

At booking creation time, validate at least:

1. Pet belongs to requester or requester has legal access through ownership/co-ownership.
2. `escort_owner` is one of the pet owners.
3. Employee is valid for this service in this location.
4. Employee schedule is valid for this location and time.
5. The pet has no overlapping booking.
6. The pet has no routing-impossible neighboring booking before or after.
7. The final slot is still free under transactional protection.
8. The escort owner has no overlapping booking.

Use proper transaction boundaries and row locking where needed. Use @transaction_atomic decorator for booking creation. 

### 3.5 Overlap + travel feasibility algorithm

For pet-level feasibility, validate not only time overlap but also routing feasibility between adjacent bookings.

For a candidate booking:

- find previous active/pending booking of the same pet;
- find next active/pending booking of the same pet;
- if previous exists, route from previous location to candidate location and verify arrival feasibility;
- if next exists, route from candidate location to next location and verify onward feasibility.

Use:

- previous booking end + travel time + optional explicit safety buffer if product decides to keep one;
- candidate booking end + travel time + optional explicit safety buffer.

Because product clarified only duration+travel is mandatory, any extra safety buffer must be a named business parameter, not a hidden assumption.

### 3.6 Escort ambiguity support

Backend must support the frontend flow where escort assignment is requested only when a new booking overlaps with existing booking(s).

Implement one of these acceptable patterns:

1. pre-validation endpoint that returns `requires_escort_assignment=true` and candidate conflicting bookings;
2. booking draft validation service reused by the create endpoint;
3. create endpoint that returns a structured validation error telling frontend escort assignment is required.

The backend must make this deterministic and explainable.

### 3.7 Date-filtered search

Update the provider/location search endpoint so that when date filtering is used, only locations with real availability are returned.

This must not be a rough "has schedule on this weekday" check.

It must be based on real slot generation for the selected:

- pet
- service or service query/category context
- date
- location/provider

Performance matters, so optimize query flow and cache routing responses if appropriate, but do not weaken correctness.

---

## 4. Routing Integration Requirements

Introduce or refactor a dedicated routing integration service.

Requirements:

- use routing API only;
- input: source location coordinates + destination location coordinates + mode/parameters if needed;
- output: travel duration in minutes/seconds;
- support repeated calls efficiently;
- allow averaged routing mode if that is the agreed business mode;
- expose explicit errors when routing data is unavailable.

You must not use existing coordinate-distance helpers as a fallback for scheduling decisions.

---

## 5. API Expectations

Review existing booking flow endpoints and redesign them as needed.

At minimum, backend must support:

1. Searching bookable locations.
2. Getting real available slots for a location.
3. Validating escort assignment requirements when needed.
4. Creating a booking with explicit or default escort owner.

Suggested payload direction:

- create booking request should accept optional `escort_owner_id`;
- if omitted, backend defaults it to current user;
- if escort disambiguation is required and omitted, return structured validation response.

Do not keep silent hidden defaults that make overlapping multi-pet scenarios ambiguous.

---

## 6. Performance and Integrity

This work changes core booking correctness. Prioritize integrity over convenience.

Requirements:

- transactional booking creation;
- race-condition protection;
- no duplicate slot acceptance;
- no inconsistent rules between search, slots, and create;
- query optimization for repeated slot checks;
- routing call optimization/caching where safe.

---

## 7. Tests You Must Add

Add and run automated backend tests for at least the following cases:

1. Booking defaults `escort_owner` to creator.
2. Booking is rejected if `escort_owner` is not an owner/co-owner of the pet.
3. Same pet cannot be double-booked at overlapping times.
4. Same pet cannot be booked in routing-impossible consecutive bookings across two locations.
5. Same escort owner can accompany multiple pets simultaneously by default.
6. Slot generation excludes employees who do not provide the service in the location.
7. Slot generation excludes non-working schedule windows.
8. Date-filtered search returns only locations with real slots.
9. Booking creation endpoint and slot endpoint use the same availability rules.
10. Historical bookings continue to use stored occupied duration snapshot after provider edits live service duration.

For testing purposes, you can use the following data:
[credentials.md](credentials.md)
---

## 8. Implementation Guidance

Relevant existing areas to inspect first:

- `PetsCare/booking/models.py`
- `PetsCare/booking/services.py`
- `PetsCare/booking/flow_views.py`
- `PetsCare/booking/api_views.py`
- `PetsCare/pets/models.py`
- `PetsCare/providers/models.py`
- `PetsCare/geolocation/models.py`
- any current location/routing/geolocation service modules

Pay special attention to the fact that the current codebase appears to contain duplicate booking-availability logic. Consolidation is part of the task, it's an obligation, not an optional cleanup.

---

## 9. Expected Outcome

After implementation:

- every booking has a clear escort owner;
- pet-level physical feasibility is enforced;
- travel time is part of booking validation;
- real slot availability is consistent across search, slot list, and final create;
- date-filtered search returns only truly bookable locations;
- no approximation fallback is used instead of routing API.

## 10. Expected style
You can use C:\Users\andre\OneDrive\Documents\Projects\PetCare\PetsCare-backend\.cursorrules as a reference for style and best practices.

## 11. Additional notes
Now the Booking table in DB is empty so you don't need to take care about the data in it.


