from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_page_size(self, request):
        limit = request.query_params.get("limit")

        if limit not in (None, ""):
            try:
                value = int(limit)
            except (TypeError, ValueError):
                value = 0

            if value > 0:
                return min(value, self.max_page_size)

        return super().get_page_size(request)

    def get_paginated_response(self, data):
        response = super().get_paginated_response(data)
        response.data["items"] = response.data["results"]
        response.data["total"] = response.data["count"]
        response.data["page"] = self.page.number
        response.data["limit"] = self.get_page_size(self.request)
        return response
