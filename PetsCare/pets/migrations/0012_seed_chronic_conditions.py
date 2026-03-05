# Data migration: seed ChronicCondition reference list

from django.db import migrations


def seed_chronic_conditions(apps, schema_editor):
    ChronicCondition = apps.get_model('pets', 'ChronicCondition')
    # Order within category for display
    conditions = [
        # Orthopaedic
        ('osteoarthritis', 'Osteoarthritis / Arthrosis', 'orthopaedic', 0),
        ('hip_dysplasia', 'Hip dysplasia', 'orthopaedic', 1),
        ('patellar_luxation', 'Patellar luxation', 'orthopaedic', 2),
        # Cardiological and respiratory
        ('heart_failure', 'Heart failure', 'cardio_respiratory', 0),
        ('tracheal_collapse', 'Tracheal collapse', 'cardio_respiratory', 1),
        ('asthma', 'Asthma', 'cardio_respiratory', 2),
        # Neurological
        ('epilepsy', 'Epilepsy / Seizure disorder', 'neurological', 0),
        # Dermatological and immune
        ('atopic_dermatitis', 'Atopic dermatitis', 'dermatological_immune', 0),
        ('food_allergy', 'Food allergy', 'dermatological_immune', 1),
        # Endocrine and systemic
        ('diabetes', 'Diabetes mellitus', 'endocrine_systemic', 0),
        ('chronic_kidney_disease', 'Chronic kidney disease (CKD)', 'endocrine_systemic', 1),
    ]
    for code, name, category, order in conditions:
        ChronicCondition.objects.get_or_create(
            code=code,
            defaults={'name': name, 'category': category, 'order': order}
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('pets', '0011_chronic_condition_and_vaccination_expiry'),
    ]

    operations = [
        migrations.RunPython(seed_chronic_conditions, noop),
    ]
