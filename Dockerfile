# ==============================================================================
# Multi-stage Dockerfile for Homebox MCP Server
# Supports: linux/amd64, linux/arm64
# ==============================================================================

# Stage 1: Dependency resolution with uv
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1

# Install runtime dependencies
RUN uv pip install --system fastmcp httpx python-dotenv

# Stage 2: Minimal, secure runtime
FROM python:3.12-slim-bookworm

WORKDIR /app

# Run as non-root user for security
RUN useradd -m -u 1000 appuser

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source code
COPY homebox_mcp.py /app/homebox_mcp.py

ENV PYTHONUNBUFFERED=1
ENV MCP_HOST=0.0.0.0

USER appuser

# Expose port in case SSE transport is used (MCP_TRANSPORT=sse)
EXPOSE 8000

# Default entrypoint runs the MCP server
ENTRYPOINT ["python3", "/app/homebox_mcp.py"]
