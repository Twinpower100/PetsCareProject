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
        'message': _('PetCare API'),
        'version': 'v1',
        'endpoints': {
            'authentication': {
                'register': '/api/v1/register/',
                'login': '/api/v1/login/',
                'google_auth': '/api/v1/google-auth/',
                'profile': '/api/v1/profile/',
            },
            'documentation': {
                'docs': '/docs/',
            },
            'pets': '/api/v1/pets/',
            'providers': '/api/v1/providers/',
            'booking': '/api/v1/bookings/',
            'notifications': '/api/v1/notifications/',
            'legal': {
                'public_document': '/api/v1/legal/documents/{document_type}/',
                'accept_document': '/api/v1/legal/documents/{id}/accept/'
            },
            'billing': {
                'payments': '/api/v1/payments/',
                'invoices': '/api/v1/invoices/',
                'refunds': '/api/v1/refunds/',
                'blocking_rules': '/api/v1/blocking-rules/'
            },
            'ratings': '/api/v1/ratings/',
            'reports': {
                'income': '/api/v1/reports/income/',
                'workload': '/api/v1/reports/workload/',
                'debt': '/api/v1/reports/debt/',
                'activity': '/api/v1/reports/activity/',
                'payment': '/api/v1/reports/payment/',
                'cancellation': '/api/v1/reports/cancellation/'
            },
            'analytics': {
                'user_growth': '/api/v1/analytics/user-growth/',
                'provider_performance': '/api/v1/analytics/provider-performance/',
                'revenue_trends': '/api/v1/analytics/revenue-trends/',
                'behavioral': '/api/v1/analytics/behavioral/'
            },
            'audit': {
                'actions': '/api/v1/audit/actions/',
                'statistics': '/api/v1/audit/statistics/'
            },
            'access': '/api/v1/access/',
            'sitters': '/api/v1/sitters/',
            'services': '/api/v1/services/',
        },
        'authentication': {
            'type': 'JWT',
            'header': 'Authorization: Bearer <token>',
            'description': _('Use JWT token for authentication')
        }
    })
