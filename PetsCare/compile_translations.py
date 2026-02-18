"""
Скрипт для компиляции .po файлов в .mo файлы с использованием babel.
"""
from babel.messages import pofile, mofile
from pathlib import Path

locale_path = Path('locale')

for lang in ['ru', 'me', 'de']:
    po_file = locale_path / lang / 'LC_MESSAGES' / 'django.po'
    mo_file = locale_path / lang / 'LC_MESSAGES' / 'django.mo'
    
    if po_file.exists():
        try:
            with open(po_file, 'rb') as f:
                cat = pofile.read_po(f)
            with open(mo_file, 'wb') as f:
                mofile.write_mo(f, cat)
            print(f'✓ Compiled {lang}/LC_MESSAGES/django.mo')
        except Exception as e:
            print(f'✗ Error compiling {lang}: {e}')
    else:
        print(f'⚠ File not found: {po_file}')

print('\nCompilation complete!')

