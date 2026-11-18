"""Phase 1 checks (docs/build_order.md and PLAN.md, Phase 1 "Done when")."""
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

BREAKPOINTS = ["475px", "640px", "768px", "1024px", "1280px", "1536px"]


class SetupTests(TestCase):
    def test_health_reports_the_database(self):
        response = self.client.get(reverse("health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "ok"})

    def test_base_page_is_mobile_ready(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertContains(response, 'name="viewport"')
        self.assertContains(response, "Sign in to PathGen")

    def test_home_sends_visitors_to_sign_in(self):
        response = self.client.get(reverse("dashboards:home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_sqlite_in_development_postgresql_in_production(self):
        from unittest import mock

        from django.core.exceptions import ImproperlyConfigured

        from config.settings.base import database_from_env

        self.assertIn(settings.DATABASES["default"]["ENGINE"],
                      ("django.db.backends.sqlite3", "django.db.backends.postgresql"))
        with mock.patch.dict("os.environ", {"DATABASE_URL": ""}):
            config = database_from_env()
            self.assertEqual(config["ENGINE"], "django.db.backends.sqlite3")
            self.assertEqual(config["OPTIONS"]["transaction_mode"], "IMMEDIATE")
            with self.assertRaises(ImproperlyConfigured):
                database_from_env(postgres_only=True)
        with mock.patch.dict("os.environ", {"DATABASE_URL": "sqlite:///x.sqlite3"}):
            with self.assertRaises(ImproperlyConfigured):
                database_from_env(postgres_only=True)
        with mock.patch.dict("os.environ", {"DATABASE_URL": "postgres://u@db:5432/pathgen"}):
            self.assertEqual(database_from_env(postgres_only=True)["ENGINE"], "django.db.backends.postgresql")

    def test_every_account_needs_a_role(self):
        User = get_user_model()
        self.assertEqual(User._meta.label, "accounts.User")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user("no_role", password="x-12345678")
        teacher = User.objects.create_user("t1", password="x-12345678", role=User.Role.TEACHER)
        self.assertTrue(teacher.is_teacher)
        self.assertFalse(teacher.is_student)

    def test_superuser_is_the_app_admin(self):
        User = get_user_model()
        admin = User.objects.create_superuser("root", password="x-12345678")
        self.assertEqual(admin.role, User.Role.ADMIN)

    def test_stylesheet_has_the_six_breakpoints(self):
        css = (Path(settings.BASE_DIR) / "static" / "css" / "app.css").read_text(encoding="utf-8")
        for width in BREAKPOINTS:
            self.assertIn(f"/* @media (min-width: {width}) {{}} */", css)
