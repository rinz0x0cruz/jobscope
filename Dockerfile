FROM node:24-bookworm-slim@sha256:6f7b03f7c2c8e2e784dcf9295400527b9b1270fd37b7e9a7285cf83b6951452d AS web

WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN node -e 'require("fs").writeFileSync("/tmp/dashboard.json", JSON.stringify({generated:"container",total:0,rows:[],overview:{funnel:{},gaps:[],considered:0,targets:[]},applications:[],profile:null,applied_outreach:[],companies:[],reviews:[],activity_audit:{recent_runs:[],selected_run_id:"",decisions:[],recoverable_applications:[]}}))' \
    && JOBSCOPE_DASHBOARD_JSON=/tmp/dashboard.json JOBSCOPE_ENCRYPTED_JSON=none VITE_JOBSCOPE_HOSTED=1 npm run build

FROM python:3.12-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.lock ./
RUN python -m pip install --no-cache-dir --requirement requirements.lock
COPY jobscope/ ./jobscope/
COPY --from=web /src/web/dist ./web/dist

RUN mkdir -p /data
EXPOSE 8799
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import os,urllib.request; port=os.getenv('PORT','8799'); urllib.request.urlopen(f'http://127.0.0.1:{port}/healthz', timeout=2).close()"]

CMD ["python", "-m", "jobscope", "--config", "/data/config.yaml", "serve", "--hosted"]