# API and worker image (GPU host). Python 3.11 so the bpy wheel runs the Blender stages in-process
# subprocesses of the worker (Cycles on CUDA through the NVIDIA runtime).
FROM node:22-bookworm-slim AS spa
WORKDIR /src
COPY apps/kiosk/package.json apps/kiosk/package-lock.json apps/kiosk/
RUN cd apps/kiosk && npm ci --no-audit --no-fund
COPY . .
RUN cd apps/kiosk && npm run build

FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgl1 libxi6 libxrender1 libxkbcommon0 libsm6 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml ./
COPY . .
RUN pip install --no-cache-dir -e '.[gpu-host]' bpy==4.2.0
COPY --from=spa /src/apps/kiosk/dist apps/kiosk/dist
ENV PETPOP_MODE=real PETPOP_BPY_PYTHON=/usr/local/bin/python PYTHONPATH=/app PETPOP_VAR=/var/petpop
EXPOSE 8000
CMD ["python", "-m", "backend.api", "--host", "0.0.0.0", "--port", "8000"]
