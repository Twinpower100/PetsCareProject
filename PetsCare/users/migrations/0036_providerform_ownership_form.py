from django.db import migrations, models
import django.db.models.deletion


def migrate_provider_form_ownership_forms(apps, schema_editor):
    ProviderForm = apps.get_model('users', 'ProviderForm')
    OwnershipForm = apps.get_model('providers', 'OwnershipForm')

    for provider_form in ProviderForm.objects.all():
        code = (getattr(provider_form, 'organization_type_text', '') or '').strip()
        country = str(getattr(provider_form, 'country', '') or '').strip().upper()[:2]
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
        provider_form.organization_type_id = ownership_form.id
        provider_form.save(update_fields=['organization_type'])


def noop_reverse(apps, schema_editor):
    return None


class Migration(migrations.Migration):

    dependencies = [
        ('providers', '0056_ownership_form'),
        ('users', '0035_user_preferred_language'),
    ]

    operations = [
        migrations.RenameField(
            model_name='providerform',
            old_name='organization_type',
            new_name='organization_type_text',
        ),
        migrations.AddField(
            model_name='providerform',
            name='organization_type',
            field=models.ForeignKey(blank=True, help_text='Legal ownership form of the organization (required)', null=True, on_delete=django.db.models.deletion.PROTECT, related_name='provider_forms', to='providers.ownershipform', verbose_name='Ownership Form'),
        ),
        migrations.RunPython(migrate_provider_form_ownership_forms, noop_reverse),
        migrations.RemoveField(
            model_name='providerform',
            name='organization_type_text',
        ),
    ]
