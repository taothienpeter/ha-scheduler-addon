ARG BUILD_FROM=ghcr.io/home-assistant/base:latest

FROM ${BUILD_FROM}

ARG BUILD_VERSION
ARG BUILD_ARCH

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="addon" \
  io.hass.arch="${BUILD_ARCH}"

# Install Python3, virtualenv support, and system tools
# NOTE: Python 3.14 on this Alpine is PEP 668 "externally managed"
# We MUST use a venv - do NOT call pip or ensurepip on the system Python
RUN apk add --no-cache \
    python3 \
    py3-virtualenv \
    curl \
    tzdata

# Create virtualenv - pip inside venv is NOT externally managed
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ /app/src/
COPY run.sh /app/
RUN chmod +x /app/run.sh

EXPOSE 5000

CMD ["/app/run.sh"]
