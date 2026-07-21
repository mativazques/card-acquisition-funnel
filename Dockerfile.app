# Streamlit cockpit — the public demo (funnel + vintage curves + heatmap + insight panel).
# Python 3.9 (streamlit pins protobuf<6). Reads only the aggregated marts via ADC; its
# "Ask the copilot" tab calls the separate copilot API by URL (COPILOT_API_URL).
# Multi-stage: deps compile in the builder venv, only the venv + app code ship.

FROM python:3.9-slim AS builder
WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY app/requirements.txt ./app/requirements.txt
RUN pip install --no-cache-dir -r app/requirements.txt

FROM python:3.9-slim
WORKDIR /app
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
COPY --from=builder /opt/venv /opt/venv
# The app imports the same governed semantic layer BI and the agents share.
COPY app/ ./app/
COPY semantic/ ./semantic/
EXPOSE 8080
# Cloud Run injects $PORT. Headless: no browser auto-open, no usage stats prompt.
CMD exec streamlit run app/main.py \
    --server.port=${PORT:-8080} \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --browser.gatherUsageStats=false
