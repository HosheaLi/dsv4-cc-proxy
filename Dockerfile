FROM python:3.12-slim AS builder

WORKDIR /build
COPY . .
RUN pip install --no-cache-dir build && python -m build --wheel

# ---

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /build/dist/*.whl .
RUN pip install --no-cache-dir *.whl && rm *.whl

EXPOSE 16889

ENV PROXY_HOST=0.0.0.0
ENV PROXY_PORT=16889

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:16889/health')" || exit 1

CMD ["dsv4-cc-proxy"]
