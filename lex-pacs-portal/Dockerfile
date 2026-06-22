FROM python:3.12-slim

ARG LEX_PACS_VERSION=0.4.0
ENV LEX_PACS_VERSION=${LEX_PACS_VERSION}

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    freetds-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static

ENV PYTHONUNBUFFERED=1

EXPOSE 8080 2575

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8080/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
