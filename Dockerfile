ARG BUILD_FROM=ghcr.io/home-assistant/base:latest

FROM ${BUILD_FROM}

ARG BUILD_VERSION
ARG BUILD_ARCH

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="addon" \
  io.hass.arch="${BUILD_ARCH}"

# Install Python3 and virtualenv
RUN apk add --no-cache \
    python3 \
    py3-virtualenv \
    curl \
    tzdata

# Create virtualenv — avoids PEP 668 restriction on system Python
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ /app/src/

# s6-overlay service setup:
# HA base image uses s6-overlay as init — services must be in /etc/services.d/
COPY run.sh /etc/services.d/scheduler/run
RUN chmod a+x /etc/services.d/scheduler/run

EXPOSE 5000
