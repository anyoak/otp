FROM python:3.10-alpine

# Install Chromium and ChromeDriver
RUN apk update && apk add --no-cache chromium chromium-chromedriver

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your code
COPY . .

# Start command
CMD ["python", "main.py"]
