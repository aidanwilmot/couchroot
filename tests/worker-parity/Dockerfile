# Disposable ARM64 test environment; not part of the TV package.
FROM public.ecr.aws/lambda/dotnet:10 AS runtime
FROM debian:bookworm-slim
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    build-essential python3 libjson-c5 libssl3 libicu72 util-linux mount \
    && rm -rf /var/lib/apt/lists/*
COPY --from=runtime /var/lang /opt/dotnet
ENV DOTNET_ROOT=/opt/dotnet
ENV PATH=/opt/dotnet/bin:/opt/dotnet:$PATH
