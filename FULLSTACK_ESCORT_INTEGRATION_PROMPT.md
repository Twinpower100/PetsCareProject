# Prompt: Implement Escort Disambiguation UI and API adjustments for Pet Bookings

**Role:** Senior Fullstack Developer (React/TS + Django/DRF)
**Project Subsystems:** `Petscare-web` (React SPA) and `PetsCare-backend` (Django API)
**Context:** We recently shipped a major backend refactoring to enforce logistical feasibility for bookings (`BOOKING_ESCORT_AND_SLOT_LOGIC_BACKEND_PROMPT.md`). The backend now calculates if a pet physically has time to travel between appointments and enforces that an `escort_owner` must accompany the pet. If the user making the appointment is already occupied, the backend can now reject the booking and demand a specific co-owner to be assigned as the `escort_owner`. 

**Goal:** Your task as a Fullstack engineer is to implement the frontend user experience to support these new backend rules and make minor API adjustments (serializers/views) so the frontend has the data it needs to build a seamless flow.

---

## 1. Required Backend Adjustments (`PetsCare-backend`)

The core domain logic is already implemented. You should not modify the fundamental rules in `booking/unified_services.py` or the transaction creation logic. Your focus is on the API layer (views and serializers) to support the UI.

### 1.1 Booking Serialization
Currently, the backend stores `escort_owner_id`. You must update `BookingListSerializer` (and related read serializers) to return a serialized `escort_owner` object, not just the ID. 
- Include the escort's `id`, `first_name`, and `last_name`.
- This is critical so the UI can display *"Escorted by: John Doe"* on existing bookings.

### 1.2 Co-owner Data in Validation Responses
When the backend draft validation (`/api/v1/booking/appointments/validate/` or creation flow) throws a `409 Conflict` (or structured validation error) demanding explicit `requires_escort_assignment`, it returns an array of `possible_escort_owner_ids` (e.g., `[5, 12]`).
- Ensure the API either returns a mapped dictionary with `{id, name}` for these owners, OR ensure the frontend already possesses the pet's co-owners mapped data when it attempts to book. If relying on pet co-owner data, verify the frontend `Pet` model includes co-owner profiles. If not, update backend endpoints to embed co-owner info when querying a pet.

---

## 2. Required Frontend Implementation (`Petscare-web`)

### 2.1 The Booking Flow Modal 
When the user submits the booking form (e.g., in `BookingModal.tsx` or equivalent component), the application makes a `POST` request to create the booking.

**Error Handling & State:**
- Catch the specific `409 Conflict` (or the HTTP code defined) where the data contains `requires_escort_assignment: true`.
- **Do not** close the booking modal.
- Switch the modal's internal state to a new step: **"Escort Assignment"**.
- Display an informative, friendly message: *"It looks like you are busy or traveling during this time. Who will accompany [Pet Name] to this appointment?"*
- Present a list of the users from `possible_escort_owner_ids` using a polished UI (e.g., a radio group or selectable cards displaying the co-owner's name and optional avatar).
- Add a button `Confirm Booking with Escort`.
- Only proceed to create the booking (sending `POST` with the new `escort_owner_id` payload) once the user makes a selection. 

**Fallback Error Handling:**
- Catch and elegantly display other new domain errors (e.g., `pet_conflict`, `escort_unavailable`, `employee_conflict`). Show them as toast notifications or inline error alerts using the app's standard design system. Translate them if i18n is used.

### 2.2 Booking Cards UI
In the **"My Pets"** or **"My Bookings"** sections where the user's upcoming appointments are displayed:
- Update the `BookingCard` UI component to surface the `escort_owner` information.
- Use a clear visual indicator. For example, if the current logged-in user is the escort: *"Escorted by: You"*. If a co-owner is the escort: *"Escorted by: [Co-owner Name]"*.
- Design this elegantly; use an icon (like `User` or `Users` from Lucide) and subtle text so it doesn't clutter the card but is clearly visible.

### 2.3 API Service Clients
Update your frontend API clients/hooks (e.g., `bookingService.ts` or React Query mutations):
- Add `escort_owner_id?: number` to the interface/type definitions for creating a booking payload.

---

## 3. Tech Stack and Conventions
- **React/TypeScript:** Ensure strict typing for new API payloads.
- **TailwindCSS:** Use the existing design system for the Escort selection UI. It should look premium and native to the app workflow.
- **Django/DRF:** Follow existing DRF patterns for nested serializers when updating the booking list endpoint.

## 4. Expected Outcome
1. A user can see who is escorting their pet on upcoming booking cards.
2. If the user attempts to double-book themselves (e.g., taking "Rex" to Location A, and trying to book "Luna" or "Rex" to Location B simultaneously), the UI intercepts the backend error seamlessly.
3. The UI presents the co-owners of "Luna" as fallback options to escort the pet.
4. When a co-owner is selected, the booking is successfully created via the API with the explicit `escort_owner_id`.
