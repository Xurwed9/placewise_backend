
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from notifications.models import Notification


User = get_user_model()


class NotificationAPITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="notification_user",
            phone="+992900000011",
            name="Notification User",
        )

        cls.other_user = User.objects.create_user(
            username="other_notification_user",
            phone="+992900000012",
            name="Other User",
        )

        cls.notification = Notification.objects.create(
            user=cls.user,
            notification_type=Notification.Type.REVIEW_APPROVED,
            title="Отзыв опубликован",
            message="Ваш отзыв опубликован.",
        )

        cls.other_notification = Notification.objects.create(
            user=cls.other_user,
            notification_type=Notification.Type.OWNER_REPLY,
            title="Ответ владельца",
            message="Владелец ответил на ваш отзыв.",
        )

    def setUp(self):
        self.client = APIClient()
        self.url = "/api/v1/notifications/"

    def test_guest_cannot_list_notifications(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 401)

    def test_user_sees_only_own_notifications(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["unread_count"], 1)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(
            response.data["results"][0]["id"],
            self.notification.id,
        )

    def test_user_can_mark_own_notification_read(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            f"{self.url}{self.notification.id}/read/"
        )

        self.assertEqual(response.status_code, 200)

        self.notification.refresh_from_db()
        self.assertTrue(self.notification.is_read)

    def test_user_cannot_mark_other_users_notification_read(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            f"{self.url}{self.other_notification.id}/read/"
        )

        self.assertEqual(response.status_code, 404)

        self.other_notification.refresh_from_db()
        self.assertFalse(self.other_notification.is_read)

    def test_user_can_mark_all_notifications_read(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.post(f"{self.url}read-all/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["updated_count"], 1)

        self.notification.refresh_from_db()
        self.other_notification.refresh_from_db()

        self.assertTrue(self.notification.is_read)
        self.assertFalse(self.other_notification.is_read)
