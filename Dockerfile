# fin-agent: Python CLI + Bun web server
FROM oven/bun:1.2-debian

# Install Python 3.11 and system dependencies for PDF processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    python3-pip \
    ghostscript \
    libpoppler-cpp-dev \
    poppler-utils \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set Python 3.11 as default
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1 \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

WORKDIR /app

# Copy Python package files and install fin-cli with all optional deps
COPY pyproject.toml README.md LICENSE ./
COPY fin_cli/ ./fin_cli/
RUN pip install --no-cache-dir --break-system-packages '.[all]'

# Copy entrypoint script
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Install Bun dependencies (better layer caching)
COPY package.json bun.lock* ./
RUN bun install --frozen-lockfile

# Copy the rest of the application
COPY . .

# Create data directory structure
RUN mkdir -p /var/data/imports

ENV PORT=3000
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:3000/ || exit 1

ENTRYPOINT ["entrypoint.sh"]
CMD ["bun", "run", "server/server.ts"]
