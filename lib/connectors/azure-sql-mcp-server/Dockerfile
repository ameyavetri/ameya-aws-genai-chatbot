# Multi-stage build for Azure SQL MCP Server
# Pin to bookworm so Microsoft repo (debian/12) matches base OS
FROM public.ecr.aws/docker/library/python:3.11-slim-bookworm as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Runtime stage
FROM public.ecr.aws/docker/library/python:3.11-slim-bookworm

WORKDIR /app

# Install runtime dependencies for pyodbc (signed-by keyring; no deprecated apt-key)
# python:3.11-slim is Debian Bookworm (12); use matching Microsoft repo
RUN apt-get update && apt-get install -y --no-install-recommends \
    unixodbc \
    curl \
    gnupg \
    ca-certificates \
    && curl -sSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
    msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY main.py connector.py schema_discovery.py safety.py ./

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Expose port 8080 for HTTP MCP server
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import requests; requests.get('http://localhost:8080/health', timeout=2)" || exit 1

# Run the MCP server
CMD ["python3", "main.py"]
