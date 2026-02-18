# Generated migration for updating PaymentHistory to use Provider instead of Contract

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('billing', '0004_add_public_offer_models'),
        ('providers', '0017_locationschedule_delete_providerschedule_and_more'),  # Та же зависимость, что в 0004
    ]

    operations = [
        # Шаг 1: Добавляем provider как nullable (временно)
        migrations.AddField(
            model_name='paymenthistory',
            name='provider',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='payment_history',
                to='providers.provider',
                verbose_name='Provider'
            ),
        ),
        
        # Шаг 2: Добавляем invoice как nullable
        migrations.AddField(
            model_name='paymenthistory',
            name='invoice',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='payment_history',
                to='billing.invoice',
                verbose_name='Invoice'
            ),
        ),
        
        # Шаг 3: Добавляем offer_acceptance как nullable
        migrations.AddField(
            model_name='paymenthistory',
            name='offer_acceptance',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='payment_history',
                to='billing.providerofferacceptance',
                verbose_name='Offer Acceptance'
            ),
        ),
        
        # Шаг 4: Data migration - заполняем provider из contract.provider для существующих записей
        migrations.RunPython(
            code=lambda apps, schema_editor: migrate_payment_history_data(apps, schema_editor),
            reverse_code=migrations.RunPython.noop,
        ),
        
        # Шаг 5: Делаем provider обязательным (NOT NULL)
        migrations.AlterField(
            model_name='paymenthistory',
            name='provider',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='payment_history',
                to='providers.provider',
                verbose_name='Provider'
            ),
        ),
        
        # Шаг 6: Делаем contract nullable (для обратной совместимости)
        migrations.AlterField(
            model_name='paymenthistory',
            name='contract',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='payment_history_legacy',
                to='billing.contract',
                verbose_name='Contract (Legacy)'
            ),
        ),
    ]


def migrate_payment_history_data(apps, schema_editor):
    """
    Миграция данных: заполняет provider из contract.provider для существующих записей PaymentHistory.
    
    Если база пуста, эта функция ничего не делает.
    """
    PaymentHistory = apps.get_model('billing', 'PaymentHistory')
    Contract = apps.get_model('billing', 'Contract')
    
    # Получаем все записи PaymentHistory, у которых есть contract, но нет provider
    payment_histories = PaymentHistory.objects.filter(
        contract__isnull=False,
        provider__isnull=True
    )
    
    for payment_history in payment_histories:
        if payment_history.contract and payment_history.contract.provider:
            payment_history.provider = payment_history.contract.provider
            payment_history.save(update_fields=['provider'])
    
    # Если есть записи без contract, их нужно обработать отдельно
    # В этом случае можно либо удалить их, либо связать с первым доступным провайдером
    # Но так как база пуста, это не должно произойти
    orphaned_payments = PaymentHistory.objects.filter(
        contract__isnull=True,
        provider__isnull=True
    )
    
    if orphaned_payments.exists():
        # Если есть записи без contract и provider, удаляем их
        # (так как они не могут быть валидными)
        orphaned_payments.delete()

