FROM python:3.12-slim-bookworm

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir . \
    && useradd --create-home --uid 1000 app \
    && mkdir -p /var/lib/romini \
    && chown -R app:app /var/lib/romini

ENV ROMINI_PROFILE=demo \
    ROMINI_DATA=/var/lib/romini \
    ROMINI_DASHBOARD_PORT=8080 \
    PYTHONUNBUFFERED=1

USER app
EXPOSE 8080
CMD ["python", "-m", "romini"]
