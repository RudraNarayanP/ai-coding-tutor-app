FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    default-jdk-headless \
    g++ \
    build-essential \
    && rm -rf /var/lib/apt-get/lists/*

RUN useradd --create-home --uid 10001 student
USER student
WORKDIR /workspace
COPY --chown=student:student runner.py /sandbox/runner.py

ENTRYPOINT ["python", "-I", "/sandbox/runner.py"]
