# Space Exploration Channel - Multi-stage Docker Build
# Stage 1: Base with system dependencies
FROM nvidia/cuda:12.2-devel-ubuntu22.04 AS base

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv python3-dev \
    git curl wget unzip \
    ffmpeg \
    blender \
    libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender-dev libgomp1 \
    build-essential \
    redis-tools \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -s /bin/bash spacebot && \
    usermod -aG video,render spacebot

WORKDIR /app

# Stage 2: Python dependencies
FROM base AS python-deps

COPY requirements.txt .
RUN python3 -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip setuptools wheel && \
    /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# Stage 3: RIFE model and binary
FROM base AS rife

RUN mkdir -p /opt/models/rife /opt/bin && \
    wget -q "https://github.com/hzwer/arXiv2020-RIFE/releases/download/v4.6/rife-v4.6.pth" \
    -O /opt/models/rife/rife-v4.6.pth && \
    RIFE_VERSION="20231029-ubuntu" && \
    wget -q "https://github.com/nihui/rife-ncnn-vulkan/releases/download/$RIFE_VERSION/rife-ncnn-vulkan-$RIFE_VERSION.zip" \
    -O /tmp/rife.zip && \
    unzip -q /tmp/rife.zip -d /opt/bin && \
    chmod +x /opt/bin/rife-ncnn-vulkan && \
    rm /tmp/rife.zip

# Stage 4: Application
FROM base AS app

# Copy Python environment
COPY --from=python-deps /opt/venv /opt/venv

# Copy RIFE
COPY --from=rife /opt/models /opt/models
COPY --from=rife /opt/bin /opt/bin

# Set PATH
ENV PATH="/opt/venv/bin:/opt/bin:/usr/local/bin:/usr/bin:/bin"

# Copy application code
COPY --chown=spacebot:spacebot . /app

# Create directories
RUN mkdir -p /app/assets/nasa /app/assets/branding /app/output /app/logs /app/cache /app/scripts /app/templates/blender /app/templates/davinci /app/config /app/state /app/backups && \
    chown -R spacebot:spacebot /app

# Copy config template
RUN cp /app/config/orchestrator.yaml.example /app/config/orchestrator.yaml

# Switch to non-root user
USER spacebot

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import skills; print('OK')" || exit 1

# Default command
CMD ["python", "-m", "skills.orchestrator", "continuous"]