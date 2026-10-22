"""Чтение текста чека на сервере, без внешних API.

PDF-квитанции банков обычно содержат текстовый слой — его читает pypdf. Фото читает Tesseract,
если он установлен на сервере (в Docker-образе есть; на Vercel его нет — там фото читается
на устройстве пользователя и приходит готовым текстом).
"""

import io
import logging
import shutil

log = logging.getLogger(__name__)


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages[:5]).strip()
    except Exception as e:  # битый или зашифрованный PDF
        log.warning("Не удалось прочитать PDF: %s", e)
        return ""


def image_text(content: bytes) -> str:
    if not tesseract_available():
        return ""
    try:
        import pytesseract
        from PIL import Image, ImageOps

        image = ImageOps.grayscale(Image.open(io.BytesIO(content)))
        return pytesseract.image_to_string(image, lang="rus+eng").strip()
    except Exception as e:
        log.warning("Tesseract не смог прочитать изображение: %s", e)
        return ""


def file_text(content: bytes, media_type: str) -> str:
    if media_type == "application/pdf":
        return pdf_text(content)
    return image_text(content)
