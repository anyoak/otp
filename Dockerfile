# Use official Python 3.10 slim image
FROM python:3.10-slim

# Install dependencies
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    wget \
    curl \
    unzip \
    fonts-liberation \
    libnss3 \
    libgconf-2-4 \
    libxss1 \
    libasound2 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libpangocairo-1.0-0 \
    libpango-1.0-0 \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables for headless Chrome
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROME_DRIVER=/usr/bin/chromedriver
ENV DISPLAY=:99

# Set working directory
WORKDIR /app

# Copy Python requirements
COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy your code
COPY . .

# Run the main script
CMD ["python", "main.py"]
