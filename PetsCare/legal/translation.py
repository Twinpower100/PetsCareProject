"""
Настройки переводов для моделей legal приложения.

Раньше использовался modeltranslation для LegalDocument/LegalDocumentType.
Поля title_en, title_de и т.д. удалены миграцией 0007; переводы хранятся
в DocumentTranslation. Регистрация modeltranslation отключена, чтобы ORM
не запрашивал несуществующие столбцы (title_en и т.п.).
"""
