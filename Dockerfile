ARG BUILD_FROM=python:3.11-alpine

FROM ${BUILD_FROM}

# Build arguments injected by HA CI/Supervisor
ARG BUILD_VERSION
ARG BUILD_ARCH

# Labels required by Home Assistant Add-on standard
LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="addon" \
  io.hass.arch="${BUILD_ARCH}"

# Set timezone support and curl for watchdog healthcheck
RUN apk add --no-cache curl tzdata

WORKDIR /app

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY src/ /app/src/
COPY run.sh /app/
RUN chmod a+x /app/run.sh

EXPOSE 5000

CMD ["/app/run.sh"]
