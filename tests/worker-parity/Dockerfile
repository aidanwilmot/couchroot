# Disposable ARM64 test environment; not part of the TV package.
FROM public.ecr.aws/lambda/dotnet:10@sha256:7761b09fd8b72e0225d6ddcb98a19a8f5babf8d434d2ca701ec000499b8b0cf4 AS runtime
FROM node:22-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392 AS protocol
FROM debian:bookworm-slim@sha256:7c7b2c966bc9ee8cedfeef67e0e279108992c77681fa595db4a9d65c06ccc587
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    build-essential python3 libjson-c5 libssl3 libicu72 util-linux mount \
    && rm -rf /var/lib/apt/lists/*
COPY --from=runtime /var/lang /opt/dotnet
COPY --from=protocol /usr/local/bin/node /usr/local/bin/node
ENV DOTNET_ROOT=/opt/dotnet
ENV PATH=/opt/dotnet/bin:/opt/dotnet:$PATH
