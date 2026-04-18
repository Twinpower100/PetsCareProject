from decimal import Decimal
import re

from django.db import migrations, models


UNAPPLIED_REMAINDER_RE = re.compile(
    r"Unapplied remainder after invoice allocation:\s*(?P<amount>-?\d+(?:\.\d+)?)"
)


def populate_unapplied_amount(apps, schema_editor):
    Payment = apps.get_model("billing", "Payment")
    for payment in Payment.objects.exclude(notes="").iterator():
        match = UNAPPLIED_REMAINDER_RE.search(payment.notes or "")
        if match is None:
            continue
        payment.unapplied_amount = Decimal(match.group("amount"))
        payment.save(update_fields=["unapplied_amount"])


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0030_alter_regionalblockingpolicy_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="unapplied_amount",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Part of the payment that stayed unapplied after invoice allocation",
                max_digits=10,
                verbose_name="Unapplied Amount",
            ),
        ),
        migrations.RunPython(populate_unapplied_amount, migrations.RunPython.noop),
    ]
