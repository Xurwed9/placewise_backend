from io import BytesIO
from uuid import uuid4
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
from django.core.files.base import ContentFile


MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}

THUMBNAIL_SIZE = (400, 400)
LARGE_IMAGE_SIZE = (1200, 1200)


def _open_and_validate(uploaded_file):
    if uploaded_file.size > MAX_IMAGE_BYTES:
        raise ValueError("Андозаи акс набояд аз 10 MB зиёд бошад.")

    uploaded_file.seek(0)

    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)

        with Image.open(uploaded_file) as image:
            if image.format not in ALLOWED_IMAGE_FORMATS:
                raise ValueError("Танҳо JPEG, PNG ва WebP иҷозатанд.")

            width, height = image.size

            if width * height > MAX_IMAGE_PIXELS:
                raise ValueError("Ҳаҷми пикселҳои акс аз ҳад зиёд аст.")

            image.verify()

    uploaded_file.seek(0)

    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)

        with Image.open(uploaded_file) as image:
            image = ImageOps.exif_transpose(image)
            image.load()

            if "A" in image.getbands() or "transparency" in image.info:
                image = image.convert("RGBA")
            else:
                image = image.convert("RGB")

            # Image-и нав metadata-и EXIF-и аслиро нигоҳ намедорад.
            return image.copy()


def _make_webp(image, max_size, filename):
    result = image.copy()
    result.thumbnail(max_size, Image.Resampling.LANCZOS)

    output = BytesIO()
    result.save(output, format="WEBP", quality=85, method=6)
    output.seek(0)

    return ContentFile(output.read(), name=filename)


def process_uploaded_image_variants(uploaded_file):
    """
    Бармегардонад:
      image: тасвири асосӣ, то 1200x1200
      thumbnail: тасвири хурд, то 400x400

    EXIF аз натиҷаҳои WebP нигоҳ дошта намешавад.
    """
    try:
        image = _open_and_validate(uploaded_file)
        unique_id = uuid4().hex

        return {
            "image": _make_webp(
                image,
                LARGE_IMAGE_SIZE,
                f"{unique_id}.webp",
            ),
            "thumbnail": _make_webp(
                image,
                THUMBNAIL_SIZE,
                f"{unique_id}_400.webp",
            ),
        }

    except ValueError:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValueError(
            "Файли фиристодашуда акси дуруст нест."
        ) from exc
    finally:
        uploaded_file.seek(0)


def process_uploaded_image(uploaded_file):
    """
    Мутобиқат бо API-ҳои мавҷуда:
    бармегардонад тасвири асосии WebP то 1200x1200.
    """
    variants = process_uploaded_image_variants(uploaded_file)
    return variants["image"]
