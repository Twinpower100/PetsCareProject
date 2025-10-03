"""
Простой API root view для отображения доступных endpoints.
"""
from django.utils.translation import gettext as _
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(['GET'])
@permission_classes([AllowAny])
def api_root(request):
    """
    Корневой API endpoint, показывающий доступные endpoints.
    """
    return Response({
        'message': 'PetCare API',
        'version': 'v1',
        'endpoints': {
            'authentication': {
                'register': '/api/api/register/',
                'login': '/api/api/login/',
                'google_auth': '/api/api/google-auth/',
                'profile': '/api/api/profile/',
            },
            'documentation': {
                'docs': '/docs/',
            },
            'pets': '/api/pets/',
            'providers': '/api/providers/',
            'booking': '/api/booking/',
            'notifications': '/api/notifications/',
            'billing': '/api/billing/',
            'ratings': '/api/ratings/',
            'reports': '/api/reports/',
            'analytics': '/api/analytics/',
            'audit': '/api/audit/',
            'access': '/api/access/',
            'sitters': '/api/sitters/',
            'services': '/api/services/',
            'scheduling': '/api/scheduling/',
            'security': '/api/security/',
            'user_analytics': '/api/user-analytics/',
        },
        'authentication': {
            'type': 'JWT',
            'header': 'Authorization: Bearer <token>',
            'description': _('Use JWT token for authentication')
        }
    })
