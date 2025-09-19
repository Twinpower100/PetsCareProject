/**
 * JavaScript для улучшения UX в админке UserType
 */

(function($) {
    'use strict';
    
    $(document).ready(function() {
        // Находим поле permissions
        var permissionsField = $('#id_permissions');
        
        if (permissionsField.length) {
            // Добавляем обработчик изменения
            permissionsField.on('change', function() {
                var selectedValues = $(this).val() || [];
                var hasPredefinedSet = false;
                var predefinedSetValue = null;
                
                // Проверяем, есть ли выбранный предопределенный набор
                for (var i = 0; i < selectedValues.length; i++) {
                    if (selectedValues[i].startsWith('SET:')) {
                        hasPredefinedSet = true;
                        predefinedSetValue = selectedValues[i];
                        break;
                    }
                }
                
                // Если выбран предопределенный набор, показываем предупреждение
                if (hasPredefinedSet && selectedValues.length > 1) {
                    // Находим или создаем элемент предупреждения
                    var warningDiv = $('#permissions-warning');
                    if (warningDiv.length === 0) {
                        warningDiv = $('<div id="permissions-warning" style="background: #fff3cd; border: 1px solid #ffeaa7; color: #856404; padding: 10px; margin: 10px 0; border-radius: 4px;"></div>');
                        permissionsField.closest('.field-permissions').after(warningDiv);
                    }
                    
                    var roleName = predefinedSetValue.replace('SET:', '');
                    warningDiv.html(
                        '<strong>Предупреждение:</strong> Выбран предопределенный набор "' + roleName + '". ' +
                        'Отдельные разрешения будут добавлены к набору. ' +
                        'Рекомендуется использовать только предопределенные наборы для консистентности.'
                    );
                } else {
                    // Убираем предупреждение
                    $('#permissions-warning').remove();
                }
            });
            
            // Добавляем подсказку
            var helpText = $('<div style="color: #666; font-size: 12px; margin-top: 5px;">' +
                '<strong>Подсказка:</strong> Выберите предопределенный набор роли (например, "System Administrator") ' +
                'или отдельные разрешения. Предопределенные наборы автоматически включают все необходимые разрешения.' +
                '</div>');
            permissionsField.closest('.field-permissions').append(helpText);
        }
    });
    
})(django.jQuery);
