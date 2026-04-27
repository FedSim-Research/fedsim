FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
RUN rm -f /etc/apt/sources.list.d/cuda.list && \
    apt-key del 7fa2af80 && \
    apt-get update && apt-get install -y --no-install-recommends wget && \
    wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb && \
    dpkg -i cuda-keyring_1.1-1_all.deb && \
    apt-get update \
    && apt-get install -y --no-install-recommends software-properties-common curl \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends python3.12 python3.12-dev build-essential \
    && ln -sf /usr/bin/python3.12 /usr/bin/python \
    && ln -sf /usr/bin/python3.12 /usr/bin/python3 \
    && curl -sS https://bootstrap.pypa.io/get-pip.py | python3.12 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt /app/requirements.txt
COPY framework/impl /app/framework/impl

RUN pip install --no-cache-dir -r /app/requirements.txt

COPY backend /app/backend

EXPOSE 8000
