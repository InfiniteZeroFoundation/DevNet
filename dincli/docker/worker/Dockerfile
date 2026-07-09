FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN python -m pip install --upgrade pip

# rich is the only base dependency the worker entrypoint and model-owner
# services can rely on out of the box (for console output); everything else
# is whatever the model owner pins in their manifest requirements.txt,
# installed separately by dincli into a mounted packages directory.
RUN pip install --no-cache-dir rich

COPY dincli/docker/worker/worker.py /usr/local/bin/din-worker
RUN chmod +x /usr/local/bin/din-worker

WORKDIR /din

ENTRYPOINT ["din-worker"]
