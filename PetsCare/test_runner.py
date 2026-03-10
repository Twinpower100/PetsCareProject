"""
Кастомный test runner для стабильного discovery в monorepo-layout.
"""

import importlib
import sys
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.test.runner import DiscoverRunner


class AppLabelDiscoverRunner(DiscoverRunner):
    """
    При пустом `manage.py test` собирает suite по app labels, а не по raw fs-discovery.

    Это исключает импорт модулей как `PetsCare.billing.tests`, когда приложение
    зарегистрировано в `INSTALLED_APPS` как `billing`.
    """

    def build_suite(self, test_labels=None, extra_tests=None, **kwargs):
        self._install_project_module_aliases()

        if not test_labels:
            test_labels = self._default_test_labels()

        if extra_tests is not None:
            kwargs['extra_tests'] = extra_tests

        return super().build_suite(test_labels=test_labels, **kwargs)

    def _default_test_labels(self):
        project_root = (Path(settings.BASE_DIR) / 'PetsCare').resolve()
        labels = ['tests']

        for app_config in apps.get_app_configs():
            try:
                app_path = Path(app_config.path).resolve()
            except OSError:
                continue

            if project_root == app_path or project_root in app_path.parents:
                labels.append(app_config.name)

        return list(dict.fromkeys(labels))

    def _install_project_module_aliases(self):
        for label in self._default_test_labels():
            if label == 'tests':
                continue

            try:
                package = importlib.import_module(label)
            except Exception:
                continue

            sys.modules.setdefault(f'PetsCare.{label}', package)

            for submodule in ('models', 'tests'):
                try:
                    imported = importlib.import_module(f'{label}.{submodule}')
                except Exception:
                    continue
                sys.modules.setdefault(f'PetsCare.{label}.{submodule}', imported)
