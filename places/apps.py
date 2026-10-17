from django.apps import AppConfig


class PlacesConfig(AppConfig):
    name = "places"

    def ready(self):
        import places.signals