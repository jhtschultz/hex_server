# syntax=docker/dockerfile:1
#
# Hex server with Benzene/MoHex engine and HexGUI
#
# Build: gcloud builds submit --tag gcr.io/PROJECT/hex-server --timeout=30m
# Run:   docker run --rm -p 8080:8080 hex-server

FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=en_US.UTF-8 \
    LANGUAGE=en_US:en \
    LC_ALL=en_US.UTF-8 \
    DISPLAY=:0 \
    NOVNC_LISTEN=6080 \
    TTYD_PORT=7681

ARG TTYD_VERSION=1.7.7

# === BASE PACKAGES ===
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        locales \
        xvfb \
        fluxbox \
        x11vnc \
        websockify \
        nginx \
        procps \
        curl \
        ca-certificates \
        git \
        # Build dependencies for Benzene
        build-essential \
        cmake \
        libboost-all-dev \
        libdb-dev \
        # HexGUI dependencies (Java)
        default-jre \
        ant \
    && rm -rf /var/lib/apt/lists/* \
    && sed -i 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen

# Clone noVNC from GitHub (REQUIRED - Debian apt packages have websocket issues)
RUN git clone --depth 1 https://github.com/novnc/noVNC.git /opt/noVNC

# Install ttyd for web terminal at /shell/
RUN arch="$(dpkg --print-architecture)" \
    && case "$arch" in \
        amd64) ttyd_asset="ttyd.x86_64" ;; \
        arm64) ttyd_asset="ttyd.aarch64" ;; \
        *) echo "Unsupported architecture: $arch" && exit 1 ;; \
    esac \
    && curl -L -o /usr/local/bin/ttyd "https://github.com/tsl0922/ttyd/releases/download/${TTYD_VERSION}/${ttyd_asset}" \
    && chmod +x /usr/local/bin/ttyd

# === BUILD BENZENE (MoHex engine) ===
RUN git clone --depth 1 https://github.com/cgao3/benzene-vanilla-cmake.git /opt/benzene \
    && cd /opt/benzene \
    && mkdir build && cd build \
    && cmake ../ \
    && make -j$(nproc)

# === BUILD HEXGUI ===
RUN git clone --depth 1 https://github.com/selinger/hexgui.git /opt/hexgui \
    && cd /opt/hexgui \
    && ant

# === PYTHON DEPENDENCIES (Flask API) ===
RUN pip install --no-cache-dir flask gunicorn

WORKDIR /app

# Copy configuration files
COPY start.sh /app/start.sh
COPY nginx.conf /etc/nginx/nginx.conf
COPY fluxbox.menu /root/.fluxbox/menu
COPY app/ /app/app/

RUN chmod +x /app/start.sh \
    && mkdir -p /root/.fluxbox /var/log/nginx

EXPOSE 8080

ENTRYPOINT ["/app/start.sh"]
