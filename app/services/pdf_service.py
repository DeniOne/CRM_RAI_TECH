"""PDF-рендер печатных форм (WeasyPrint, фаза 19).

WeasyPrint требует системные pango/harfbuzz + шрифты — они ставятся в
Dockerfile (Linux-контейнер прода). На Windows-дев машине без GTK импорт
падает — ловим и отдаём PDFUnavailable, роут отвечает мягким 503.
"""

class PDFUnavailable(RuntimeError):
    pass


def render_pdf(html: str) -> bytes:
    try:
        from weasyprint import HTML
    except Exception as e:  # ImportError/OSError — нет GTK/pango
        raise PDFUnavailable(f"WeasyPrint недоступен: {e}") from e
    return HTML(string=html, base_url=".").write_pdf()
