"""
PDF için Türkçe karakter destekli TrueType font kaydı (ReportLab).
"""

from __future__ import annotations

from pathlib import Path

FONT_REGULAR_NAME = "AppPdfRegular"
FONT_BOLD_NAME = "AppPdfBold"

_REGISTERED = False


def _font_search_paths() -> list[tuple[Path, Path]]:
    """(regular, bold) font dosya çiftleri — öncelik sırasıyla."""
    root = Path(__file__).resolve().parent.parent
    bundled = root / "assets" / "fonts"
    pairs: list[tuple[Path, Path]] = [
        (bundled / "DejaVuSans.ttf", bundled / "DejaVuSans-Bold.ttf"),
        (bundled / "Arial.ttf", bundled / "Arial-Bold.ttf"),
        (
            Path(r"C:\Windows\Fonts\arial.ttf"),
            Path(r"C:\Windows\Fonts\arialbd.ttf"),
        ),
        (
            Path(r"C:\Windows\Fonts\segoeui.ttf"),
            Path(r"C:\Windows\Fonts\segoeuib.ttf"),
        ),
        (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ),
        (
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        ),
        (
            Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        ),
    ]
    return pairs


def ensure_pdf_fonts_registered() -> tuple[str, str]:
    """ReportLab'e UTF-8/Türkçe destekli fontları kaydet."""
    global _REGISTERED
    if _REGISTERED:
        return FONT_REGULAR_NAME, FONT_BOLD_NAME

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    for regular_path, bold_path in _font_search_paths():
        if regular_path.is_file() and bold_path.is_file():
            pdfmetrics.registerFont(TTFont(FONT_REGULAR_NAME, str(regular_path)))
            pdfmetrics.registerFont(TTFont(FONT_BOLD_NAME, str(bold_path)))
            _REGISTERED = True
            return FONT_REGULAR_NAME, FONT_BOLD_NAME

    raise RuntimeError(
        "Türkçe karakter destekli PDF fontu bulunamadı. "
        "backend/assets/fonts/ altına Arial.ttf ve Arial-Bold.ttf ekleyin "
        "veya sunucuya DejaVu Sans kurun."
    )
