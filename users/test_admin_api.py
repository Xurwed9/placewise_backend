from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()


class AdminUserCreateAPITests(APITestCase):
    def setUp(self):
        self.url = "/api/v1/admin/users/"

        self.admin = User.objects.create_superuser(
            username="rootadmin",
            phone="+992900000001",
            password="RootAdmin-Strong-2026!",
        )

        self.staff_admin = User.objects.create_user(
            username="staffadmin",
            phone="+992900000002",
            password="StaffAdmin-Strong-2026!",
            role="admin",
            is_staff=True,
        )

        self.regular_user = User.objects.create_user(
            username="regular",
            phone="+992900000003",
            password="RegularUser-Strong-2026!",
        )

        self.moderator = User.objects.create_user(
            username="moderator",
            phone="+992900000004",
            password="Moderator-Strong-2026!",
            role="moderator",
            is_staff=True,
        )

        self.other_admin = User.objects.create_user(
            username="otheradmin",
            phone="+992900000005",
            password="OtherAdmin-Strong-2026!",
            role="admin",
            is_staff=True,
        )

    def payload(self, **overrides):
        data = {
            "phone": "+992900000100",
            "name": "Test User",
            "password": "NewUser-Strong-2026!",
            "role": "user",
            "language": "tg",
        }
        data.update(overrides)
        return data

    def test_superuser_can_create_user_and_password_is_hashed(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.url,
            self.payload(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        created = User.objects.get(phone="+992900000100")
        self.assertTrue(created.check_password("NewUser-Strong-2026!"))
        self.assertNotEqual(created.password, "NewUser-Strong-2026!")
        self.assertEqual(created.role, "user")
        self.assertEqual(created.language, "tg")
        self.assertFalse(created.is_blocked)
        self.assertTrue(created.is_active)
        self.assertNotIn("password", response.data)

    def test_password_is_optional_for_admin_created_user(self):
        data = self.payload(phone="+992900000105")
        data.pop("password")
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(self.url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = User.objects.get(phone="+992900000105")
        self.assertFalse(created.has_usable_password())

    def test_unauthenticated_user_cannot_create_user(self):
        response = self.client.post(
            self.url,
            self.payload(),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertFalse(User.objects.filter(phone="+992900000100").exists())

    def test_regular_user_cannot_create_user(self):
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.post(
            self.url,
            self.payload(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(User.objects.filter(phone="+992900000100").exists())

    def test_staff_admin_can_create_user(self):
        self.client.force_authenticate(user=self.staff_admin)

        response = self.client.post(
            self.url,
            self.payload(phone="+992900000101"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(phone="+992900000101").exists())

    def test_non_superuser_cannot_assign_admin_role(self):
        self.client.force_authenticate(user=self.staff_admin)

        response = self.client.post(
            self.url,
            self.payload(
                phone="+992900000102",
                role="admin",
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(phone="+992900000102").exists())

    def test_superuser_can_assign_admin_role(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.url,
            self.payload(
                phone="+992900000103",
                role="admin",
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        created = User.objects.get(phone="+992900000103")
        self.assertEqual(created.role, "admin")
        self.assertTrue(created.is_staff)
        self.assertFalse(created.is_superuser)

    def test_duplicate_phone_is_rejected(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.url,
            self.payload(phone=self.regular_user.phone),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_weak_password_is_rejected(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.url,
            self.payload(
                phone="+992900000104",
                password="password",
            ),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(phone="+992900000104").exists())

    def test_admin_role_requires_password(self):
        data = self.payload(phone="+992900000106", role="admin")
        data.pop("password")
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(self.url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)
        self.assertFalse(
            User.objects.filter(phone="+992900000106").exists()
        )

    def test_moderator_role_requires_password(self):
        data = self.payload(phone="+992900000107", role="moderator")
        data.pop("password")
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(self.url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.data)

    def test_phone_is_normalized_on_create(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.url,
            self.payload(phone="900000108"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            User.objects.filter(phone="+992900000108").exists()
        )

    def set_password_url(self, user):
        return f"/api/v1/admin/users/{user.pk}/set-password/"

    def test_admin_can_set_password_for_regular_user(self):
        self.client.force_authenticate(user=self.staff_admin)

        response = self.client.post(
            self.set_password_url(self.regular_user),
            {"new_password": "NewUserPassword-Strong-2026!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.regular_user.refresh_from_db()
        self.assertTrue(
            self.regular_user.check_password(
                "NewUserPassword-Strong-2026!"
            )
        )
        self.assertFalse(
            self.regular_user.check_password(
                "RegularUser-Strong-2026!"
            )
        )

    def test_superuser_can_set_password_for_admin(self):
        self.client.force_authenticate(user=self.admin)

        response = self.client.post(
            self.set_password_url(self.other_admin),
            {"new_password": "ChangedAdminPassword-2026!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.other_admin.refresh_from_db()
        self.assertTrue(
            self.other_admin.check_password(
                "ChangedAdminPassword-2026!"
            )
        )

    def test_admin_cannot_set_password_for_another_admin(self):
        self.client.force_authenticate(user=self.staff_admin)

        response = self.client.post(
            self.set_password_url(self.other_admin),
            {"new_password": "ChangedAdminPassword-2026!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.other_admin.refresh_from_db()
        self.assertTrue(
            self.other_admin.check_password(
                "OtherAdmin-Strong-2026!"
            )
        )

    def test_moderator_cannot_set_password(self):
        self.client.force_authenticate(user=self.moderator)

        response = self.client.post(
            self.set_password_url(self.regular_user),
            {"new_password": "NewUserPassword-Strong-2026!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_regular_user_cannot_set_password(self):
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.post(
            self.set_password_url(self.moderator),
            {"new_password": "NewUserPassword-Strong-2026!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_user_cannot_set_password(self):
        response = self.client.post(
            self.set_password_url(self.regular_user),
            {"new_password": "NewUserPassword-Strong-2026!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_set_password_requires_new_password(self):
        self.client.force_authenticate(user=self.staff_admin)

        response = self.client.post(
            self.set_password_url(self.regular_user),
            {},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("new_password", response.data)

    def test_set_password_rejects_weak_password(self):
        self.client.force_authenticate(user=self.staff_admin)

        response = self.client.post(
            self.set_password_url(self.regular_user),
            {"new_password": "password"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("new_password", response.data)
        self.regular_user.refresh_from_db()
        self.assertTrue(
            self.regular_user.check_password(
                "RegularUser-Strong-2026!"
            )
        )

    def test_set_password_returns_404_for_unknown_user(self):
        self.client.force_authenticate(user=self.staff_admin)

        response = self.client.post(
            "/api/v1/admin/users/999999/set-password/",
            {"new_password": "NewUserPassword-Strong-2026!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
