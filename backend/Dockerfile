# syntax=docker/dockerfile:1
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN --mount=type=secret,id=proxy_ca,target=/run/proxy-ca.pem \
    if [ -f /run/proxy-ca.pem ]; then PIP_CERT=/run/proxy-ca.pem pip install --no-cache-dir -r requirements.txt; else pip install --no-cache-dir -r requirements.txt; fi
RUN useradd --uid 10001 --create-home medflow
COPY --chown=medflow:medflow . .
USER medflow
EXPOSE 8000
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--proxy-headers","--forwarded-allow-ips=10.0.0.0/8"]
