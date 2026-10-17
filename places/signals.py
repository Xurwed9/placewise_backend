from django.core.cache import cache
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from places.models import Place, Category, PlacePhoto


def invalidate_public_api_cache():
    """
    Танҳо версияи кэши API-и оммавиро нав мекунад.
    Кэши throttle-ро тоза намекунад.
    """
    cache.add("public-api-version", 1, timeout=None)
    cache.incr("public-api-version")


@receiver(post_save, sender=Place)
@receiver(post_delete, sender=Place)
def invalidate_cache_on_place_change(sender, **kwargs):
    invalidate_public_api_cache()


@receiver(post_save, sender=Category)
@receiver(post_delete, sender=Category)
def invalidate_cache_on_category_change(sender, **kwargs):
    invalidate_public_api_cache()


@receiver(post_save, sender=PlacePhoto)
@receiver(post_delete, sender=PlacePhoto)
def invalidate_cache_on_photo_change(sender, **kwargs):
    invalidate_public_api_cache()