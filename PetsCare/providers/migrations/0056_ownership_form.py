from django.db import migrations, models
import django.db.models.deletion
import django_countries.fields


OWNERSHIP_FORMS = [
    ('RU', 'ИП', 'Individual Entrepreneur', 'Индивидуальный предприниматель', 'Einzelunternehmer', 'Preduzetnik', 10),
    ('RU', 'ООО', 'Limited Liability Company', 'Общество с ограниченной ответственностью', 'Gesellschaft mit beschränkter Haftung', 'Društvo sa ograničenom odgovornošću', 20),
    ('RU', 'АО', 'Joint-Stock Company', 'Акционерное общество', 'Aktiengesellschaft', 'Akcionarsko društvo', 30),
    ('RU', 'ПАО', 'Public Joint-Stock Company', 'Публичное акционерное общество', 'Öffentliche Aktiengesellschaft', 'Javno akcionarsko društvo', 40),
    ('RU', 'НКО', 'Non-Profit Organization', 'Некоммерческая организация', 'Gemeinnützige Organisation', 'Neprofitna organizacija', 50),
    ('DE', 'GmbH', 'Limited Liability Company', 'Общество с ограниченной ответственностью', 'Gesellschaft mit beschränkter Haftung', 'Društvo sa ograničenom odgovornošću', 10),
    ('DE', 'mbH', 'Limited Liability Company suffix', 'Суффикс общества с ограниченной ответственностью', 'mit beschränkter Haftung', 'Sufiks društva sa ograničenom odgovornošću', 11),
    ('DE', 'UG', 'Entrepreneurial Company', 'Предпринимательское общество', 'Unternehmergesellschaft', 'Preduzetničko društvo', 20),
    ('DE', 'AG', 'Stock Corporation', 'Акционерное общество', 'Aktiengesellschaft', 'Akcionarsko društvo', 30),
    ('DE', 'e.K.', 'Registered Merchant', 'Зарегистрированный коммерсант', 'Eingetragener Kaufmann', 'Registrovani trgovac', 40),
    ('DE', 'GbR', 'Civil Law Partnership', 'Простое товарищество', 'Gesellschaft bürgerlichen Rechts', 'Građansko-pravno partnerstvo', 50),
    ('DE', 'OHG', 'General Partnership', 'Полное товарищество', 'Offene Handelsgesellschaft', 'Ortačko društvo', 60),
    ('DE', 'KG', 'Limited Partnership', 'Коммандитное товарищество', 'Kommanditgesellschaft', 'Komanditno društvo', 70),
    ('DE', 'PartG', 'Professional Partnership', 'Профессиональное партнёрство', 'Partnerschaftsgesellschaft', 'Profesionalno partnerstvo', 80),
    ('DE', 'e.V.', 'Registered Association', 'Зарегистрированная ассоциация', 'Eingetragener Verein', 'Registrovano udruženje', 90),
    ('UA', 'ФОП', 'Individual Entrepreneur', 'Физическое лицо-предприниматель', 'Einzelunternehmer', 'Preduzetnik', 10),
    ('UA', 'ТОВ', 'Limited Liability Company', 'Общество с ограниченной ответственностью', 'Gesellschaft mit beschränkter Haftung', 'Društvo sa ograničenom odgovornošću', 20),
    ('UA', 'ПП', 'Private Enterprise', 'Частное предприятие', 'Privatunternehmen', 'Privatno preduzeće', 30),
    ('UA', 'АТ', 'Joint-Stock Company', 'Акционерное общество', 'Aktiengesellschaft', 'Akcionarsko društvo', 40),
    ('UA', 'ПрАТ', 'Private Joint-Stock Company', 'Частное акционерное общество', 'Private Aktiengesellschaft', 'Privatno akcionarsko društvo', 50),
    ('UA', 'ПАТ', 'Public Joint-Stock Company', 'Публичное акционерное общество', 'Öffentliche Aktiengesellschaft', 'Javno akcionarsko društvo', 60),
    ('ME', 'DOO', 'Limited Liability Company', 'Общество с ограниченной ответственностью', 'Društvo mit beschränkter Haftung', 'Društvo sa ograničenom odgovornošću', 10),
    ('ME', 'AD', 'Joint-Stock Company', 'Акционерное общество', 'Aktiengesellschaft', 'Akcionarsko društvo', 20),
    ('ME', 'Preduzetnik', 'Entrepreneur', 'Предприниматель', 'Einzelunternehmer', 'Preduzetnik', 30),
    ('ME', 'OD', 'General Partnership', 'Полное товарищество', 'Offene Handelsgesellschaft', 'Ortačko društvo', 40),
    ('ME', 'KD', 'Limited Partnership', 'Коммандитное товарищество', 'Kommanditgesellschaft', 'Komanditno društvo', 50),
    ('ME', 'NVO', 'Non-Governmental Organization', 'Некоммерческая организация', 'Nichtregierungsorganisation', 'Nevladina organizacija', 60),
    ('ME', 'JP', 'Public Enterprise', 'Публичное предприятие', 'Öffentliches Unternehmen', 'Javno preduzeće', 70),
    ('FR', 'SARL', 'Limited Liability Company', 'Общество с ограниченной ответственностью', 'Gesellschaft mit beschränkter Haftung', 'Društvo sa ograničenom odgovornošću', 10),
    ('FR', 'SAS', 'Simplified Joint-Stock Company', 'Упрощённое акционерное общество', 'Vereinfachte Aktiengesellschaft', 'Pojednostavljeno akcionarsko društvo', 20),
    ('FR', 'SA', 'Public Limited Company', 'Акционерное общество', 'Aktiengesellschaft', 'Akcionarsko društvo', 30),
    ('FR', 'EURL', 'Single-Member Limited Liability Company', 'ООО с единственным участником', 'Einpersonengesellschaft mit beschränkter Haftung', 'Jednočlano društvo sa ograničenom odgovornošću', 40),
    ('US', 'LLC', 'Limited Liability Company', 'Общество с ограниченной ответственностью', 'Gesellschaft mit beschränkter Haftung', 'Društvo sa ograničenom odgovornošću', 10),
    ('US', 'Corp', 'Corporation', 'Корпорация', 'Kapitalgesellschaft', 'Korporacija', 20),
    ('US', 'Inc', 'Incorporated Company', 'Инкорпорированная компания', 'Kapitalgesellschaft', 'Inkorporirano društvo', 30),
    ('US', 'Partnership', 'Partnership', 'Партнёрство', 'Personengesellschaft', 'Partnerstvo', 40),
    ('US', 'Sole Proprietorship', 'Sole Proprietorship', 'Индивидуальное предприятие', 'Einzelunternehmen', 'Samostalna djelatnost', 50),
]


def seed_ownership_forms(apps, schema_editor):
    OwnershipForm = apps.get_model('providers', 'OwnershipForm')
    for country, code, name_en, name_ru, name_de, name_me, sort_order in OWNERSHIP_FORMS:
        OwnershipForm.objects.update_or_create(
            country=country,
            code=code,
            defaults={
                'name_en': name_en,
                'name_ru': name_ru,
                'name_de': name_de,
                'name_me': name_me,
                'is_active': True,
                'sort_order': sort_order,
            },
        )


def migrate_provider_ownership_forms(apps, schema_editor):
    Provider = apps.get_model('providers', 'Provider')
    OwnershipForm = apps.get_model('providers', 'OwnershipForm')

    for provider in Provider.objects.all():
        code = (getattr(provider, 'organization_type_text', '') or '').strip()
        country = str(getattr(provider, 'country', '') or '').strip().upper()[:2]
        if not code or not country:
            continue
        ownership_form = OwnershipForm.objects.filter(country=country, code__iexact=code).first()
        if not ownership_form:
            ownership_form = OwnershipForm.objects.create(
                country=country,
                code=code,
                name_en=code,
                name_ru=code,
                name_de=code,
                name_me=code,
                is_active=False,
                sort_order=1000,
            )
        provider.organization_type_id = ownership_form.id
        provider.save(update_fields=['organization_type'])


def noop_reverse(apps, schema_editor):
    return None


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0035_user_preferred_language'),
        ('providers', '0055_provider_served_pet_types'),
    ]

    operations = [
        migrations.CreateModel(
            name='OwnershipForm',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('country', django_countries.fields.CountryField(db_index=True, help_text='Country where this ownership form can be used.', max_length=2, verbose_name='Country')),
                ('code', models.CharField(help_text='Stable ownership form code submitted by the frontend.', max_length=50, verbose_name='Code')),
                ('name_en', models.CharField(max_length=120, verbose_name='Name EN')),
                ('name_ru', models.CharField(max_length=120, verbose_name='Name RU')),
                ('name_de', models.CharField(max_length=120, verbose_name='Name DE')),
                ('name_me', models.CharField(max_length=120, verbose_name='Name ME')),
                ('is_active', models.BooleanField(db_index=True, default=True, help_text='Inactive forms stay available for historical records but are hidden from registration.', verbose_name='Is Active')),
                ('sort_order', models.PositiveIntegerField(default=100, verbose_name='Sort Order')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Created At')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Updated At')),
            ],
            options={
                'verbose_name': 'Ownership Form',
                'verbose_name_plural': 'Ownership Forms',
                'ordering': ['country', 'sort_order', 'code'],
            },
        ),
        migrations.RenameField(
            model_name='provider',
            old_name='organization_type',
            new_name='organization_type_text',
        ),
        migrations.AddField(
            model_name='provider',
            name='organization_type',
            field=models.ForeignKey(blank=True, help_text='Legal ownership form of the organization.', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='providers', to='providers.ownershipform', verbose_name='Ownership Form'),
        ),
        migrations.AddConstraint(
            model_name='ownershipform',
            constraint=models.UniqueConstraint(fields=('country', 'code'), name='providers_ownershipform_country_code_uniq'),
        ),
        migrations.AddIndex(
            model_name='ownershipform',
            index=models.Index(fields=['country', 'is_active', 'sort_order'], name='providers_o_country_76d2a5_idx'),
        ),
        migrations.RunPython(seed_ownership_forms, noop_reverse),
        migrations.RunPython(migrate_provider_ownership_forms, noop_reverse),
        migrations.RemoveField(
            model_name='provider',
            name='organization_type_text',
        ),
    ]
