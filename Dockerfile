# Official Playwright image: ships Chromium + all required system libraries,
# version-matched to playwright==1.60.0. This avoids having to run
# `playwright install` (and apt-get for deps) on the host, which is not
# feasible on Render's native runtime.
FROM mcr.microsoft.com/playwright/python:v1.60.0-noble

WORKDIR /app

# Refresh the system CA store and pip's bundled CA certs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends --only-upgrade ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir --upgrade "pip>=26.2.2"

# Install Python dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project (includes the cached assets/idols portraits).
COPY . .

CMD ["python", "bot.py"]
