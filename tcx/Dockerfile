ARG BUILD_FROM
FROM $BUILD_FROM

# Vendor "jandy" package (recovered from the upstream ghcr.io/liptonj/amd64-tcx-client
# base image, which is amd64-only and no longer maintained) plus this add-on's
# Python dependencies. Building them in-tree makes the add-on natively multi-arch.
RUN apk add --no-cache --virtual .build-deps gcc musl-dev libffi-dev openssl-dev

COPY requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt \
    && apk del .build-deps

COPY jandy/ /opt/jandy/

# Local patches on top of the vendored jandy package (secret redaction in logs,
# stale-state refresh fix, CONST module aliasing, credential-safe launcher).
COPY client.py /opt/jandy/client.py
COPY ha_api.py /opt/jandy/ha_api.py
COPY ha_publish.py /opt/jandy/ha_publish.py
COPY zodaic_init.py /opt/jandy/api/zodaic/__init__.py
COPY launcher.py /opt/tcx_launcher.py
COPY run.sh /etc/services.d/tcx-client/run
RUN chmod 755 /etc/services.d/tcx-client/run

# Environment variables
ENV \
    HOME="/root" \
    LANG="C.UTF-8" \
    PS1="$(whoami)@$(hostname):$(pwd)$ " \
    S6_LOGGING=0 \
    S6_BEHAVIOUR_IF_STAGE2_FAILS=0 \
    TERM="xterm-256color" \
    PYTHONPATH="/opt:/opt/jandy:/opt/jandy/api"

# Build arugments
ARG BUILD_DATE
ARG BUILD_REF
ARG BUILD_VERSION
ARG BUILD_REPOSITORY
ARG BUILD_ARCH
# Labels
LABEL \
    io.hass.name="Jandy TCX Client Image for ${BUILD_ARCH}" \
    io.hass.description="Jandy TCX Client image for: ${BUILD_ARCH} base image" \
    io.hass.arch="${BUILD_ARCH}" \
    io.hass.type="addon" \
    io.hass.version=${BUILD_VERSION} \
    maintainer="Matt Vicari <matthewvicari@gmail.com>" \
    org.opencontainers.image.title="Jandy TCX Client for ${BUILD_ARCH}" \
    org.opencontainers.image.description="Jandy TCX Client that publishes native Home Assistant sensors and serves pool controls" \
    org.opencontainers.image.licenses="MIT" \
    org.opencontainers.image.url="https://github.com/${BUILD_REPOSITORY}" \
    org.opencontainers.image.source="https://github.com/${BUILD_REPOSITORY}" \
    org.opencontainers.image.documentation="https://github.com/${BUILD_REPOSITORY}/blob/main/README.md" \
    org.opencontainers.image.created=${BUILD_DATE} \
    org.opencontainers.image.revision=${BUILD_REF} \
    org.opencontainers.image.version=${BUILD_VERSION}

ENTRYPOINT ["/init"]
