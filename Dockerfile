ARG BUILD_FROM=ghcr.io/home-assistant/base:latest

FROM ${BUILD_FROM}

ARG BUILD_VERSION
ARG BUILD_ARCH

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="addon" \
  io.hass.arch="${BUILD_ARCH}"

# Install Python3, virtualenv, curl for healthcheck
RUN apk add --no-cache \
    python3 \
    py3-virtualenv \
    curl \
    tzdata

# Create virtualenv — avoids PEP 668 on Python 3.14
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ /app/src/
COPY run.sh /app/run.sh
RUN chmod +x /app/run.sh

EXPOSE 5000

# init: false in config.json means HA Supervisor runs CMD directly (no s6-overlay)
CMD ["/app/run.sh"]
