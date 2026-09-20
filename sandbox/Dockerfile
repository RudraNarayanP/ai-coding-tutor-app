FROM python:3.12-slim

# Node.js 22 LTS from NodeSource: --experimental-strip-types (TS erasable
# syntax) landed in Node 22.6 and is absent from Debian's bundled Node 18.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
       | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" \
       > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

RUN rm -f /etc/apt/sources.list.d/nodesource.list

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-jdk-headless \
    g++ \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 student
USER student
WORKDIR /workspace
COPY --chown=student:student runner.py /sandbox/runner.py

ENTRYPOINT ["python", "-I", "/sandbox/runner.py"]
