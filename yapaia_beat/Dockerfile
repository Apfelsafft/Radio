ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base-debian:bookworm

# --------------------------------------------------------------------------
# Build stage: welle-cli (DAB/DAB+) and redsea (RDS decoder)
# --------------------------------------------------------------------------
FROM ${BUILD_FROM} AS builder

ARG WELLE_VERSION=v2.7
ARG REDSEA_VERSION=v1.3.1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential cmake git pkg-config meson ninja-build ca-certificates xxd \
        librtlsdr-dev libfftw3-dev libfaad-dev libmpg123-dev libmp3lame-dev \
        libsndfile1-dev libliquid-dev nlohmann-json3-dev

RUN git clone --depth 1 --branch "${WELLE_VERSION}" https://github.com/AlbrechtL/welle.io.git /src/welle \
    && cmake -S /src/welle -B /src/welle/build \
        -DCMAKE_BUILD_TYPE=Release \
        -DBUILD_WELLE_IO=OFF \
        -DBUILD_WELLE_CLI=ON \
        -DRTLSDR=ON \
    # generate the embedded web resources ourselves (older xxd lacks "-n")
    && cd /src/welle/build \
    && for res in index.html:index_html index.js:index_js favicon.ico:favicon_ico; do \
        src="/src/welle/src/welle-cli/${res%%:*}"; var="${res##*:}"; \
        { echo "unsigned char ${var}[] = {"; xxd -i < "${src}"; echo "};"; \
          echo "unsigned int ${var}_len = $(stat -c %s "${src}");"; } > "${res%%:*}.h"; \
       done \
    && cmake --build /src/welle/build --target welle-cli -j"$(nproc)" \
    && install -m 0755 /src/welle/build/welle-cli /usr/local/bin/welle-cli

RUN git clone --depth 1 --branch "${REDSEA_VERSION}" https://github.com/windytan/redsea.git /src/redsea \
    && cd /src/redsea \
    && meson setup build --buildtype=release \
    && meson compile -C build \
    && install -m 0755 build/redsea /usr/local/bin/redsea

# --------------------------------------------------------------------------
# Runtime image
# --------------------------------------------------------------------------
FROM ${BUILD_FROM}

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        rtl-sdr librtlsdr0 \
        libfftw3-single3 libfaad2 libmpg123-0 libmp3lame0 libsndfile1 libliquid-dev \
        lame mpg123 pulseaudio-utils \
        python3 python3-numpy python3-scipy python3-aiohttp python3-dnspython \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/bin/welle-cli /usr/local/bin/redsea /usr/local/bin/
# fail early if a shared library is missing
RUN if ldd /usr/local/bin/welle-cli /usr/local/bin/redsea | grep "not found"; then exit 1; fi
COPY rootfs /

ARG BUILD_VERSION=dev
ENV YAPAIA_VERSION=${BUILD_VERSION} \
    YAPAIA_APP=/opt/yapaia \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/yapaia

RUN chmod a+x /etc/s6-overlay/s6-rc.d/yapaia/run /etc/s6-overlay/s6-rc.d/yapaia/finish 2>/dev/null || true \
    && sed -i "s/\"version\": \"[^\"]*\"/\"version\": \"${BUILD_VERSION}\"/" \
        /opt/yapaia/integration/yapaia_beat/manifest.json

LABEL \
    io.hass.name="Yapaia Beat" \
    io.hass.description="FM & DAB+ radio with an RTL-SDR stick" \
    io.hass.type="addon" \
    io.hass.version="${BUILD_VERSION}" \
    org.opencontainers.image.title="Yapaia Beat" \
    org.opencontainers.image.source="https://github.com/apfelsafft/radio" \
    org.opencontainers.image.licenses="MIT"
