# Group12 Car Rental - complete Flask application from main.
# Build from SourceCode/: docker build -t group12-car-rental:main .
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install the dependencies used by the shared Flask, MySQL and Admin modules.
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 group12 \
    && useradd --uid 10001 --gid group12 --create-home group12

# Package ALL application layers and UI assets. Do not embed .env or test data.
COPY --chown=group12:group12 run.py ./
COPY --chown=group12:group12 business/ ./business/
COPY --chown=group12:group12 data/ ./data/
COPY --chown=group12:group12 presentation/ ./presentation/

USER group12
EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/', timeout=3)" || exit 1

# A stable SECRET_KEY must be supplied at runtime for multi-worker sessions.
# Gunicorn runs production mode. Student Payment Demo remains local Flask only.
CMD ["sh", "-c", "test -n \"$SECRET_KEY\" || { echo 'ERROR: Set SECRET_KEY with --env-file .env' >&2; exit 1; }; exec gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 60 --access-logfile - --error-logfile - run:app"]
