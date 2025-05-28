# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies (minimal, no browser requirements)
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Basic tools
    curl \
    wget \
    ca-certificates \
    # Build tools for some Python packages
    build-essential \
    pkg-config \
    # Image processing libraries for matplotlib (part of qwen-agent)
    libfreetype6-dev \
    libpng-dev \
    # Networking tools for debugging
    iputils-ping \
    # Clean up
    && rm -rf /var/lib/apt/lists/* \
    && apt-get autoremove -y \
    && apt-get autoclean

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install Python packages as root (to avoid permission issues)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Fix matplotlib font permissions issue
RUN python -c "import matplotlib; matplotlib.use('Agg')" || true

# Copy the rest of the application code
COPY . .

# Create non-root user for security
RUN groupadd -r qwen && useradd -r -g qwen -s /bin/false qwen

# Create necessary directories with proper permissions
RUN mkdir -p /home/qwen/.ipython /home/qwen/.jupyter /home/qwen/.cache && \
    chown -R qwen:qwen /home/qwen && \
    chown -R qwen:qwen /app

# Set HOME environment variable
ENV HOME=/home/qwen
ENV MPLCONFIGDIR=/home/qwen/.matplotlib

# Switch to non-root user
USER qwen

# Make port 5001 available to the world outside this container
EXPOSE 5001

# Add a health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:5001/health || exit 1

# Start the application
CMD ["python", "app.py"]