# The Linux machine coganchor's port is tested on from a Mac: Rust, uv and Python 3.12, and
# zig for the static musl builds. Run through linux-test.sh, which mounts the checkout at /src.
FROM rust:1-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl git sqlite3 xz-utils \
 && rm -rf /var/lib/apt/lists/*

# uv, which brings the Python the tests run under.
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /uvx /usr/local/bin/
ENV UV_PYTHON=3.12 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/venv \
    CARGO_TARGET_DIR=/target \
    PATH=/venv/bin:$PATH
RUN uv python install 3.12

RUN rustup component add clippy rustfmt \
 && rustup target add x86_64-unknown-linux-musl aarch64-unknown-linux-musl

# A non-root user, as the suites assume: ptrace, Landlock and the fence all behave differently
# for root.
RUN useradd --create-home --uid 1000 dev \
 && mkdir -p /venv /target /usr/local/cargo/registry \
 && chown dev /venv /target /usr/local/cargo -R
USER dev
WORKDIR /src
