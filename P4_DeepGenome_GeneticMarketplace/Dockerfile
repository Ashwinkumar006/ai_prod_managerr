FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN groupadd -r deepgenome && useradd -r -g deepgenome -d /app -s /sbin/nologin deepgenome
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chown -R deepgenome:deepgenome /app
USER deepgenome
EXPOSE 8004
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import httpx; assert httpx.get('http://localhost:8004/docs').status_code==200" || exit 1
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8004"]
