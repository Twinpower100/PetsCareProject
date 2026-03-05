# Seed BehavioralTrait with translations (en, ru, de, me)

from django.db import migrations


def seed_behavioral_traits(apps, schema_editor):
    BehavioralTrait = apps.get_model('pets', 'BehavioralTrait')
    # code, name, name_en, name_ru, name_de, name_me, order
    traits = [
        ('traitFlightRisk', 'Flight Risk', 'Flight Risk', 'Склонность к побегу', 'Fluchtrisiko', 'Sklonost bjekstvu', 0),
        ('traitAnimalAggression', 'Animal Aggression', 'Animal Aggression', 'Агрессия к животным', 'Tieraggression', 'Agresija prema životinjama', 1),
        ('traitHumanAggression', 'Human Aggression', 'Human Aggression', 'Агрессия к людям', 'Menschenaggression', 'Agresija prema ljudima', 2),
        ('traitLoudNoiseFear', 'Fear of Loud Noises', 'Fear of Loud Noises', 'Боязнь громких звуков', 'Angst vor lauten Geräuschen', 'Strah od glasnih zvukova', 3),
        ('traitFoodAggression', 'Food Aggression', 'Food Aggression', 'Пищевая агрессия', 'Futteraggression', 'Agresija oko hrane', 4),
        ('traitStressBiting', 'Bites under stress', 'Bites under stress', 'Кусается при стрессе', 'Beißt bei Stress', 'Ujeda pod stresom', 5),
        ('traitPottyTrained', 'Potty Trained', 'Potty Trained', 'Приучен к лотку/выгулу', 'Stubenrein', 'Naučen na toalet/izlazak', 6),
        ('traitDestructive', 'Destructive Behavior', 'Destructive Behavior', 'Портит вещи', 'Zerstörerisch', 'Destruktivno ponašanje', 7),
        ('traitSeparationAnxiety', 'Separation Anxiety', 'Separation Anxiety', 'Воет в одиночестве', 'Trennungsangst', 'Strah od odvajanja', 8),
        ('traitWaterFear', 'Fear of Water', 'Fear of Water', 'Боязнь воды', 'Angst vor Wasser', 'Strah od vode', 9),
        ('traitDryerFear', 'Fear of Dryer', 'Fear of Dryer', 'Боязнь фена', 'Angst vor Föhn', 'Strah od fena', 10),
    ]
    for code, name, name_en, name_ru, name_de, name_me, order in traits:
        BehavioralTrait.objects.get_or_create(
            code=code,
            defaults={'name': name, 'name_en': name_en, 'name_ru': name_ru, 'name_de': name_de, 'name_me': name_me, 'order': order}
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('pets', '0016_behavioral_trait'),
    ]

    operations = [
        migrations.RunPython(seed_behavioral_traits, noop),
    ]
