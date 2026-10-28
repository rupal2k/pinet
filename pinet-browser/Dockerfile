FROM debian:trixie-slim

# Enable multiarch arm64
RUN dpkg --add-architecture arm64 && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        build-essential \
        pkg-config \
        gcc-aarch64-linux-gnu \
        g++-aarch64-linux-gnu \
        libwebkit2gtk-4.1-dev:arm64 \
        libgtk-3-dev:arm64 \
        libglib2.0-dev:arm64 \
        libcairo2-dev:arm64 \
        libpango1.0-dev:arm64 \
        libgdk-pixbuf-2.0-dev:arm64 \
        libatk1.0-dev:arm64 \
        libssl-dev:arm64 && \
    rm -rf /var/lib/apt/lists/*

# Install Rust toolchain with aarch64 target
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable --target aarch64-unknown-linux-gnu

ENV PATH="/root/.cargo/bin:${PATH}"
ENV PKG_CONFIG_PATH="/usr/lib/aarch64-linux-gnu/pkgconfig:/usr/share/pkgconfig"
ENV PKG_CONFIG_ALLOW_CROSS=1
ENV CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER="aarch64-linux-gnu-gcc"

WORKDIR /src
