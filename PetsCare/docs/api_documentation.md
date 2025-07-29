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