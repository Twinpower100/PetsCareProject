from django.utils import translation

class ForceAdminEnglishMiddleware:
    """
    Middleware, которое принудительно переключает язык интерфейса на английский
    для всех страниц Django Admin (пути, начинающиеся с /admin/).
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Проверяем, начинается ли путь с /admin/
        if request.path.startswith('/admin/'):
            # Запоминаем текущий активный язык
            current_lang = translation.get_language()
            
            # Устанавливаем английский язык для этого запроса
            translation.activate('en')
            request.LANGUAGE_CODE = 'en'
            
            response = self.get_response(request)
            
            # Восстанавливаем предыдущий язык
            if current_lang:
                translation.activate(current_lang)
            else:
                translation.deactivate()
                
            return response
            
        # Для всех остальных путей просто продолжаем выполнение
        return self.get_response(request)
