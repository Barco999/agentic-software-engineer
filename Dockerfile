FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
COPY agents agents
COPY llm llm
COPY orchestration orchestration
COPY scenarios scenarios
COPY tests tests
COPY scripts scripts
COPY pyproject.toml .
RUN useradd --create-home service && mkdir /data && chown service:service /data /app
USER service
ENV DATABASE_URL=sqlite:////data/links.db AGENT_DATA_DIR=/data/agentic
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port $PORT"]
