FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY leadscout ./leadscout

RUN useradd --system --uid 10001 --home /srv leadscout && mkdir -p /data && chown leadscout /data
USER leadscout

# api:    uvicorn leadscout.api:app
# worker: python -m leadscout.worker
CMD ["python", "-m", "leadscout.worker"]
