# swissco in a container: one CLI, six federal and international data sources.
#
# The build resolves from uv.lock, so an image built today and an image built
# next year from the same commit contain the same dependency versions.

FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first, in their own layer, so editing src/ does not re-resolve
# and re-download the whole tree. mcp/ is a workspace member: uv reads its
# manifest to verify the lock, and never installs it.
COPY pyproject.toml uv.lock README.md ./
COPY mcp/pyproject.toml mcp/README.md ./mcp/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable


FROM python:3.14-slim-bookworm

LABEL org.opencontainers.image.title="swissco" \
      org.opencontainers.image.description="Swiss company data from the shell: Zefix, SHAB, simap, FINMA, GLEIF and ARAMIS in one command" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.source="https://github.com/prospex-ch/swissco-cli" \
      org.opencontainers.image.url="https://prospex.ch" \
      org.opencontainers.image.documentation="https://swissco.readthedocs.io"

# A named user, so the state directory below belongs to somebody and the
# container does not write to bind mounts as root.
RUN useradd --create-home --uid 1000 swissco

COPY --from=builder --chown=swissco:swissco /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

USER swissco
WORKDIR /home/swissco

# Where `watch` keeps its seen-ids and the FINMA files are cached. Mount it to
# keep that across runs: -v swissco-state:/home/swissco/.swissco
VOLUME ["/home/swissco/.swissco"]

ENTRYPOINT ["swissco"]
CMD ["--help"]
