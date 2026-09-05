FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    GRADIO_ANALYTICS_ENABLED=False \
    HUNYUAN_WEB_DATA_DIR=/data \
    HUNYUAN_INITIAL_PASSWORD=change-this-password

WORKDIR /app

COPY requirements-local.txt ./
RUN pip install --no-cache-dir -r requirements-local.txt

COPY local_web.py vue_web.py ./
COPY web-dist ./web-dist

VOLUME ["/data"]
EXPOSE 7864

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7864/login', timeout=3)"

CMD ["python", "vue_web.py"]
