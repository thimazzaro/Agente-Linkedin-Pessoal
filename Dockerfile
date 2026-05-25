# Python 3.12 slim — smaller image, faster Railway deploy
FROM python:3.12-slim

WORKDIR /app

# System fonts required by Pillow for infographic generation
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first (layer cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Railway injects PORT at runtime — do not hardcode it here
EXPOSE 8080

CMD ["python", "main.py"]
