"""
Кастомные адаптеры для django-allauth.

Обеспечивают правильную обработку существующих пользователей
при входе через социальные сети (Google OAuth).
"""
import logging

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from django.contrib.auth import get_user_model
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)
User = get_user_model()


def _is_admin_request(request):
    """
    Определяет, является ли запрос запросом из админки.
    
    Проверяет путь, параметр next, реферер и сессию.
    
    Args:
        request: HTTP запрос
        
    Returns:
        bool: True если запрос из админки, False иначе
    """
    # Проверяем, что request не None и имеет необходимые атрибуты
    if request is None or not hasattr(request, 'path'):
        return False
    
    # Проверяем путь
    if request.path.startswith('/admin/') or '/admin/' in request.get_full_path():
        return True
    
    # Проверяем параметр next
    next_url = request.GET.get('next', '') or request.POST.get('next', '')
    if next_url.startswith('/admin/'):
        return True
    
    # Проверяем реферер
    referer = request.META.get('HTTP_REFERER', '')
    if referer:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(referer)
            if parsed.path.startswith('/admin/'):
                return True
        except Exception:
            pass
    
    # Проверяем сессию (если была установлена при первом запросе)
    if request.session.get('admin_login', False):
        return True
    
    # Проверяем параметр state в OAuth callback (может содержать информацию о source)
    # При callback от Google путь может быть /accounts/google/login/callback/
    # но параметр next должен быть в сессии или в state
    if request.path == '/accounts/google/login/callback/':
        # Если это callback и есть next=/admin/ в сессии или GET параметрах
        oauth_next = request.session.get('oauth_next', '')
        if oauth_next.startswith('/admin/'):
            return True
        if request.session.get('next', '').startswith('/admin/'):
            return True
        if request.GET.get('next', '').startswith('/admin/'):
            return True
    
    return False


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Кастомный адаптер для социальных аккаунтов.
    
    Обеспечивает правильное связывание существующих пользователей
    с социальными аккаунтами при входе через Google OAuth.
    Выбирает правильный SocialApp в зависимости от источника запроса (админка vs фронт).
    """
    
    def get_app(self, request, provider):
        """
        Выбирает правильный SocialApp в зависимости от источника запроса.
        
        Для админки: использует SocialApp "PetsCare Admin"
        Для фронта: использует SocialApp "PetsCare Frontend"
        
        Args:
            request: HTTP запрос
            provider: Провайдер OAuth (например, 'google')
            
        Returns:
            SocialApp: Выбранный SocialApp
        """
        from allauth.socialaccount.models import SocialApp
        from django.contrib.sites.models import Site
        
        # Проверяем, что request не None
        if request is None:
            # Это нормальная ситуация в некоторых случаях (например, при инициализации)
            return super().get_app(request, provider)
        
        # Сохраняем параметр next в сессии при первом запросе (перед редиректом на Google)
        if hasattr(request, 'path') and request.path == '/accounts/google/login/':
            next_url = request.GET.get('next', '')
            if next_url:
                request.session['oauth_next'] = next_url
        
        # Определяем, это запрос из админки или с фронта
        is_admin_request = _is_admin_request(request) if request else False
        
        # Получаем текущий Site
        try:
            current_site = Site.objects.get_current(request) if request else None
        except Exception as e:
            logger.warning(f"Could not get current Site: {e}")
            current_site = None
        
        if provider == 'google':
            if is_admin_request:
                # Для админки - ищем SocialApp "PetsCare Admin"
                try:
                    admin_app = SocialApp.objects.get(
                        provider='google',
                        name='PetsCare Admin'
                    )
                    return admin_app
                except SocialApp.DoesNotExist:
                    logger.error("SocialApp 'PetsCare Admin' not found in database")
                    # Fallback на стандартное поведение
                    return super().get_app(request, provider)
            else:
                # Для фронта - ищем SocialApp "PetsCare Frontend"
                try:
                    frontend_app = SocialApp.objects.get(
                        provider='google',
                        name='PetsCare Frontend'
                    )
                    return frontend_app
                except SocialApp.DoesNotExist:
                    logger.error("SocialApp 'PetsCare Frontend' not found in database")
                    # Fallback на стандартное поведение
                    return super().get_app(request, provider)
        
        # Для других провайдеров - стандартное поведение
        return super().get_app(request, provider)
    
    def get_redirect_uri(self, request, app):
        """
        Формирует redirect_uri для OAuth callback.
        """
        return super().get_redirect_uri(request, app)
    
    def pre_social_login(self, request, sociallogin):
        """
        Вызывается перед входом через социальную сеть.
        
        Для админки: проверяет существование пользователя и блокирует создание новых.
        Для фронта: разрешает создание новых пользователей.
        """
        # Если пользователь уже аутентифицирован, ничего не делаем
        if request.user.is_authenticated:
            return
        
        # Определяем, это запрос из админки или с фронта
        is_admin_request = _is_admin_request(request)
        
        # Получаем email из социального аккаунта
        email = None
        if sociallogin.email_addresses:
            email = sociallogin.email_addresses[0].email
        elif hasattr(sociallogin, 'account') and sociallogin.account:
            # Если email нет в данных, пытаемся получить из extra_data
            email = sociallogin.account.extra_data.get('email')
        
        if not email:
            return
        
        # Проверяем, существует ли пользователь с таким email
        # Используем case-insensitive поиск для надежности
        try:
            user = User.objects.get(email__iexact=email)
            # Если пользователь найден, связываем его с социальным аккаунтом
            # Используем прямое присваивание вместо connect(), чтобы избежать проблем с внешними ключами
            sociallogin.user = user
            # Убеждаемся, что пользователь сохранен в БД
            if not user.pk:
                user.save()
        except User.DoesNotExist:
            # Пользователь не найден
            if is_admin_request:
                # Для админки - запрещаем создание нового пользователя
                logger.warning(f"No existing user found with email {email}, access denied (admin)")
                from django.contrib import messages
                messages.error(request, _('User with this email is not registered. Please contact administrator.'))
                raise ImmediateHttpResponse(
                    HttpResponseRedirect('/admin/login/?error=user_not_found')
                )
            # Для фронта - разрешаем создание нового пользователя (не делаем ничего)
        except User.MultipleObjectsReturned:
            # Несколько пользователей с таким email (не должно быть, но на всякий случай)
            # Берем первого
            logger.warning(f"Multiple users found with email {email}, using first one")
            user = User.objects.filter(email__iexact=email).first()
            if user:
                sociallogin.user = user
                if not user.pk:
                    user.save()
        except Exception as e:
            logger.error(f"Error in pre_social_login: {e}", exc_info=True)
            # В случае ошибки позволяем allauth обработать стандартным способом
            pass
    
    def is_open_for_signup(self, request, sociallogin):
        """
        Разрешает или запрещает автоматическую регистрацию через социальные сети.
        
        Для админки: запрещает (только существующие пользователи).
        Для фронта: разрешает (можно создавать новых пользователей).
        """
        # Определяем, это запрос из админки или с фронта
        is_admin_request = _is_admin_request(request)
        logger.info(f"=== is_open_for_signup called ===")
        logger.info(f"Request path: {request.path}")
        logger.info(f"Is admin request: {is_admin_request}")
        logger.info(f"sociallogin.user exists: {hasattr(sociallogin, 'user') and sociallogin.user is not None}")
        if hasattr(sociallogin, 'user') and sociallogin.user:
            logger.info(f"sociallogin.user.id: {sociallogin.user.id}")
        
        if is_admin_request:
            logger.info("Social signup blocked for admin request")
            return False
        else:
            logger.info("Social signup allowed for frontend request")
            return True
    
    def save_user(self, request, sociallogin, form=None):
        """
        Сохраняет пользователя при первом входе через социальную сеть.
        
        Для админки: не должен вызываться (блокируется через is_open_for_signup).
        Для фронта: разрешает создание новых пользователей.
        """
        logger.info(f"=== save_user called ===")
        logger.info(f"Request path: {request.path}")
        logger.info(f"sociallogin.user exists: {hasattr(sociallogin, 'user') and sociallogin.user is not None}")
        
        # Определяем, это запрос из админки или с фронта
        is_admin_request = _is_admin_request(request)
        logger.info(f"Is admin request: {is_admin_request}")
        
        if is_admin_request:
            # Для админки - не должно доходить до этого метода
            logger.error("save_user called for admin request - this should not happen")
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied(_('User creation through social login is not allowed in admin panel. Please contact administrator.'))
        
        # Для фронта - разрешаем создание пользователя
        try:
            logger.info("Calling super().save_user() to create new user")
            user = super().save_user(request, sociallogin, form)
            logger.info(f"Created new user {user.id} from social login with email {user.email} (frontend)")
            return user
        except Exception as e:
            logger.error(f"Error in save_user: {e}", exc_info=True)
            raise


class CustomAccountAdapter(DefaultAccountAdapter):
    """
    Кастомный адаптер для обычных аккаунтов.
    
    Используется для настройки поведения при регистрации и входе.
    """
    
    def is_open_for_signup(self, request):
        """
        Запрещает регистрацию через обычные аккаунты в админке.
        
        Для социальных аккаунтов используется CustomSocialAccountAdapter.
        """
        # В админке регистрация запрещена
        if request.path.startswith('/admin/'):
            return False
        return super().is_open_for_signup(request)
    
    def get_login_redirect_url(self, request):
        """
        Определяет URL для перенаправления после входа.
        
        Если пользователь входит через админку, перенаправляем в админку.
        """
        if request.path.startswith('/admin/'):
            return '/admin/'
        return super().get_login_redirect_url(request)

