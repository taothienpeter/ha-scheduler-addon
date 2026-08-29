ARG BUILD_FROM=ghcr.io/home-assistant/base:latest

FROM ${BUILD_FROM}

ARG BUILD_VERSION
ARG BUILD_ARCH

LABEL \
  io.hass.version="${BUILD_VERSION}" \
  io.hass.type="addon" \
  io.hass.arch="${BUILD_ARCH}"

# Install Python3 and venv support from Alpine apk
RUN apk add --no-cache python3 py3-virtualenv curl tzdata

# Create a virtual environment - cleanest way to install pip packages on Alpine
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Install Python dependencies inside venv
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY src/ /app/src/
COPY run.sh /app/
RUN chmod +x /app/run.sh

EXPOSE 5000

CMD ["/app/run.sh"]
