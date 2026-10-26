from core.exceptions import STATUS_CODES, get_message
from core.manual_messages import translate_manual_message


class APIErrorEnvelopeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if not request.path.startswith("/api/"):
            return response

        if response.status_code < 400:
            return response

        data = getattr(response, "data", None)

        if not isinstance(data, (dict, list)):
            return response

        if isinstance(data, dict) and isinstance(data.get("error"), dict):
            return response

        code = STATUS_CODES.get(response.status_code, "ERROR")
        fallback_message = get_message(code, request)
        details = None

        if isinstance(data, list):
            message = fallback_message
            details = data
            payload = {}
        else:
            payload = dict(data)

            if isinstance(payload.get("error"), str):
                message = payload.pop("error")
            elif isinstance(payload.get("detail"), str):
                message = payload["detail"]
            else:
                message = fallback_message
                details = data

        message = translate_manual_message(message, request)

        error = {
            "code": code,
            "message": message,
        }

        if details not in (None, "", {}, []):
            error["details"] = details

        if isinstance(data, list):
            payload["errors"] = data

        payload["error"] = error
        payload.setdefault("detail", message)
        response.data = payload

        if getattr(response, "_is_rendered", False):
            response._is_rendered = False

        response.render()

        return response
