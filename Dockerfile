FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir --default-timeout=120 \
    fastapi>=0.111 "uvicorn[standard]>=0.29" aiohttp>=3.9 pydantic>=2.0

COPY app/ ./app/

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
