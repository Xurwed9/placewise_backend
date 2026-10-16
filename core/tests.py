
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from PIL import Image

from core.image_processing import process_uploaded_image


def make_image(
    image_format="JPEG",
    size=(100, 80),
    color="red",
):
    buffer = BytesIO()
    image = Image.new("RGB", size, color=color)
    image.save(buffer, format=image_format)

    return SimpleUploadedFile(
        "test-image." + image_format.lower(),
        buffer.getvalue(),
        content_type="image/" + image_format.lower(),
    )


class ImageProcessingTests(SimpleTestCase):
    def test_jpeg_is_converted_to_webp(self):
        uploaded = make_image("JPEG")

        result = process_uploaded_image(uploaded)

        self.assertTrue(result.name.endswith(".webp"))

        with Image.open(result) as image:
            self.assertEqual(image.format, "WEBP")
            self.assertEqual(image.size, (100, 80))

    def test_png_is_converted_to_webp(self):
        uploaded = make_image("PNG")

        result = process_uploaded_image(uploaded)

        with Image.open(result) as image:
            self.assertEqual(image.format, "WEBP")

    def test_large_dimensions_are_reduced(self):
        uploaded = make_image(
            "JPEG",
            size=(3000, 1500),
        )

        result = process_uploaded_image(uploaded)

        with Image.open(result) as image:
            self.assertEqual(image.format, "WEBP")
            self.assertEqual(image.size, (1200, 600))

    def test_invalid_file_is_rejected(self):
        uploaded = SimpleUploadedFile(
            "not-image.jpg",
            b"this is not an image",
            content_type="image/jpeg",
        )

        with self.assertRaises(ValueError):
            process_uploaded_image(uploaded)

    def test_svg_or_other_format_is_rejected(self):
        uploaded = make_image("GIF")

        with self.assertRaises(ValueError):
            process_uploaded_image(uploaded)

    def test_file_over_10mb_is_rejected(self):
        uploaded = SimpleUploadedFile(
            "large.jpg",
            b"x" * (10 * 1024 * 1024 + 1),
            content_type="image/jpeg",
        )

        with self.assertRaises(ValueError):
            process_uploaded_image(uploaded)
