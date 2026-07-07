FROM python:3.12-slim

# ============================================
# Environment Variables
# ============================================

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

# ============================================
# Working Directory
# ============================================

WORKDIR /app

# ============================================
# Install System Dependencies
# ============================================

RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    libpq-dev \
    pkg-config \
    curl \
    libffi-dev \
    libssl-dev \
    libjpeg-dev \
    zlib1g-dev \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# ============================================
# Install Python Dependencies
# ============================================

COPY requirements.txt .

RUN pip install --upgrade pip

RUN pip install --no-cache-dir -r requirements.txt

# ============================================
# Copy Project
# ============================================

COPY . .

# ============================================
# Create Required Directories
# ============================================

RUN mkdir -p logs
RUN mkdir -p staticfiles
RUN mkdir -p media

# ============================================
# Make Entrypoint Executable
# ============================================

RUN chmod +x docker-entrypoint.sh

# ============================================
# Expose Port
# ============================================

EXPOSE 8000

# ============================================
# Entrypoint
# ============================================

ENTRYPOINT ["./docker-entrypoint.sh"]

# ============================================
# Default Command
# ============================================

CMD ["gunicorn", "peopleskilltrainingapp.wsgi:application", "-c", "gunicorn.conf.py"]