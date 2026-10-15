from io import BytesIO
from uuid import uuid4
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError
from django.core.files.base import ContentFile


MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MAX_IMAGE_DIMENSION = 2000
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}


def process_uploaded_image(uploaded_file):
    """
    Санҷидани тасвири воридшуда ва омода кардани WebP.
    Файли тайёрро ҳамчун ContentFile бармегардонад.
    Ҳангоми хатои санҷиш ValueError медиҳад.
    """
    if uploaded_file.size > MAX_IMAGE_BYTES:
        raise ValueError("Андозаи акс набояд аз 10 MB зиёд бошад.")

    try:
        uploaded_file.seek(0)

        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)

            with Image.open(uploaded_file) as image:
                if image.format not in ALLOWED_IMAGE_FORMATS:
                    raise ValueError(
                        "Танҳо JPEG, PNG ва WebP иҷозатанд."
                    )

                width, height = image.size

                if width * height > MAX_IMAGE_PIXELS:
                    raise ValueError(
                        "Ҳаҷми пикселҳои акс аз ҳад зиёд аст."
                    )

                image.verify()

            uploaded_file.seek(0)

            with Image.open(uploaded_file) as image:
                image = ImageOps.exif_transpose(image)
                image.thumbnail(
                    (MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION),
                    Image.Resampling.LANCZOS,
                )

                # WebP alpha/transparency-ро нигоҳ дошта метавонад.
                if "A" in image.getbands() or "transparency" in image.info:
                    image = image.convert("RGBA")
                else:
                    image = image.convert("RGB")

                output = BytesIO()
                image.save(
                    output,
                    format="WEBP",
                    quality=85,
                    method=6,
                )

        output.seek(0)
        return ContentFile(
            output.read(),
            name=f"{uuid4().hex}.webp",
        )

    except ValueError:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise ValueError("Файли фиристодашуда акси дуруст нест.") from exc
    finally:
        uploaded_file.seek(0)
