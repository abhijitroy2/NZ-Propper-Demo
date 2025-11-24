FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libatspi2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libwayland-client0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies (build context is repo root, Dockerfile is in backend/)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (deps already installed above)
RUN playwright install chromium

# Copy application code (build context is repo root, Dockerfile is in backend/)
COPY backend/app/ ./app/

# Create logs directory
RUN mkdir -p logs

# Expose port (Railway will set PORT env var)
EXPOSE 8000

# Run the application (use PORT env var from Railway)
# Railway sets PORT automatically, default to 8000 if not set
CMD sh -c "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"


