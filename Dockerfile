ARG BUILD_FROM=ghcr.io/home-assistant/base:latest

FROM ${BUILD_FROM}

# Build arguments injected by HA Supervisor
ARG BUILD_VERSION
ARG BUILD_ARCH

# Labels required by Home Assistant Add-on standard
LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="addon" \
  io.hass.arch="${BUILD_ARCH}"

# Install Python3, pip, and system dependencies
# HA base image is Alpine Linux - no Python pre-installed
RUN apk add --no-cache \
    python3 \
    py3-pip \
    curl \
    tzdata

WORKDIR /app

# Install Python dependencies into system (not venv) to avoid conflict
COPY requirements.txt /app/
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Copy application source
COPY src/ /app/src/
COPY run.sh /app/
RUN chmod a+x /app/run.sh

EXPOSE 5000

CMD ["/app/run.sh"]
