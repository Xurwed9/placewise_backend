
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.test import TestCase
from django.utils import timezone

from rest_framework import status
from rest_framework.test import APIClient

from users.models import PhoneOTP


User = get_user_model()


class AuthAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.phone = "+992900123456"
        self.request_url = "/api/v1/auth/request-code/"
        self.verify_url = "/api/v1/auth/verify-code/"
        self.me_url = "/api/v1/auth/me/"

    def create_otp(self, code="1234", phone=None, expires_in=180):
        return PhoneOTP.objects.create(
            phone=phone or self.phone,
            code_hash=make_password(code),
            expires_at=timezone.now() + timedelta(seconds=expires_in),
        )

    def create_user(self, phone=None, is_blocked=False):
        phone = phone or self.phone
        return User.objects.create_user(
            username=phone,
            phone=phone,
            password="TestPassword123!",
            name="Test User",
            is_blocked=is_blocked,
        )

    def test_request_code_with_invalid_phone(self):
        response = self.client.post(
            self.request_url,
            {"phone": "invalid"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(PhoneOTP.objects.count(), 0)

    def test_request_code_success(self):
        response = self.client.post(
            self.request_url,
            {"phone": self.phone},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["expires_in"], 180)
        self.assertTrue(
            PhoneOTP.objects.filter(phone=self.phone).exists()
        )

    def test_request_code_rate_limit(self):
        now = timezone.now()

        for minute in range(5):
            PhoneOTP.objects.create(
                phone=self.phone,
                code_hash=make_password("1234"),
                created_at=now - timedelta(minutes=minute + 2),
                expires_at=now + timedelta(minutes=3),
            )

        response = self.client.post(
            self.request_url,
            {"phone": self.phone},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_429_TOO_MANY_REQUESTS,
        )

    def test_verify_without_otp(self):
        response = self.client.post(
            self.verify_url,
            {"phone": self.phone, "code": "1234"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_verify_with_wrong_code(self):
        self.create_otp(code="1234")

        response = self.client.post(
            self.verify_url,
            {"phone": self.phone, "code": "9999"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(PhoneOTP.objects.get().attempts, 1)

    def test_verify_with_expired_code(self):
        self.create_otp(expires_in=-10)

        response = self.client.post(
            self.verify_url,
            {"phone": self.phone, "code": "1234"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_verify_success_returns_jwt(self):
        self.create_otp(code="1234")

        response = self.client.post(
            self.verify_url,
            {"phone": self.phone, "code": "1234"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["user"]["phone"], self.phone)
        self.assertTrue(
            PhoneOTP.objects.get().consumed_at is not None
        )

    def test_otp_cannot_be_reused(self):
        self.create_otp(code="1234")

        first = self.client.post(
            self.verify_url,
            {"phone": self.phone, "code": "1234"},
            format="json",
        )
        second = self.client.post(
            self.verify_url,
            {"phone": self.phone, "code": "1234"},
            format="json",
        )

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(
            second.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_blocked_user_cannot_login(self):
        self.create_user(is_blocked=True)
        self.create_otp(code="1234")

        response = self.client.post(
            self.verify_url,
            {"phone": self.phone, "code": "1234"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_profile_requires_authentication(self):
        response = self.client.get(self.me_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_authenticated_user_can_get_profile(self):
        user = self.create_user()
        self.client.force_authenticate(user=user)

        response = self.client.get(self.me_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["phone"], self.phone)

    def test_blocked_user_cannot_get_profile(self):
        user = self.create_user(is_blocked=True)
        self.client.force_authenticate(user=user)

        response = self.client.get(self.me_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_403_FORBIDDEN,
        )
