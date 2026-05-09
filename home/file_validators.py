from pathlib import Path
import io
import logging

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile


logger = logging.getLogger(__name__)


MAX_KYC_DOC_SIZE_BYTES = 5 * 1024 * 1024
MAX_PROFILE_IMAGE_SIZE_BYTES = 5 * 1024 * 1024
MAX_PROPERTY_IMAGE_SIZE_BYTES = 10 * 1024 * 1024
MAX_PROPERTY_VIDEO_SIZE_BYTES = 100 * 1024 * 1024
MAX_IMAGE_WIDTH = 8000
MAX_IMAGE_HEIGHT = 8000
MAX_PDF_PAGE_COUNT = 100
ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi"}
ALLOWED_MIME_BY_EXTENSION = {
    ".pdf": {"application/pdf"},
    ".jpg": {"image/jpeg", "image/jpg", "image/pjpeg"},
    ".jpeg": {"image/jpeg", "image/jpg", "image/pjpeg"},
    ".png": {"image/png", "image/x-png"},
}
ALLOWED_VIDEO_MIME_BY_EXTENSION = {
    ".mp4": {"video/mp4", "application/mp4", "video/quicktime"},
    ".mov": {"video/quicktime", "video/mp4", "application/mp4"},
    ".avi": {
        "video/x-msvideo",
        "video/avi",
        "application/x-troff-msvideo",
        "video/msvideo",
    },
}
PDF_DANGEROUS_NAMES = {
    "/JavaScript",
    "/JS",
    "/AA",
    "/OpenAction",
    "/Launch",
    "/RichMedia",
    "/EmbeddedFile",
    "/EmbeddedFiles",
    "/XFA",
    "/SubmitForm",
    "/ImportData",
}
IMAGE_SIGNATURES = {
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".png": [b"\x89PNG\r\n\x1a\n"],
}
VIDEO_SIGNATURES = {
    ".mp4": [lambda header: len(header) >= 12 and header[4:8] == b"ftyp"],
    ".mov": [lambda header: len(header) >= 12 and header[4:8] == b"ftyp"],
    ".avi": [lambda header: header.startswith(b"RIFF") and b"AVI" in header[8:16]],
}


def _detect_mime(uploaded_file, field_label):
    uploaded_file.seek(0)
    header = uploaded_file.read(4096)
    uploaded_file.seek(0)

    if not header:
        raise ValidationError(f"{field_label} is empty.")

    try:
        import magic
        mime = (magic.from_buffer(header, mime=True) or "").lower().strip()
        if mime:
            return mime
    except Exception:
        pass

    try:
        import filetype

        guessed_mime = filetype.guess_mime(header)
        if guessed_mime:
            return guessed_mime.lower().strip()
    except Exception:
        pass

    if header.startswith(b"%PDF-"):
        return "application/pdf"

    raise ValidationError(
        f"{field_label} type could not be determined securely. Ensure libmagic or filetype is available."
    )


def _validate_mime(uploaded_file, file_extension, field_label):
    allowed_mimes = ALLOWED_MIME_BY_EXTENSION.get(file_extension)
    if not allowed_mimes:
        raise ValidationError(f"{field_label} has an unsupported file type.")

    detected_mime = _detect_mime(uploaded_file, field_label)
    if detected_mime == "application/octet-stream" and file_extension in IMAGE_EXTENSIONS:
        return

    if detected_mime not in allowed_mimes:
        raise ValidationError(f"{field_label} content does not match its file type.")


def _validate_video_mime(uploaded_file, file_extension, field_label):
    allowed_mimes = ALLOWED_VIDEO_MIME_BY_EXTENSION.get(file_extension)
    if not allowed_mimes:
        raise ValidationError(f"{field_label} has an unsupported video type.")

    detected_mime = _detect_mime(uploaded_file, field_label)
    if detected_mime == "application/octet-stream":
        return

    if detected_mime not in allowed_mimes:
        raise ValidationError(f"{field_label} content does not match its file type.")


def _validate_file_signature(uploaded_file, file_extension, field_label):
    uploaded_file.seek(0)
    header = uploaded_file.read(16)
    uploaded_file.seek(0)

    if file_extension == ".pdf" and not header.startswith(b"%PDF-"):
        raise ValidationError(f"{field_label} must be a valid PDF file.")

    if file_extension in IMAGE_SIGNATURES:
        expected_signatures = IMAGE_SIGNATURES[file_extension]
        if not any(header.startswith(sig) for sig in expected_signatures):
            raise ValidationError(f"{field_label} content does not match its file type.")

    if file_extension in VIDEO_SIGNATURES:
        validators = VIDEO_SIGNATURES[file_extension]
        if not any(validate(header) for validate in validators):
            raise ValidationError(f"{field_label} content does not match its file type.")


def _validate_image(uploaded_file, field_label):
    from PIL import Image, UnidentifiedImageError

    uploaded_file.seek(0)
    try:
        image = Image.open(uploaded_file)
        image.verify()
    except (UnidentifiedImageError, OSError):
        raise ValidationError(f"{field_label} is not a valid image file.")
    finally:
        uploaded_file.seek(0)

    uploaded_file.seek(0)
    try:
        image = Image.open(uploaded_file)
        width, height = image.size
        if width > MAX_IMAGE_WIDTH or height > MAX_IMAGE_HEIGHT:
            raise ValidationError(
                f"{field_label} resolution is too large. Maximum allowed is {MAX_IMAGE_WIDTH}x{MAX_IMAGE_HEIGHT}."
            )
    except (UnidentifiedImageError, OSError):
        raise ValidationError(f"{field_label} is not a valid image file.")
    finally:
        uploaded_file.seek(0)


def _scan_pdf_object(obj, visited):
    from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject

    object_id = id(obj)
    if object_id in visited:
        return False
    visited.add(object_id)

    if isinstance(obj, IndirectObject):
        try:
            return _scan_pdf_object(obj.get_object(), visited)
        except Exception:
            return True

    if isinstance(obj, DictionaryObject):
        for key, value in obj.items():
            key_name = str(key)
            if key_name in PDF_DANGEROUS_NAMES:
                return True
            if _scan_pdf_object(value, visited):
                return True
        return False

    if isinstance(obj, ArrayObject):
        for item in obj:
            if _scan_pdf_object(item, visited):
                return True
        return False

    value_text = str(obj)
    return any(marker in value_text for marker in PDF_DANGEROUS_NAMES)


def _validate_pdf(uploaded_file, field_label):
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ValidationError("PDF validation service is unavailable. Please contact support.")

    _validate_file_signature(uploaded_file, ".pdf", field_label)

    uploaded_file.seek(0)
    try:
        reader = PdfReader(uploaded_file, strict=False)
    except Exception:
        uploaded_file.seek(0)
        raise ValidationError(f"{field_label} is corrupted or unreadable.")

    if getattr(reader, "is_encrypted", False):
        uploaded_file.seek(0)
        raise ValidationError(f"Encrypted PDFs are not allowed for {field_label}.")

    try:
        root = reader.trailer.get("/Root")
        if root and _scan_pdf_object(root, set()):
            raise ValidationError(
                f"{field_label} contains active content (JavaScript/actions) and was blocked."
            )

        # Also inspect page-level dictionaries for additional actions.
        if len(reader.pages) > MAX_PDF_PAGE_COUNT:
            raise ValidationError(
                f"{field_label} exceeds the maximum page limit of {MAX_PDF_PAGE_COUNT}."
            )

        for page in reader.pages:
            if _scan_pdf_object(page, set()):
                raise ValidationError(
                    f"{field_label} contains active content (JavaScript/actions) and was blocked."
                )
    finally:
        uploaded_file.seek(0)


def validate_uploaded_kyc_document(uploaded_file, field_label="Document"):
    if not uploaded_file:
        return

    file_extension = Path(uploaded_file.name or "").suffix.lower()
    if file_extension not in ALLOWED_EXTENSIONS:
        raise ValidationError(
            f"{field_label} must be one of: PDF, JPG, JPEG, PNG."
        )

    if uploaded_file.size > MAX_KYC_DOC_SIZE_BYTES:
        raise ValidationError(f"{field_label} must be 5MB or smaller.")

    _validate_mime(uploaded_file, file_extension, field_label)
    _validate_file_signature(uploaded_file, file_extension, field_label)

    if file_extension == ".pdf":
        _validate_pdf(uploaded_file, field_label)
        return

    if file_extension in IMAGE_EXTENSIONS:
        _validate_image(uploaded_file, field_label)


def validate_profile_picture(uploaded_file, field_label="Profile picture"):
    if not uploaded_file:
        return

    file_extension = Path(uploaded_file.name or "").suffix.lower()
    if file_extension not in IMAGE_EXTENSIONS:
        raise ValidationError(f"{field_label} must be JPG, JPEG, or PNG.")

    if uploaded_file.size > MAX_PROFILE_IMAGE_SIZE_BYTES:
        raise ValidationError(f"{field_label} must be 5MB or smaller.")

    _validate_mime(uploaded_file, file_extension, field_label)
    _validate_file_signature(uploaded_file, file_extension, field_label)
    _validate_image(uploaded_file, field_label)


def validate_property_image(uploaded_file, field_label="Property image"):
    if not uploaded_file:
        return

    file_extension = Path(uploaded_file.name or "").suffix.lower()
    if file_extension not in IMAGE_EXTENSIONS:
        raise ValidationError(f"{field_label} must be JPG, JPEG, or PNG.")

    if uploaded_file.size > MAX_PROPERTY_IMAGE_SIZE_BYTES:
        raise ValidationError(f"{field_label} must be 10MB or smaller.")

    _validate_mime(uploaded_file, file_extension, field_label)
    _validate_file_signature(uploaded_file, file_extension, field_label)
    _validate_image(uploaded_file, field_label)


def validate_property_video(uploaded_file, field_label="Property video"):
    if not uploaded_file:
        return

    file_extension = Path(uploaded_file.name or "").suffix.lower()
    if file_extension not in VIDEO_EXTENSIONS:
        raise ValidationError(f"{field_label} must be MP4, MOV, or AVI.")

    if uploaded_file.size > MAX_PROPERTY_VIDEO_SIZE_BYTES:
        raise ValidationError(f"{field_label} must be 100MB or smaller.")

    _validate_video_mime(uploaded_file, file_extension, field_label)
    _validate_file_signature(uploaded_file, file_extension, field_label)


def sanitize_uploaded_image(uploaded_file, field_label="Image"):
    if not uploaded_file:
        return uploaded_file

    from PIL import Image, ImageOps, UnidentifiedImageError

    file_extension = Path(uploaded_file.name or "").suffix.lower()
    if file_extension not in IMAGE_EXTENSIONS:
        return uploaded_file

    uploaded_file.seek(0)
    try:
        image = Image.open(uploaded_file)
        image = ImageOps.exif_transpose(image)

        output_stream = io.BytesIO()
        image_format = "JPEG" if file_extension in {".jpg", ".jpeg"} else "PNG"

        if image_format == "JPEG":
            image = image.convert("RGB")
            image.save(output_stream, format=image_format, quality=90, optimize=True)
        else:
            image.save(output_stream, format=image_format, optimize=True)
    except (UnidentifiedImageError, OSError):
        raise ValidationError(f"{field_label} is not a valid image file.")
    finally:
        uploaded_file.seek(0)

    sanitized_content = ContentFile(output_stream.getvalue())
    sanitized_content.name = uploaded_file.name
    return sanitized_content


def sanitize_uploaded_pdf(uploaded_file, field_label="Document"):
    if not uploaded_file:
        return uploaded_file

    file_extension = Path(uploaded_file.name or "").suffix.lower()
    if file_extension != ".pdf":
        return uploaded_file

    try:
        import pikepdf
    except ImportError:
        return uploaded_file

    uploaded_file.seek(0)
    source_bytes = uploaded_file.read()
    uploaded_file.seek(0)

    if not source_bytes:
        raise ValidationError(f"{field_label} is empty.")

    source_stream = io.BytesIO(source_bytes)
    sanitized_stream = io.BytesIO()

    try:
        with pikepdf.open(source_stream) as pdf:
            pdf.Root.pop("/OpenAction", None)
            pdf.Root.pop("/JavaScript", None)
            pdf.Root.pop("/AcroForm", None)

            for page in pdf.pages:
                page.obj.pop("/AA", None)
                annotations = page.obj.get("/Annots", [])
                for annotation in annotations:
                    annotation_obj = annotation.get_object()
                    if annotation_obj:
                        annotation_obj.pop("/AA", None)
                        action = annotation_obj.get("/A")
                        if action and str(action.get("/S", "")) in {"/JavaScript", "/Launch", "/SubmitForm", "/ImportData"}:
                            annotation_obj.pop("/A", None)

            pdf.save(sanitized_stream)
    except Exception as pike_error:
        logger.warning("Primary PDF sanitization failed for %s: %s", field_label, pike_error)
        try:
            from pypdf import PdfReader, PdfWriter

            source_stream.seek(0)
            reader = PdfReader(source_stream, strict=False)
            writer = PdfWriter()

            for page in reader.pages:
                writer.add_page(page)

            writer.add_metadata({})
            writer.write(sanitized_stream)
        except Exception as fallback_error:
            logger.exception(
                "Fallback PDF sanitization failed for %s: %s",
                field_label,
                fallback_error,
            )
            raise ValidationError(
                f"{field_label} could not be sanitized. Please upload a valid, non-encrypted PDF."
            )

    sanitized_content = ContentFile(sanitized_stream.getvalue())
    sanitized_content.name = uploaded_file.name
    return sanitized_content