from rest_framework.views import exception_handler

SUPPORTED_LANGUAGES = {"ru", "tg", "en"}

MESSAGES = {
    "VALIDATION_ERROR": {
        "ru": "Проверьте переданные данные.",
        "tg": "Маълумоти воридшударо санҷед.",
        "en": "Please check the submitted data.",
    },
    "AUTH_REQUIRED": {
        "ru": "Требуется авторизация.",
        "tg": "Воридшавӣ лозим аст.",
        "en": "Authentication is required.",
    },
    "INVALID_TOKEN": {
        "ru": "Токен недействителен.",
        "tg": "Токен эътибор надорад.",
        "en": "The token is invalid.",
    },
    "USER_BLOCKED": {
        "ru": "Этот аккаунт недоступен.",
        "tg": "Ин ҳисоб дастрас нест.",
        "en": "This account is unavailable.",
    },
    "PERMISSION_DENIED": {
        "ru": "Доступ запрещён.",
        "tg": "Дастрасӣ манъ аст.",
        "en": "Permission denied.",
    },
    "NOT_FOUND": {
        "ru": "Не найдено.",
        "tg": "Ёфт нашуд.",
        "en": "Not found.",
    },
    "METHOD_NOT_ALLOWED": {
        "ru": "Метод не разрешён.",
        "tg": "Усул иҷозат дода нашудааст.",
        "en": "Method not allowed.",
    },
    "TOO_MANY_REQUESTS": {
        "ru": "Слишком много запросов. Попробуйте позже.",
        "tg": "Дархостҳо аз ҳад зиёд шуданд. Баъдтар кӯшиш кунед.",
        "en": "Too many requests. Try again later.",
    },
    "CONFLICT": {
        "ru": "Конфликт данных.",
        "tg": "Мухолифати маълумот.",
        "en": "Data conflict.",
    },
    "INTERNAL_ERROR": {
        "ru": "Внутренняя ошибка сервера.",
        "tg": "Хатои дохилии сервер.",
        "en": "Internal server error.",
    },
    "ERROR": {
        "ru": "Ошибка запроса.",
        "tg": "Хатои дархост.",
        "en": "Request error.",
    },
    "REVIEW_TOO_SHORT": {
        "ru": "Отзыв должен содержать минимум 50 символов.",
        "tg": "Отзыв бояд камаш 50 аломат дошта бошад.",
        "en": "The review must contain at least 50 characters.",
    },
    "REVIEW_TOO_LONG": {
        "ru": "Отзыв не должен превышать 2000 символов.",
        "tg": "Отзыв набояд аз 2000 аломат зиёд бошад.",
        "en": "The review must not exceed 2000 characters.",
    },
    "REVIEW_RATING_INVALID": {
        "ru": "Оценка должна быть от 1 до 5.",
        "tg": "Баҳо бояд аз 1 то 5 бошад.",
        "en": "The rating must be between 1 and 5.",
    },
    "REVIEW_LANG_INVALID": {
        "ru": "Язык отзыва должен быть ru, tg или en.",
        "tg": "Забони отзыв бояд ru, tg ё en бошад.",
        "en": "The review language must be ru, tg or en.",
    },
}

STATUS_CODES = {
    400: "VALIDATION_ERROR",
    401: "AUTH_REQUIRED",
    403: "PERMISSION_DENIED",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    429: "TOO_MANY_REQUESTS",
    500: "INTERNAL_ERROR",
}


def get_request_language(request):
    if request is None:
        return "ru"

    params = getattr(request, "query_params", None)

    if params is None:
        params = getattr(request, "GET", {})

    language = (params.get("lang") or "").lower()

    if language in SUPPORTED_LANGUAGES:
        return language

    accept_language = request.headers.get("Accept-Language", "")

    for item in accept_language.split(","):
        candidate = item.split(";")[0].strip().lower().split("-")[0]

        if candidate in SUPPORTED_LANGUAGES:
            return candidate

    return "ru"


def get_message(code, request):
    language = get_request_language(request)
    translations = MESSAGES.get(code, MESSAGES["ERROR"])
    return translations.get(language, translations["ru"])


def find_specific_error_code(details):
    if isinstance(details, dict):
        for value in details.values():
            code = find_specific_error_code(value)
            if code:
                return code
        return None

    if isinstance(details, (list, tuple)):
        for value in details:
            code = find_specific_error_code(value)
            if code:
                return code
        return None

    code = getattr(details, "code", None)

    if isinstance(code, str):
        candidate = code.upper()
        if candidate in MESSAGES and candidate != "VALIDATION_ERROR":
            return candidate

    return None


def get_error_code(exception, response, details=None):
    specific_code = find_specific_error_code(details)

    if specific_code:
        return specific_code

    default_code = getattr(exception, "default_code", "") or ""
    default_code = default_code.upper()

    if default_code in {"NOT_AUTHENTICATED", "NOTAUTHENTICATED"}:
        return "AUTH_REQUIRED"

    if default_code in {"AUTHENTICATION_FAILED", "INVALID_TOKEN"}:
        return "INVALID_TOKEN"

    if default_code in MESSAGES:
        return default_code

    if response.status_code == 400:
        return "VALIDATION_ERROR"

    return STATUS_CODES.get(response.status_code, "ERROR")


def api_exception_handler(exception, context):
    response = exception_handler(exception, context)

    if response is None:
        return None

    request = context.get("request")
    details = response.data
    code = get_error_code(exception, response, details)
    message = get_message(code, request)

    error = {
        "code": code,
        "message": message,
    }

    if details not in (None, "", {}, []):
        error["details"] = details

    if isinstance(details, dict):
        data = dict(details)
    elif isinstance(details, list):
        data = {"errors": details}
    else:
        data = {}

    data["error"] = error
    data.setdefault("detail", message)

    response.data = data
    return response
