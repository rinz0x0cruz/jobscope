FROM node:24-bookworm-slim@sha256:6f7b03f7c2c8e2e784dcf9295400527b9b1270fd37b7e9a7285cf83b6951452d AS web

WORKDIR /src/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN node -e 'require("fs").writeFileSync("/tmp/dashboard.json", JSON.stringify({generated:"container",total:0,rows:[],overview:{funnel:{},gaps:[],considered:0,targets:[]},applications:[],profile:null,applied_outreach:[],companies:[],reviews:[],outreach_snapshot:{read_only:true,campaigns:[],details:[],engagements:[]},activity_audit:{recent_runs:[],selected_run_id:"",decisions:[],recoverable_applications:[]}}))' \
    && JOBSCOPE_DASHBOARD_JSON=/tmp/dashboard.json JOBSCOPE_ENCRYPTED_JSON=none VITE_JOBSCOPE_HOSTED=1 npm run build

FROM python:3.12-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b AS sqlite

ARG SQLITE_ARCHIVE=sqlite-autoconf-3530400.tar.gz
ARG SQLITE_SHA256=0e9483900e92cd5de8fd48d16bf9200145a61f7fd5be542a5ac81d8a9516eb9c
RUN apt-get update \
    && apt-get install --yes --no-install-recommends build-essential ca-certificates curl \
    && curl --fail --location --proto '=https' --tlsv1.2 \
        --output "/tmp/$SQLITE_ARCHIVE" "https://www.sqlite.org/2026/$SQLITE_ARCHIVE" \
    && echo "$SQLITE_SHA256  /tmp/$SQLITE_ARCHIVE" | sha256sum --check --strict \
    && tar --extract --gzip --file "/tmp/$SQLITE_ARCHIVE" --directory /tmp \
    && cd /tmp/sqlite-autoconf-3530400 \
    && ./configure --prefix=/usr/local --disable-static --enable-shared \
    && make --jobs="$(nproc)" \
    && make DESTDIR=/sqlite install

FROM python:3.12-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b

ARG JOBSCOPE_REVISION=unknown
ARG SQLITE_SHA256=0e9483900e92cd5de8fd48d16bf9200145a61f7fd5be542a5ac81d8a9516eb9c
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    JOBSCOPE_ARTIFACT_ID=$JOBSCOPE_REVISION \
    JOBSCOPE_SQLITE_ARCHIVE_SHA256=$SQLITE_SHA256
LABEL org.opencontainers.image.revision=$JOBSCOPE_REVISION \
      org.jobscope.sqlite.archive-sha256=$SQLITE_SHA256
WORKDIR /app

COPY --from=sqlite /sqlite/usr/local/lib/libsqlite3.so* /usr/local/lib/
RUN ldconfig \
    && python -c "import sqlite3; expected='2026-07-24 19:02:57 bf7c7f30031888f4e796e429ab3978879485813aaca6f641c7b33e4e09459bcc'; actual=sqlite3.connect(':memory:').execute('SELECT sqlite_source_id()').fetchone()[0]; assert sqlite3.sqlite_version == '3.53.4', sqlite3.sqlite_version; assert actual == expected, actual"

COPY requirements.lock ./
RUN python -m pip install --no-cache-dir --requirement requirements.lock
COPY jobscope/ ./jobscope/
COPY --from=web /src/web/dist ./web/dist

RUN mkdir -p /data
EXPOSE 8799
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import os,urllib.request; port=os.getenv('PORT','8799'); urllib.request.urlopen(f'http://127.0.0.1:{port}/healthz', timeout=2).close()"]

CMD ["python", "-m", "jobscope", "--config", "/data/config.yaml", "serve", "--hosted"]