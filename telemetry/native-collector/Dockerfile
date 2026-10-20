FROM debian:bullseye-slim
RUN printf '%s\n' 'deb http://archive.debian.org/debian bullseye main' > /etc/apt/sources.list && \
    printf 'Package: *\nPin: release n=bullseye\nPin-Priority: 1001\n' > /etc/apt/preferences.d/archive && \
    apt-get update -qq && \
    apt-get install -y --allow-downgrades --no-install-recommends libc6 libssl1.1 gcc gcc-arm-linux-gnueabi \
      libc6-dev libc6-dev-armel-cross libcurl4-openssl-dev libssl-dev libjson-c-dev \
      python3 openssl ca-certificates
# Extract the archived ARM development files separately: json-c-dev is not multiarch.
RUN dpkg --add-architecture armel && \
    apt-get update -qq && mkdir /arm-packages /arm && cd /arm-packages && \
    apt-get download libcurl4-openssl-dev:armel libssl-dev:armel libjson-c-dev:armel && \
    for package in *.deb; do dpkg-deb -x "$package" /arm; done && \
    sha256sum *.deb > /arm/build-packages.sha256 && rm -rf /var/lib/apt/lists/* /arm-packages
WORKDIR /src
