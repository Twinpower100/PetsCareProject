# Geolocation Module

Module for working with addresses and geolocation in the PetsCare system. Provides structured address storage, validation via Google Maps API, geocoding and caching of results.

## Main Components

### 1. Models

#### Address
Structured address model with components:
- `street_number` - house number
- `route` - street
- `locality` - city
- `administrative_area_level_1` - region/state
- `administrative_area_level_2` - district
- `country` - country
- `postal_code` - postal code
- `formatted_address` - formatted address
- `latitude`, `longitude` - coordinates
- `is_validated` - validation flag
- `validation_status` - validation status

#### AddressValidation
Address validation results:
- `address` - link to address
- `is_valid` - validation result
- `formatted_address` - formatted address
- `latitude`, `longitude` - coordinates
- `confidence_score` - confidence level
- `validation_details` - validation details
- `api_response` - API response

#### AddressCache
Caching of geocoding results:
- `query_hash` - query hash
- `query_text` - query text
- `formatted_address` - formatted address
- `latitude`, `longitude` - coordinates
- `api_response` - API response
- `expires_at` - expiration time

### 2. Services

#### AddressValidationService
Main service for address validation:
- `validate_address(address)` - address validation
- `validate_address_text(text)` - text address validation
- `get_cached_result(query_hash)` - getting cached result
- `cache_result(query_hash, result)` - caching result

#### GoogleMapsService
Service for working with Google Maps API:
- `geocode_address(address)` - geocoding address
- `reverse_geocode(lat, lon)` - reverse geocoding
- `get_place_autocomplete(query, session_token)` - autocomplete

### 3. API (Views)

#### AddressViewSet
CRUD operations with addresses:
- `GET /api/addresses/` - list of addresses
- `POST /api/addresses/` - creating address
- `GET /api/addresses/{id}/` - getting address
- `PUT /api/addresses/{id}/` - updating address
- `DELETE /api/addresses/{id}/` - deleting address
- `POST /api/addresses/{id}/validate/` - address validation
- `GET /api/addresses/statistics/` - statistics

#### AddressAutocompleteView
Address autocomplete:
- `POST /api/autocomplete/` - autocomplete

#### AddressGeocodeView
Geocoding addresses:
- `POST /api/geocode/` - geocoding

#### AddressReverseGeocodeView
Reverse geocoding:
- `POST /api/reverse-geocode/` - reverse geocoding

### 4. Forms

#### AddressForm
Form for creating/editing addresses:
- Automatic validation via Google Maps API
- Autocomplete support
- Validation of required fields

#### AddressSearchForm
Form for searching addresses:
- Search by text
- Filtering by validation status
- Filtering by country/city

### 5. Serializers

#### AddressSerializer
Serializer for Address model:
- Automatic validation when creating/updating
- Partial update support

#### AddressValidationSerializer
Serializer for validation results

#### AddressCacheSerializer
Serializer for geocoding cache

### 6. Signals

#### auto_validate_address
Automatic address validation when creating/updating

#### update_address_validation_status
Updating address validation status

#### cleanup_address_data
Cleaning up related data when deleting address

#### cleanup_expired_cache
Cleaning up expired records cache

### 7. Management Commands

#### validate_addresses
Mass address validation:
```bash
python manage.py validate_addresses --all
python manage.py validate_addresses --invalid-only
python manage.py validate_addresses --pending-only --limit 100
```

#### cleanup_geolocation_cache
Cleaning up geolocation cache:
```bash
python manage.py cleanup_geolocation_cache --all
python manage.py cleanup_geolocation_cache --cache-only
python manage.py cleanup_geolocation_cache --validation-only --days 7
```

## Configuration

### 1. Environment Variables

Add to `settings.py`:

```python
# Google Maps API
GOOGLE_MAPS_API_KEY = 'your_api_key_here'

# Address validation settings
ADDRESS_VALIDATION_CACHE_TIMEOUT = 3600  # 1 hour
ADDRESS_VALIDATION_MAX_RETRIES = 3
ADDRESS_VALIDATION_TIMEOUT = 10  # seconds
ADDRESS_VALIDATION_ENABLE_CACHE = True
```

### 2. Dependencies Installation

```bash
pip install googlemaps
```

### 3. Migrations

```bash
python manage.py makemigrations geolocation
python manage.py migrate
```

## Usage

### 1. Creating Address

```python
from geolocation.models import Address
from geolocation.services import AddressValidationService

# Creating address
address = Address.objects.create(
    street_number='123',
    route='Test Street',
    locality='Test City',
    country='Test Country'
)

# Address validation
service = AddressValidationService()
result = service.validate_address(address)

if result.is_valid:
    print(f"Address is valid: {result.formatted_address}")
    print(f"Coordinates: {result.latitude}, {result.longitude}")
```

### 2. Geocoding

```python
from geolocation.services import GoogleMapsService

service = GoogleMapsService()
result = service.geocode_address('123 Test Street, Test City')

if result:
    print(f"Coordinates: {result['geometry']['location']}")
```

### 3. Autocomplete

```python
from geolocation.services import GoogleMapsService

service = GoogleMapsService()
predictions = service.get_place_autocomplete('Test')

for prediction in predictions:
    print(f"Variant: {prediction['description']}")
```

### 4. API Usage

#### Creating Address
```bash
curl -X POST http://localhost:8000/api/addresses/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_token" \
  -d '{
    "street_number": "123",
    "route": "Test Street",
    "locality": "Test City",
    "country": "Test Country"
  }'
```

#### Autocomplete
```bash
curl -X POST http://localhost:8000/api/autocomplete/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_token" \
  -d '{
    "query": "Test"
  }'
```

#### Geocoding
```bash
curl -X POST http://localhost:8000/api/geocode/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_token" \
  -d '{
    "address": "123 Test Street, Test City"
  }'
```

## Integration with Other Modules

### 1. Provider (Institutions)

Model `Provider` now uses structured address:

```python
provider = Provider.objects.create(
    name='Test Clinic',
    structured_address=address,  # Link to Address
    # ... other fields
)
```

### 2. SitterProfile (Sitter Profiles)

Model `SitterProfile` uses structured address:

```python
sitter_profile = SitterProfile.objects.create(
    user=user,
    address=address,  # Link to Address
    # ... other fields
)
```

### 3. User (Users)

Model `User` can have structured address:

```python
user = User.objects.create(
    username='testuser',
    email='test@example.com',
    address=address,  # Link to Address
    # ... other fields
)
```

## Monitoring and Maintenance

### 1. Validation Statistics

```python
from geolocation.models import Address

total = Address.objects.count()
validated = Address.objects.filter(is_validated=True).count()
invalid = Address.objects.filter(validation_status='invalid').count()
pending = Address.objects.filter(validation_status='pending').count()

print(f"Total addresses: {total}")
print(f"Validated: {validated}")
print(f"Invalid: {invalid}")
print(f"Pending validation: {pending}")
```

### 2. Cleaning Old Data

```bash
# Cleaning old validation records (older than 30 days)
python manage.py cleanup_geolocation_cache --validation-only --days 30

# Cleaning expired cache
python manage.py cleanup_geolocation_cache --cache-only
```

### 3. Mass Validation

```bash
# Validation of all invalid addresses
python manage.py validate_addresses --invalid-only

# Validation with limit
python manage.py validate_addresses --pending-only --limit 100
```

## Testing

Running tests:

```bash
python manage.py test geolocation
```

Tests cover:
- Address models
- Validation services
- API endpoints
- Forms and serializers
- Signals

## Security

### 1. API Keys
- Store Google Maps API keys in environment variables
- Do not commit keys to repository
- Use domain/IP restrictions in Google Cloud Console

### 2. Caching
- Configure TTL for cache
- Regularly clean up expired records
- Monitor cache usage

### 3. Rate Limiting
- Configure API request limits
- Use caching to reduce load
- Monitor Google Maps API quota usage

## Performance

### 1. Query Optimization
- Use `select_related()` for related models
- Add indexes for frequently used fields
- Cache geocoding results

### 2. Caching
- Configure Redis/Memcached for caching
- Use TTL for automatic updates
- Monitor hit/miss ratio

### 3. Monitoring
- Monitor API response time
- Monitor Google Maps requests
- Configure alerts for exceeding limits

## Extending Functionality

### 1. Supporting Other Geocoding Providers
You can add support for other providers like Yandex Maps, OpenStreetMap, etc.:

```python
class YandexMapsService:
    def geocode_address(self, address):
        # Implementation for Yandex Maps
        pass

class OpenStreetMapService:
    def geocode_address(self, address):
        # Implementation for OpenStreetMap
        pass
```

### 2. Geofencing
Add functionality to determine if a point is within a given area:

```python
def is_point_in_polygon(point, polygon):
    # Ray casting algorithm
    pass
```

### 3. Finding Nearest Objects
Implement finding nearest facilities, sitters, etc.:

```python
def find_nearest_providers(lat, lon, radius=10):
    # Finding nearest providers
    pass
``` 