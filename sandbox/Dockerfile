FROM python:3.12-slim

RUN useradd --create-home --uid 10001 student
USER student
WORKDIR /workspace
COPY --chown=student:student runner.py /sandbox/runner.py

ENTRYPOINT ["python", "-I", "/sandbox/runner.py"]
