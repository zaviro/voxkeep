FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    libportaudio2 \
    xdotool \
    ydotool \
  && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md /app/
COPY src /app/src
COPY config /app/config
COPY scripts /app/scripts

RUN uv sync --no-dev --group runtime-ai
RUN uv run --python 3.11 python scripts/setup_openwakeword_models.py

CMD ["/bin/sh", "-lc", "if [ -e /dev/uinput ]; then ydotoold --socket-path /tmp/.ydotool_socket & fi; uv run python -m voxkeep --config config/config.yaml"]
