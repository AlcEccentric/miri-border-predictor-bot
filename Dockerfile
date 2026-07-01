# Official Playwright image: ships Chromium + all required system libraries,
# version-matched to playwright==1.60.0. This avoids having to run
# `playwright install` (and apt-get for deps) on the host, which is not
# feasible on Render's native runtime.
FROM mcr.microsoft.com/playwright/python:v1.60.0-noble

WORKDIR /app

# Install Python dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project (includes the cached assets/idols portraits).
COPY . .

CMD ["python", "bot.py"]
