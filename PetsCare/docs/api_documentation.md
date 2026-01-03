# API Documentation

## Table of Contents
1. [Authentication](#authentication)
2. [Pets Management](#pets-management)
3. [Pet Search and Filtering](#pet-search-and-filtering)
4. [Medical Records](#medical-records)
5. [Pet Records](#pet-records)
6. [Pet Access](#pet-access)
7. [Providers](#providers)
8. [Bookings](#bookings)
9. [Pet Sitting](#pet-sitting)
10. [Ratings and Reviews](#ratings-and-reviews)
11. [Notifications](#notifications)
12. [Billing](#billing)

## Authentication

All API endpoints require authentication. Use JWT tokens:

```
Authorization: Bearer <your_jwt_token>
```

## Pets Management

### Get All Pets
```
GET /api/pets/
```

### Get Pet by ID
```
GET /api/pets/{id}/
```

### Create Pet
```
POST /api/pets/
```

### Update Pet
```
PUT /api/pets/{id}/
PATCH /api/pets/{id}/
```

### Delete Pet
```
DELETE /api/pets/{id}/
```

## Pet Search and Filtering

### Advanced Pet Search
```
GET /api/pets/search/
```

**Query Parameters:**
- `pet_type` - Filter by pet type ID
- `pet_type_code` - Filter by pet type code
- `breed` - Filter by breed ID
- `breed_code` - Filter by breed code
- `age_min` - Minimum age in years
- `age_max` - Maximum age in years
- `age_range` - Age range (e.g., "2-5")
- `weight_min` - Minimum weight in kg
- `weight_max` - Maximum weight in kg
- `weight_range` - Weight range (e.g., "5-15")
- `has_medical_conditions` - Filter pets with medical conditions (true/false)
- `medical_condition` - Search for specific medical condition
- `has_special_needs` - Filter pets with special needs (true/false)
- `special_need` - Search for specific special need
- `created_after` - Created after this date (YYYY-MM-DD)
- `created_before` - Created before this date (YYYY-MM-DD)
- `updated_after` - Updated after this date (YYYY-MM-DD)
- `updated_before` - Updated before this date (YYYY-MM-DD)
- `last_visit_after` - Last visit after this date (YYYY-MM-DD)
- `last_visit_before` - Last visit before this date (YYYY-MM-DD)
- `owner` - Filter by owner ID
- `main_owner` - Filter by main owner ID
- `is_active` - Filter active/inactive pets (true/false)
- `ordering` - Sort by field (e.g., "name", "-created_at", "weight")
- `page` - Page number for pagination
- `page_size` - Number of items per page (max 100)
- `include_medical_info` - Include medical information in response (true/false)
- `include_records_count` - Include records count in response (true/false)

**Example Request:**
```
GET /api/pets/search/?pet_type=1&age_min=2&age_max=5&has_medical_conditions=true&ordering=name&page=1&page_size=20
```

**Example Response:**
```json
{
    "count": 15,
    "next": "http://api.example.com/api/pets/search/?page=2",
    "previous": null,
    "results": [
        {
            "id": 1,
            "name": "Buddy",
            "pet_type": 1,
            "pet_type_name": "Dog",
            "breed": 5,
            "breed_name": "Golden Retriever",
            "birth_date": "2020-03-15",
            "age": 3,
            "weight": 25.5,
            "description": "Friendly and energetic dog",
            "has_medical_conditions": true,
            "has_special_needs": false,
            "records_count": 12,
            "last_visit_date": "2023-12-01T10:30:00Z",
            "created_at": "2020-03-20T14:30:00Z",
            "updated_at": "2023-12-01T15:45:00Z"
        }
    ]
}
```

### Pet Type Search
```
GET /api/pets/pet-types/search/
```

**Query Parameters:**
- `name` - Search by pet type name
- `code` - Search by pet type code
- `ordering` - Sort by field (e.g., "name", "code")

**Example Request:**
```
GET /api/pets/pet-types/search/?name=dog&ordering=name
```

### Breed Search
```
GET /api/pets/breeds/search/
```

**Query Parameters:**
- `name` - Search by breed name
- `code` - Search by breed code
- `pet_type` - Filter by pet type ID
- `pet_type_code` - Filter by pet type code
- `ordering` - Sort by field (e.g., "name", "pet_type__name")

**Example Request:**
```
GET /api/pets/breeds/search/?pet_type=1&ordering=name
```

### Pet Recommendations
```
GET /api/pets/recommendations/
```

**Query Parameters:**
- `limit` - Number of recommendations (default: 10)

**Example Request:**
```
GET /api/pets/recommendations/?limit=5
```

### Pet Statistics
```
GET /api/pets/statistics/
```

**Example Response:**
```json
{
    "total_pets": 8,
    "pets_by_type": [
        {"pet_type__name": "Dog", "count": 5},
        {"pet_type__name": "Cat", "count": 3}
    ],
    "age_distribution": {
        "young": 2,
        "adult": 4,
        "senior": 2
    },
    "pets_with_medical_conditions": 3,
    "pets_with_special_needs": 1,
    "recent_visits": 6
}
``` 

## Providers

### Provider Locations

Provider locations represent physical service points where organizations provide services. Each organization (Provider) can have multiple locations.

#### Get All Provider Locations
```
GET /api/provider-locations/
```

**Query Parameters:**
- `provider` - Filter by provider organization ID
- `is_active` - Filter by active status (true/false)
- `search` - Search by name, phone number, or email
- `ordering` - Sort by field (e.g., "name", "-created_at")

**Example Request:**
```
GET /api/provider-locations/?provider=1&is_active=true&ordering=name
```

**Example Response:**
```json
{
    "count": 2,
    "results": [
        {
            "id": 1,
            "provider": 1,
            "provider_name": "Test Provider Organization",
            "name": "Филиал на Тимирязевской",
            "structured_address": 1,
            "full_address": "Timiryazevskaya Ulitsa, 20 корпус 1, Moskva, Russia, 127422",
            "latitude": 55.7558,
            "longitude": 37.6173,
            "phone_number": "+79991234568",
            "email": "location1@example.com",
            "available_services": [
                {
                    "id": 1,
                    "location_name": "Филиал на Тимирязевской",
                    "service_name": "Консультация ветеринара",
                    "price": "1000.00",
                    "duration_minutes": 60,
                    "tech_break_minutes": 15,
                    "is_active": true
                }
            ],
            "is_active": true,
            "created_at": "2024-01-15T10:00:00Z",
            "updated_at": "2024-01-15T10:00:00Z"
        }
    ]
}
```

#### Get Provider Location by ID
```
GET /api/provider-locations/{id}/
```

**Example Request:**
```
GET /api/provider-locations/1/
```

#### Create Provider Location
```
POST /api/provider-locations/
```

**Required Permissions:** `system_admin` or `provider_admin` (only for their own organization)

**Request Body:**
```json
{
    "provider": 1,
    "name": "Новая локация",
    "structured_address": 1,
    "phone_number": "+79991234568",
    "email": "location@example.com",
    "is_active": true
}
```

**Example Response:**
```json
{
    "id": 2,
    "provider": 1,
    "provider_name": "Test Provider Organization",
    "name": "Новая локация",
    "full_address": "Timiryazevskaya Ulitsa, 20 корпус 1, Moskva, Russia, 127422",
    "latitude": 55.7558,
    "longitude": 37.6173,
    "phone_number": "+79991234568",
    "email": "location@example.com",
    "available_services": [],
    "is_active": true,
    "created_at": "2024-01-15T11:00:00Z",
    "updated_at": "2024-01-15T11:00:00Z"
}
```

#### Update Provider Location
```
PUT /api/provider-locations/{id}/
PATCH /api/provider-locations/{id}/
```

**Required Permissions:** `system_admin` or `provider_admin` (only for their own organization)

**Request Body:**
```json
{
    "name": "Обновленное название",
    "phone_number": "+79991234569",
    "is_active": false
}
```

#### Delete Provider Location
```
DELETE /api/provider-locations/{id}/
```

**Required Permissions:** `system_admin` or `provider_admin` (only for their own organization)

**Note:** When a location is deactivated, all active and future bookings are automatically cancelled.

### Provider Location Services

Provider location services represent services available at a specific location with location-specific pricing and duration.

#### Get All Provider Location Services
```
GET /api/provider-location-services/
```

**Query Parameters:**
- `location` - Filter by location ID
- `service` - Filter by service ID
- `is_active` - Filter by active status (true/false)
- `ordering` - Sort by field (e.g., "location", "service", "price")

**Example Request:**
```
GET /api/provider-location-services/?location=1&is_active=true
```

**Example Response:**
```json
{
    "count": 1,
    "results": [
        {
            "id": 1,
            "location": 1,
            "location_name": "Филиал на Тимирязевской",
            "service": 1,
            "service_name": "Консультация ветеринара",
            "service_details": {
                "id": 1,
                "name": "Консультация ветеринара",
                "description": "Консультация специалиста"
            },
            "price": "1000.00",
            "duration_minutes": 60,
            "tech_break_minutes": 15,
            "is_active": true,
            "created_at": "2024-01-15T10:00:00Z",
            "updated_at": "2024-01-15T10:00:00Z"
        }
    ]
}
```

#### Get Provider Location Service by ID
```
GET /api/provider-location-services/{id}/
```

#### Create Provider Location Service
```
POST /api/provider-location-services/
```

**Required Permissions:** `system_admin` or `provider_admin` (only for their own organization)

**Request Body:**
```json
{
    "location": 1,
    "service": 1,
    "price": "1000.00",
    "duration_minutes": 60,
    "tech_break_minutes": 15,
    "is_active": true
}
```

**Note:** The service must be from the provider's available category levels (level 0 categories).

#### Update Provider Location Service
```
PUT /api/provider-location-services/{id}/
PATCH /api/provider-location-services/{id}/
```

**Required Permissions:** `system_admin` or `provider_admin` (only for their own organization)

**Request Body:**
```json
{
    "price": "1200.00",
    "duration_minutes": 90,
    "is_active": false
}
```

#### Delete Provider Location Service
```
DELETE /api/provider-location-services/{id}/
```

**Required Permissions:** `system_admin` or `provider_admin` (only for their own organization)

**Note:** The relationship between location and service is unique. You cannot create duplicate location-service pairs.

### Provider Search (Updated)

Provider search now works with locations instead of organizations directly. Users see specific locations with addresses when searching.

#### Search Providers by Distance
```
GET /api/providers/search-by-distance/
```

**Query Parameters:**
- `latitude` - Center latitude (required)
- `longitude` - Center longitude (required)
- `radius` - Search radius in kilometers (required)
- `service_id` - Filter by service ID
- `price_min` - Minimum price
- `price_max` - Maximum price
- `min_rating` - Minimum rating
- `sort_by` - Sort by: "distance", "price_asc", "price_desc", "rating"
- `limit` - Maximum number of results

**Example Request:**
```
GET /api/providers/search-by-distance/?latitude=55.7558&longitude=37.6173&radius=10&service_id=1&sort_by=distance
```

**Example Response:**
```json
{
    "results": [
        {
            "id": 1,
            "name": "Test Provider Organization",
            "location": {
                "id": 1,
                "name": "Филиал на Тимирязевской",
                "full_address": "Timiryazevskaya Ulitsa, 20 корпус 1, Moskva, Russia, 127422",
                "latitude": 55.7558,
                "longitude": 37.6173,
                "distance": 0.5
            },
            "service_price": "1000.00",
            "rating": 4.5
        }
    ]
}
```

**Note:** Results are now grouped by location. Each result includes the nearest location for the provider and the distance to that location.

## Pet Sitting

### Pet Filter for Sitting
```
GET /api/sitters/pets/filter/
```

**Description:** Filter user's pets when creating a pet sitting advertisement.

**Query Parameters:**
- `pet_type` - Filter by pet type code (e.g., "dog", "cat")
- `breed` - Filter by breed code (e.g., "golden_retriever")
- `age_min` - Minimum age in years
- `age_max` - Maximum age in years
- `weight_min` - Minimum weight in kg
- `weight_max` - Maximum weight in kg
- `has_medical_conditions` - Filter pets with medical conditions (true/false)
- `has_special_needs` - Filter pets with special needs (true/false)
- `is_active` - Filter active/inactive pets (true/false)
- `distance_km` - Maximum distance in kilometers (requires lat/lng)
- `lat` - Latitude for distance calculation
- `lng` - Longitude for distance calculation
- `ordering` - Sort by field (e.g., "name", "age", "-age", "weight", "-weight", "distance", "-distance")

**Example Request:**
```
GET /api/sitters/pets/filter/?pet_type=dog&age_min=1&age_max=5&has_medical_conditions=false&ordering=name
```

**Example Response:**
```json
{
    "results": [
        {
            "id": 1,
            "name": "Buddy",
            "pet_type": 1,
            "pet_type_name": "Dog",
            "breed": 5,
            "breed_name": "Golden Retriever",
            "birth_date": "2020-03-15",
            "age": 3,
            "weight": 25.5,
            "description": "Friendly and energetic dog",
            "has_medical_conditions": false,
            "has_special_needs": false,
            "main_owner": 1,
            "main_owner_name": "John Doe",
            "main_owner_email": "john@example.com",
            "created_at": "2020-03-20T14:30:00Z",
            "updated_at": "2023-12-01T15:45:00Z"
        }
    ],
    "meta": {
        "total_count": 1,
        "filters_applied": {
            "pet_type": "dog",
            "breed": null,
            "age_min": "1",
            "age_max": "5",
            "weight_min": null,
            "weight_max": null,
            "has_medical_conditions": "false",
            "has_special_needs": null,
            "is_active": null,
            "distance_km": null
        },
        "ordering": "name"
    }
}
```

**Features:**
- Filters only pets owned by the authenticated user
- Supports multiple filter combinations
- Includes metadata about applied filters
- Supports pagination
- Distance-based filtering (when coordinates provided)
- Age calculation based on birth date
- Medical conditions and special needs filtering
- Active/inactive pet status filtering 