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

# Install Python3, pip, and system deps on HA Alpine base image
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-setuptools \
    curl \
    tzdata && \
    python3 -m ensurepip --upgrade && \
    python3 -m pip install --no-cache-dir --upgrade pip

WORKDIR /app

# Install Python dependencies
COPY requirements.txt /app/
RUN python3 -m pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY src/ /app/src/
COPY run.sh /app/
RUN chmod a+x /app/run.sh

EXPOSE 5000

CMD ["/app/run.sh"]
