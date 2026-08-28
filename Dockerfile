ARG BUILD_FROM=python:3.10-alpine
FROM $BUILD_FROM

# Set work directory
WORKDIR /app

# Install system dependencies (curl for healthcheck)
RUN apk add --no-cache curl tzdata

# Copy requirements and install
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ /app/src/
COPY run.sh /app/

# Make run script executable
RUN chmod a+x /app/run.sh

# Expose port
EXPOSE 5000

# Run the app
CMD [ "/app/run.sh" ]
