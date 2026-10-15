# Multi-stage image for xcode-api (docs/08-operability.md section 9).
#
# Both stages pin python:3.13-slim-bookworm by the digest of its multi-platform index,
# recorded with its date in deploy/README.md ("Base image digest"); renew both lines and
# that row together. The platform runs the container with a read-only root filesystem and
# /tmp as a tmpfs (docker run --read-only --tmpfs /tmp); nothing here writes elsewhere.

FROM python:3.13-slim-bookworm@sha256:a1165e272e578941b84abc79e4ab38a0305cd12803a5c4247979ac7655f4d641 AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Install the pinned runtime dependencies into a self-contained virtualenv.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.lock.txt ./
RUN pip install -r requirements.lock.txt

# Install the application itself (no dev dependencies).
COPY pyproject.toml requirements.txt README.md ./
COPY src ./src
RUN pip install --no-deps .


FROM python:3.13-slim-bookworm@sha256:a1165e272e578941b84abc79e4ab38a0305cd12803a5c4247979ac7655f4d641 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Non-root user; the root filesystem is mounted read-only by the platform, with /tmp a tmpfs.
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin xcode

COPY --from=builder /opt/venv /opt/venv
# pip is a build tool and nothing installs at runtime; its vendored urllib3, msgpack and pkg_resources are what the
# image scan flags, so neither the venv nor the base image keeps it.
RUN /opt/venv/bin/python -m pip uninstall --yes pip \
    && /usr/local/bin/python -m pip uninstall --yes pip
# The migration runner needs the SQL files at runtime (db migrate/routines/verify).
COPY db /app/db

WORKDIR /app
USER 10001

EXPOSE 5000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5000/health/live', timeout=4).read()==b'Healthy' else 1)"]

ENTRYPOINT ["xcode-api"]
CMD ["serve"]
