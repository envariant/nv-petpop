# syntax=docker/dockerfile:1.7
# API and worker image for every GenAI profile. Python 3.11 so the bpy wheel runs the Blender stages as
# subprocesses of the worker (Cycles on CPU, or CUDA under infra/docker-compose.nvidia.yml).
# Behind a TLS-inspecting proxy, pass its CA bundle as the optional `build_ca` secret
# (PETPOP_BUILD_CA=/path/ca.pem make up); normal hosts leave it empty.
FROM node:22-bookworm-slim AS spa
WORKDIR /src
COPY apps/kiosk/package.json apps/kiosk/package-lock.json apps/kiosk/
RUN --mount=type=secret,id=build_ca \
    if [ -s /run/secrets/build_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/build_ca; fi; \
    cd apps/kiosk && npm ci --no-audit --no-fund
COPY . .
RUN cd apps/kiosk && npm run build

FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgl1 libxi6 libxrender1 libxkbcommon0 libsm6 \
        libxfixes3 libxxf86vm1 libx11-6 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . .
RUN --mount=type=secret,id=build_ca \
    if [ -s /run/secrets/build_ca ]; then export PIP_CERT=/run/secrets/build_ca; fi; \
    pip install --no-cache-dir -e '.[stack]' bpy==5.0.1
COPY --from=spa /src/apps/kiosk/dist apps/kiosk/dist
ENV PETPOP_BPY_PYTHON=/usr/local/bin/python PYTHONPATH=/app PETPOP_VAR=/var/petpop
EXPOSE 8000
CMD ["python", "-m", "backend.api", "--host", "0.0.0.0", "--port", "8000"]
