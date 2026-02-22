FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
COPY framework/impl /app/framework/impl

RUN pip install --no-cache-dir -r /app/requirements.txt

COPY backend /app/backend

EXPOSE 8000
