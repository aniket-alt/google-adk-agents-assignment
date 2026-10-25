# Cloud Run image for the Gemini CLI + ADK agent.
# NOT TESTED: written without a Google Cloud project or Docker available.
# Build from the repository root:  docker build -f b_gemini_cli_agent/Dockerfile -t gemini-cli-agent .
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends git curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/b_gemini_cli_agent
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY b_gemini_cli_agent/package.json b_gemini_cli_agent/package-lock.json ./
RUN npm ci

COPY b_gemini_cli_agent/gemini_cli_agent ./gemini_cli_agent

ENV PORT=8080
# Provide GOOGLE_API_KEY (or Vertex AI settings) as Cloud Run environment variables / secrets.
CMD ["sh", "-c", "adk api_server --host 0.0.0.0 --port ${PORT} ."]
