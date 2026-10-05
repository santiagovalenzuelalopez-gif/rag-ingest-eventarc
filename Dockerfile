# ---- Build ----
FROM python:3.11-slim AS builder
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
# Por defecto solo el núcleo (modo memoria). Producción: --build-arg REQUIREMENTS=requirements-gcp.txt
ARG REQUIREMENTS=requirements.txt
COPY requirements.txt requirements-gcp.txt ./
RUN pip install --no-cache-dir --user -r ${REQUIREMENTS}

# ---- Runtime ----
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH=/home/appuser/.local/bin:$PATH PORT=8080
RUN useradd --create-home --uid 1000 appuser
WORKDIR /app
COPY --from=builder /root/.local /home/appuser/.local
COPY --chown=appuser:appuser app ./app
USER appuser
# Servicio interno (solo Eventarc), sin tráfico público: un worker alcanza.
CMD exec gunicorn --bind :$PORT --workers 1 --worker-class uvicorn.workers.UvicornWorker --timeout 0 app.main:app
