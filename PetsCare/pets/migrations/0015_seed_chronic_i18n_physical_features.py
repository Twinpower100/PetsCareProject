# Data: ChronicCondition translations + seed PhysicalFeature

from django.db import migrations


def seed_chronic_translations(apps, schema_editor):
    ChronicCondition = apps.get_model('pets', 'ChronicCondition')
    # name_en = copy from name; fill name_ru, name_de, name_me from known translations
    translations = {
        'osteoarthritis': {'name_en': 'Osteoarthritis / Arthrosis', 'name_ru': 'Остеоартрит / артроз', 'name_de': 'Osteoarthritis / Arthrose', 'name_me': 'Osteoartritis / artroza'},
        'hip_dysplasia': {'name_en': 'Hip dysplasia', 'name_ru': 'Дисплазия тазобедренного сустава', 'name_de': 'Hüftdysplasie', 'name_me': 'Displazija kuka'},
        'patellar_luxation': {'name_en': 'Patellar luxation', 'name_ru': 'Вывих надколенника', 'name_de': 'Patellaluxation', 'name_me': 'Luxacija patelle'},
        'heart_failure': {'name_en': 'Heart failure', 'name_ru': 'Сердечная недостаточность', 'name_de': 'Herzinsuffizienz', 'name_me': 'Zatajenje srca'},
        'tracheal_collapse': {'name_en': 'Tracheal collapse', 'name_ru': 'Коллапс трахеи', 'name_de': 'Trachealkollaps', 'name_me': 'Kolaps dušnika'},
        'asthma': {'name_en': 'Asthma', 'name_ru': 'Астма', 'name_de': 'Asthma', 'name_me': 'Astma'},
        'epilepsy': {'name_en': 'Epilepsy / Seizure disorder', 'name_ru': 'Эпилепсия / судорожное расстройство', 'name_de': 'Epilepsie / Anfallsleiden', 'name_me': 'Epilepsija / napadaji'},
        'atopic_dermatitis': {'name_en': 'Atopic dermatitis', 'name_ru': 'Атопический дерматит', 'name_de': 'Atopische Dermatitis', 'name_me': 'Atopijski dermatitis'},
        'food_allergy': {'name_en': 'Food allergy', 'name_ru': 'Пищевая аллергия', 'name_de': 'Nahrungsmittelallergie', 'name_me': 'Alergija na hranu'},
        'diabetes': {'name_en': 'Diabetes mellitus', 'name_ru': 'Сахарный диабет', 'name_de': 'Diabetes mellitus', 'name_me': 'Dijabetes melitus'},
        'chronic_kidney_disease': {'name_en': 'Chronic kidney disease (CKD)', 'name_ru': 'Хроническая болезнь почек (ХБП)', 'name_de': 'Chronische Nierenerkrankung (CKD)', 'name_me': 'Hronična bubrežna bolest (CKD)'},
    }
    for cond in ChronicCondition.objects.all():
        data = translations.get(cond.code, {})
        if data:
            for key, value in data.items():
                setattr(cond, key, value)
        else:
            cond.name_en = cond.name or ''
        cond.save()


def seed_physical_features(apps, schema_editor):
    PhysicalFeature = apps.get_model('pets', 'PhysicalFeature')
    features = [
        ('featureAmputee', 'Amputee', 'Amputee', 'Отсутствие конечностей', 'Amputiert', 'Amputacija', 0),
        ('featureJointProblems', 'Joint problems', 'Joint problems', 'Проблемы с суставами', 'Gelenkprobleme', 'Problemi sa zglobovima', 1),
        ('featureBlindness', 'Blindness', 'Blindness', 'Слепота', 'Blindheit', 'Sljepoća', 2),
        ('featureDeafness', 'Deafness', 'Deafness', 'Глухота', 'Taubheit', 'Gluhoća', 3),
    ]
    for code, name, name_en, name_ru, name_de, name_me, order in features:
        PhysicalFeature.objects.get_or_create(
            code=code,
            defaults={'name': name, 'name_en': name_en, 'name_ru': name_ru, 'name_de': name_de, 'name_me': name_me, 'order': order}
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('pets', '0014_chronic_condition_i18n_physical_feature'),
    ]

    operations = [
        migrations.RunPython(seed_chronic_translations, noop),
        migrations.RunPython(seed_physical_features, noop),
    ]
