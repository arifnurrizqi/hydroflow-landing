FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/app/data
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home cms && mkdir /app/data && chown cms:cms /app/data
COPY --chown=cms:cms app.py index.html logo-hsm.svg ./
COPY --chown=cms:cms templates ./templates
COPY --chown=cms:cms static ./static
USER cms
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "--timeout", "60", "--access-logfile", "-", "app:app"]
