ARG BUILD_FROM
FROM $BUILD_FROM
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
    TERM="xterm-256color"

# Build arugments
ARG BUILD_DATE
ARG BUILD_REF
ARG BUILD_VERSION
ARG BUILD_REPOSITORY
# Labels
LABEL \
    io.hass.name="Jandy TCX Client Image for ${BUILD_ARCH}" \
    io.hass.description="Jandy TCX Client image for: ${BUILD_ARCH} base image" \
    io.hass.arch="${BUILD_ARCH}" \
    io.hass.type="base" \
    io.hass.version=${BUILD_VERSION} \
    io.hass.base.version=${BUILD_VERSION} \
    io.hass.base.name="homeassistant/${BUILD_ARCH}-base:latest" \
    io.hass.base.image="homeassistant/${BUILD_ARCH}-base" \
    maintainer="Josh Lipton <Josh.Lipton@outlook.com>" \
    org.opencontainers.image.title="Jandy TCX Cliente for ${BUILD_ARCH}" \
    org.opencontainers.image.description="Home Assistant Community Add-on: ${BUILD_ARCH} Base image" \
    org.opencontainers.image.vendor="Josh Lipton" \
    org.opencontainers.image.authors="Josh Lipton <Josh.Lipton@outlook.com>" \
    org.opencontainers.image.licenses="MIT" \
    org.opencontainers.image.url="https://github.com/${BUILD_REPOSITORY}" \
    org.opencontainers.image.source="https://github.com/${BUILD_REPOSITORY}" \
    org.opencontainers.image.documentation="https://github.com/${BUILD_REPOSITORY}/blob/main/README.md" \
    org.opencontainers.image.created=${BUILD_DATE} \
    org.opencontainers.image.revision=${BUILD_REF} \
    org.opencontainers.image.version=${BUILD_VERSION}

ENTRYPOINT ["/init"]
