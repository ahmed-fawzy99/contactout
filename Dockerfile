FROM python:3.9-slim

# Install system dependencies required for Playwright
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    libgconf-2-4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libexpat1 \
    libxcb1 \
    libxkbcommon0 \
    libx11-6 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2 \
    libnspr4 \
    libnss3 \
    fonts-liberation \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install --with-deps
# If you need other browsers, uncomment these lines:

# Copy application code
COPY . .

# Run with xvfb-run if you need a virtual display
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "app:app"]