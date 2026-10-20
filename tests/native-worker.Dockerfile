# Host-only native regression fixtures; separate from the pinned TV toolchain.
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    gcc libc6-dev libjson-c5 openssl procps util-linux && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /src
