FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    CBCS_RUNTIME_PINS=/opt/cbcs/cloud_runtime_pins.env \
    CBCS_DOWNLOAD_CACHE=/var/cache/cbcs \
    FREECAD_APPRUN=/opt/freecad/AppRun \
    CBCS_FB_APPRUN_11=/opt/freecad-1.1/AppRun \
    CBCS_FB_PY311=/usr/local/bin/cbcs-fb-python \
    CBCS_FB_PY39=/home/ubuntu/opt/freecad/bin/python \
    CBCS_FB_UIC=/usr/local/bin/cbcs-fb-uic \
    CBCS_FB_RCC=/usr/local/bin/cbcs-fb-rcc \
    CBCS_ARTIFACTS_DIR=/home/ubuntu/cbcs_artifacts \
    npm_config_yes=true \
    DISPLAY=:1

RUN if ! id ubuntu >/dev/null 2>&1; then \
      useradd --create-home --shell /bin/bash --uid 1000 ubuntu; \
    fi

COPY scripts/cloud_runtime_pins.env \
     scripts/cloud_runtime_lib.sh \
     scripts/cloud_install_apt.sh \
     scripts/cloud_install_node.sh \
     scripts/cloud_bake_runtimes.sh \
     scripts/setup_freecad_dev.sh \
     /opt/cbcs/

RUN bash /opt/cbcs/cloud_install_apt.sh \
    && echo 'ubuntu ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/ubuntu \
    && chmod 440 /etc/sudoers.d/ubuntu \
    && bash /opt/cbcs/cloud_install_node.sh \
    && bash /opt/cbcs/cloud_bake_runtimes.sh \
    && rm -rf /var/lib/apt/lists/* /root/.cache

USER ubuntu
