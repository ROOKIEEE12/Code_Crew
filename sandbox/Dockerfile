# Image used when SANDBOX=docker. Build once:
#   docker build -t codecrew-sandbox sandbox
FROM python:3.12-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir pytest
RUN useradd -m runner
USER runner
WORKDIR /work
