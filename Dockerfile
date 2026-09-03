FROM python:3.11-slim

WORKDIR /app

# WeasyPrint (печать КП/счетов, фаза 19): pango+harfbuzz обязательны, иначе
# импорт падает; fonts-dejavu — иначе кириллица в PDF рендерится квадратами.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 libxslt1.1 \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
    shared-mime-info fonts-dejavu-core fontconfig \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p storage/documents templates_docx

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
