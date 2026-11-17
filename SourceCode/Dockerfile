# Group12 Car Rental - Flask application
# Run docker build from the SourceCode directory.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Explicit copies: do not include .env or other local secrets in the image.
COPY run.py ./
COPY business/ ./business/
COPY data/ ./data/
COPY presentation/ ./presentation/

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "run:app"]
