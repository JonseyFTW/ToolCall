# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies required by Playwright and headless browsers
# These are common for Debian-based systems (like the python:3.10-slim image)
# Also adding build-essential and other common build dependencies for matplotlib if needed from source
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Playwright dependencies
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libgbm1 \
    libgtk-3-0 \
    libasound2 \
    libxshmfence1 \
    # To run browsers in headless mode
    xvfb \
    # Dependencies for matplotlib and other scientific packages if they build from source
    build-essential \
    pkg-config \
    libfreetype6-dev \
    libpng-dev \
    # Clean up
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# This single command will install all dependencies including the pinned playwright version
# and qwen-agent with code_interpreter extras.
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser binaries
# This step can take some time as it downloads browser engines
#RUN playwright install --with-deps
# If you only need a specific browser, e.g., chromium:
RUN playwright install chromium --with-deps

# Copy the rest of the application code into the container at /app
COPY . .

# Make port 5001 available to the world outside this container
EXPOSE 5001

# Define the command to run your app
# Using 0.0.0.0 to ensure it's accessible from outside the container
CMD ["python", "app.py"]