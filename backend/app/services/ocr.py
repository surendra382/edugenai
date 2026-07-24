from pathlib import Path
from typing import Protocol

import pytesseract
from PIL import Image
from pdf2image import convert_from_path


class OCRProvider(Protocol):
    def extract_text(self, file_path: Path, file_type: str) -> str: ...


class TesseractOCRProvider:
    """Default OCR engine: PaddleOCR is the SRS's other named option but is a
    much heavier dependency (deep-learning framework + model downloads);
    Tesseract is already available on this machine and sits behind the same
    OCRProvider interface, so swapping in PaddleOCR later needs no changes
    outside this class.
    """

    def extract_text(self, file_path: Path, file_type: str) -> str:
        if file_type == "image":
            return pytesseract.image_to_string(Image.open(file_path))
        if file_type == "pdf":
            pages = convert_from_path(str(file_path))
            return "\n".join(pytesseract.image_to_string(page) for page in pages)
        raise ValueError(f"Unsupported file_type for OCR: {file_type}")


ocr_provider: OCRProvider = TesseractOCRProvider()
