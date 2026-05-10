FROM python:3.12-slim AS builder

WORKDIR /build
COPY proxy/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---

FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY proxy/deepseek-thinking-proxy.py .

EXPOSE 16889

ENV PROXY_HOST=0.0.0.0
ENV PROXY_PORT=16889

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:16889/health')" || exit 1

CMD ["python3", "deepseek-thinking-proxy.py"]
