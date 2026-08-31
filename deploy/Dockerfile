# syntax=docker/dockerfile:1
# D.I.A.N.A. OS - Bare-Metal Node Container Specification
# Runtime: Ollama 0.33.2 + NVIDIA CUDA + Python 3.10 + Z3 SMT Crucible

FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV OLLAMA_VERSION=0.33.2
ENV CUDA_VISIBLE_DEVICES=0
ENV OLLAMA_NUM_PARALLEL=1
ENV OLLAMA_FLASH_ATTENTION=1
ENV OLLAMA_GPU_OVERHEAD=0

# Install base dependencies and Ollama 0.33.2
RUN apt-get update && apt-get install -y \
    curl \
    git \
    python3 \
    python3-pip \
    ca-certificates \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://ollama.com/install.sh | OLLAMA_VERSION=${OLLAMA_VERSION} sh

WORKDIR /app
COPY pyproject.toml .
RUN pip3 install --no-cache-dir \
    pydantic \
    z3-solver \
    pymodbus \
    cryptography \
    requests \
    httpx \
    qdrant-client \
    faster-whisper \
    mss \
    opencv-python-headless \
    pyautogui \
    pytesseract \
    python-telegram-bot

COPY . .

EXPOSE 11434 8501 502

CMD ["/usr/bin/python3", "core/daemon.py"]
