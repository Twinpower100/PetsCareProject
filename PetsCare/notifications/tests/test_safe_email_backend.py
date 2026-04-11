from django.core import mail
from django.core.mail import send_mail
from django.test import SimpleTestCase, override_settings

from notifications.email_safety import is_reserved_demo_recipient, split_safe_recipients


class EmailSafetyHelpersTests(SimpleTestCase):
    def test_reserved_demo_recipient_detection(self):
        self.assertTrue(is_reserved_demo_recipient("demo@example.com"))
        self.assertTrue(is_reserved_demo_recipient("Demo User <demo@example.org>"))
        self.assertTrue(is_reserved_demo_recipient("seed@local.test"))
        self.assertFalse(is_reserved_demo_recipient("client@petcare.me"))

    def test_split_safe_recipients(self):
        safe, skipped = split_safe_recipients(
            ["demo@example.com", "client@petcare.me", "seed@demo.invalid"]
        )

        self.assertEqual(safe, ["client@petcare.me"])
        self.assertEqual(skipped, ["demo@example.com", "seed@demo.invalid"])


@override_settings(
    EMAIL_BACKEND="notifications.safe_email_backend.SafeEmailBackend",
    ACTUAL_EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
class SafeEmailBackendTests(SimpleTestCase):
    def test_backend_drops_reserved_demo_recipients(self):
        delivered = send_mail(
            "Demo only",
            "Body",
            "noreply@petcare.me",
            ["demo@example.com"],
        )

        self.assertEqual(delivered, 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_backend_keeps_real_recipients(self):
        delivered = send_mail(
            "Real recipient",
            "Body",
            "noreply@petcare.me",
            ["demo@example.com", "owner@petcare.me"],
        )

        self.assertEqual(delivered, 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["owner@petcare.me"])
