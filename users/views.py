from django.conf import settings
import logging
import re
import secrets
from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.utils import timezone

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes,throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from drf_spectacular.utils import extend_schema, OpenApiRequest
from .serializers import UserProfileSerializer, UserProfileUpdateSerializer
from .throttles import OTPRequestRateThrottle
from core.sms import SMSDeliveryError, send_sms

from .serializers import UserProfileSerializer

from .models import PhoneOTP

logger = logging.getLogger(__name__)


from .phone_utils import normalize_phone



@extend_schema(
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "phone": {
                    "type": "string",
                    "example": "+992900123456",
                }
            },
            "required": ["phone"],
        }
    },
    responses={200: None, 400: None, 429: None},
)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([OTPRequestRateThrottle])
def request_code(request):
    raw_phone = request.data.get("phone", "")

    if not isinstance(raw_phone, str):
        return Response(
            {"detail": "Телефон бояд матн бошад."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    phone = normalize_phone(raw_phone)

    if not phone:
        return Response(
            {"detail": "Рақами телефон нодуруст аст."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    now = timezone.now()

    # Allow at most 5 code requests per phone in a rolling hour.
    recent_requests = PhoneOTP.objects.filter(
        phone=phone,
        created_at__gte=now - timedelta(hours=1),
    ).count()

    if recent_requests >= 5:
        return Response(
            {"detail": "Шумо дар як соат ҳадди аксар 5 код гирифта метавонед."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    # Resend is allowed only once per minute.
    latest = PhoneOTP.objects.filter(
    phone=phone
        ).order_by("-created_at").first()

    if latest and latest.created_at > now - timedelta(minutes=1):
        return Response(
            {"detail": "Пеш аз гирифтани коди нав 1 дақиқа интизор шавед."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    code = f"{secrets.randbelow(10000):04d}"

    otp = PhoneOTP.objects.create(
        phone=phone,
        code_hash=make_password(code),
        expires_at=now + timedelta(minutes=3),
    )

    try:
        sms_sent = send_sms(
            phone,
            f"Placewise: коди тасдиқ {code}. Муҳлат: 3 дақиқа.",
        )
    except SMSDeliveryError as exc:
        otp.delete()
        logger.error("Failed to deliver OTP SMS to %s: %s", phone, exc)
        return Response(
            {"detail": "Хатои фиристодани SMS. Баъдтар кӯшиш кунед."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    # Development only: print the code when real SMS is disabled.
    if settings.DEBUG and not sms_sent:
        print(f"Development OTP: {code}")

    return Response(
        {
            "detail": "Агар рақам дуруст бошад, коди тасдиқ фиристода мешавад.",
            "expires_in": 180,
        },
        status=status.HTTP_200_OK,
    )



User = get_user_model()



@extend_schema(
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "phone": {
                    "type": "string",
                    "example": "+992900123456",
                },
                "code": {
                    "type": "string",
                    "example": "0440",
                },
            },
            "required": ["phone", "code"],
        }
    },
    responses={200: None, 400: None, 403: None, 429: None},
)
@api_view(["POST"])
@permission_classes([AllowAny])
def verify_code(request):
    phone = request.data.get("phone", "")
    code = request.data.get("code", "")

    if not isinstance(phone, str) or not isinstance(code, str):
        return Response(
            {"detail": "Телефон ва код бояд матн бошанд."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    phone = normalize_phone(phone)

    if not phone or not re.fullmatch(r"\d{4}", code):
        return Response(
            {"detail": "Телефон ё код нодуруст аст."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    otp = PhoneOTP.objects.filter(
        phone=phone,
        consumed_at__isnull=True,
    ).order_by("-created_at").first()

    if otp is None:
        return Response(
            {"detail": "Код ёфт нашуд. Коди нав гиред."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if otp.expires_at <= timezone.now():
        return Response(
            {"detail": "Муҳлати код тамом шуд. Коди нав гиред."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if otp.attempts >= 5:
        return Response(
            {"detail": "Шумораи кӯшишҳо тамом шуд. Коди нав гиред."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    otp.attempts += 1

    if not check_password(code, otp.code_hash):
        otp.save(update_fields=["attempts"])
        return Response(
            {"detail": "Код нодуруст аст."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    otp.consumed_at = timezone.now()
    otp.save(update_fields=["attempts", "consumed_at"])

    user, created = User.objects.get_or_create(
        phone=phone,
        defaults={
            "username": phone,
            "name": "",
        },
    )

    if user.is_blocked or not user.is_active:
        return Response(
            {"detail": "Ин ҳисоб дастрас нест."},
            status=status.HTTP_403_FORBIDDEN,
        )

    refresh = RefreshToken.for_user(user)

    return Response(
        {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": user.id,
                "phone": user.phone,
                "name": user.name,
                "language": user.language,
            },
        },
        status=status.HTTP_200_OK,
    )




@extend_schema(
    request={"multipart/form-data": UserProfileUpdateSerializer},
    methods=["PATCH"],
    responses={200: UserProfileSerializer, 400: None, 401: None, 403: None},
)
@extend_schema(
    methods=["GET"],
    responses=UserProfileSerializer,
)
@api_view(["GET", "PATCH"])
@parser_classes([MultiPartParser, FormParser, JSONParser])
@permission_classes([IsAuthenticated])
def me(request):
    if request.user.is_blocked or not request.user.is_active:
        return Response(
            {"detail": "Ин ҳисоб дастрас нест."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method == "GET":
        serializer = UserProfileSerializer(
            request.user,
            context={"request": request},
        )
        return Response(serializer.data)

    serializer = UserProfileUpdateSerializer(
    request.user,
    data=request.data,
    partial=True,
    context={"request": request},
)

    serializer.is_valid(raise_exception=True)
    serializer.save()

    return Response(serializer.data)
