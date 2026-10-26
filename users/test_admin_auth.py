from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APITestCase


User = get_user_model()

LOGIN_URL = "/api/v1/auth/admin/login/"


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "placewise-admin-login-tests",
        }
    }
)
class AdminPhonePasswordLoginTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.password = "Admin-Strong-Password-2026!"

        self.admin = User.objects.create_user(
            username="+992900000001",
            phone="+992900000001",
            password=self.password,
            name="Admin",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.moderator = User.objects.create_user(
            username="+992900000002",
            phone="+992900000002",
            password=self.password,
            name="Moderator",
            role=User.Role.MODERATOR,
            is_staff=True,
        )
        self.regular_user = User.objects.create_user(
            username="+992900000003",
            phone="+992900000003",
            password=self.password,
            name="User",
            role=User.Role.USER,
        )
        self.superuser = User.objects.create_superuser(
            username="+992900000004",
            phone="+992900000004",
            password=self.password,
            name="Superuser",
        )

    def login(self, phone, password=None):
        return self.client.post(
            LOGIN_URL,
            {
                "phone": phone,
                "password": self.password if password is None else password,
            },
            format="json",
        )

    def test_admin_can_login_and_receive_tokens(self):
        response = self.login(self.admin.phone)

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["user"]["id"], self.admin.id)
        self.assertEqual(response.data["user"]["phone"], self.admin.phone)
        self.assertEqual(response.data["user"]["role"], "admin")
        self.assertTrue(response.data["user"]["is_staff"])

    def test_moderator_can_login(self):
        response = self.login(self.moderator.phone)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["role"], "moderator")

    def test_superuser_can_login(self):
        response = self.login(self.superuser.phone)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["role"], "admin")
        self.assertTrue(response.data["user"]["is_superuser"])

    def test_access_token_can_open_admin_api(self):
        response = self.login(self.admin.phone)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {response.data['access']}"
        )

        response = self.client.get("/api/v1/admin/users/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("items", response.data)

    def test_wrong_password_is_rejected(self):
        response = self.login(self.admin.phone, "wrong-password")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.data["detail"],
            "Неверный телефон или пароль.",
        )

    def test_unknown_phone_is_rejected(self):
        response = self.login("+992900000099")

        self.assertEqual(response.status_code, 401)

    def test_regular_user_cannot_login_to_admin_api(self):
        response = self.login(self.regular_user.phone)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.data["detail"],
            "Доступ разрешён только администраторам.",
        )

    def test_blocked_admin_cannot_login(self):
        self.admin.is_blocked = True
        self.admin.save(update_fields=["is_blocked"])

        response = self.login(self.admin.phone)

        self.assertEqual(response.status_code, 403)

    def test_inactive_admin_cannot_login(self):
        self.admin.is_active = False
        self.admin.save(update_fields=["is_active"])

        response = self.login(self.admin.phone)

        self.assertEqual(response.status_code, 403)

    def test_admin_with_unusable_password_cannot_login(self):
        self.admin.set_unusable_password()
        self.admin.save(update_fields=["password"])

        response = self.login(self.admin.phone)

        self.assertEqual(response.status_code, 401)

    def test_missing_password_is_rejected(self):
        response = self.client.post(
            LOGIN_URL,
            {"phone": self.admin.phone},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_invalid_phone_is_rejected(self):
        response = self.client.post(
            LOGIN_URL,
            {"phone": "invalid", "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_phone_is_normalized(self):
        response = self.login("900000001")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["user"]["phone"],
            "+992900000001",
        )

    def test_legacy_unnormalized_phone_still_logs_in(self):
        legacy = User.objects.create_user(
            username="900000009",
            phone="900000009",
            password=self.password,
            role=User.Role.ADMIN,
            is_staff=True,
        )

        response = self.login("900000009")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["id"], legacy.id)

    def test_password_is_not_returned(self):
        response = self.login(self.admin.phone)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("password", response.data)
        self.assertNotIn("password", response.data["user"])

    def test_old_email_code_endpoints_are_removed(self):
        response = self.client.post(
            "/api/v1/auth/admin/request-code/",
            {"email": "admin@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, 404)
