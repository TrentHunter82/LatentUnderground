# Latent Underground - Production Deployment Guide

## Quick Start (Docker Compose)

```bash
# 1. Set your API key
export LU_API_KEY="your-secret-api-key"

# 2. Generate self-signed SSL certs (or provide your own)
mkdir -p deploy/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout deploy/ssl/key.pem -out deploy/ssl/cert.pem \
  -subj "/CN=localhost"

# 3. Launch
docker compose -f docker-compose.prod.yml up -d

# 4. Access at https://localhost
```

## Configuration

All settings are controlled via environment variables. Set them in a `.env` file in the project root or pass them to Docker.

| Variable | Default | Description |
|---|---|---|
| `LU_API_KEY` | _(empty = disabled)_ | API key for authentication |
| `LU_HOST` | `127.0.0.1` | Server bind address |
| `LU_PORT` | `8000` | Server port |
| `LU_DB_PATH` | `latent.db` | SQLite database path |
| `LU_LOG_LEVEL` | `info` | Log level (debug/info/warning/error) |
| `LU_LOG_FORMAT` | `text` | Log format (`text` or `json`) |
| `LU_RATE_LIMIT_RPM` | `30` | Max POST requests/minute/client (0 = disabled) |
| `LU_BACKUP_INTERVAL_HOURS` | `0` | Auto-backup interval (0 = disabled) |
| `LU_BACKUP_KEEP` | `5` | Max auto-backups to retain |
| `LU_LOG_RETENTION_DAYS` | `0` | Auto-delete old logs (0 = disabled) |
| `LU_CORS_ORIGINS` | `localhost:5173,8000` | Allowed CORS origins |
| `LU_FRONTEND_DIST` | `../frontend/dist` | Frontend build directory |

### Docker-specific variables

| Variable | Default | Description |
|---|---|---|
| `LU_PUBLIC_PORT` | `443` | External HTTPS port |
| `LU_HTTP_PORT` | `80` | External HTTP port (redirects to HTTPS) |
| `LU_SSL_CERT` | `./deploy/ssl/cert.pem` | Path to SSL certificate |
| `LU_SSL_KEY` | `./deploy/ssl/key.pem` | Path to SSL private key |

## Deployment Options

### Option 1: Docker Compose (Recommended)

Uses `docker-compose.prod.yml` with nginx reverse proxy, SSL, and health checks.

```bash
# Build and start
docker compose -f docker-compose.prod.yml up -d --build

# View logs
docker compose -f docker-compose.prod.yml logs -f latent-underground

# Stop
docker compose -f docker-compose.prod.yml down

# Backup database (manual)
docker compose -f docker-compose.prod.yml exec latent-underground \
  python -c "import sqlite3, sys; c=sqlite3.connect('/app/data/latent.db'); [print(l) for l in c.iterdump()]" > backup.sql
```

### Option 2: Bare Metal with systemd

For Linux servers without Docker.

```bash
# 1. Create service user
sudo useradd -r -s /bin/false latent

# 2. Clone and install
sudo mkdir -p /opt/latent-underground
sudo chown latent:latent /opt/latent-underground
cd /opt/latent-underground
git clone <repo-url> .

# 3. Build frontend
cd frontend
npm ci && npm run build
cd ..

# 4. Set up backend
cd backend
pip install uv
uv sync --no-dev
cp .env.example .env
# Edit .env with your settings

# 5. Install systemd service
sudo cp deploy/latent-underground.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now latent-underground

# 6. Set up nginx (install separately)
sudo cp deploy/nginx.conf /etc/nginx/conf.d/latent-underground.conf
# Edit server_name and SSL paths, then:
sudo nginx -t && sudo systemctl reload nginx
```

### Option 3: Development (Local)

```bash
# Backend
cd backend
uv sync
uv run python run.py

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

## SSL Certificates

### Self-signed (development/testing)

```bash
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout deploy/ssl/key.pem -out deploy/ssl/cert.pem \
  -subj "/CN=your-domain.com"
```

### Let's Encrypt (production)

```bash
# Install certbot
sudo apt install certbot

# Get certificate
sudo certbot certonly --standalone -d your-domain.com

# Update docker-compose.prod.yml volumes:
# - /etc/letsencrypt/live/your-domain.com/fullchain.pem:/etc/nginx/ssl/cert.pem:ro
# - /etc/letsencrypt/live/your-domain.com/privkey.pem:/etc/nginx/ssl/key.pem:ro
```

## Security Checklist

- [ ] Set `LU_API_KEY` to a strong random string
- [ ] Use HTTPS (self-signed minimum, Let's Encrypt for public)
- [ ] Restrict `LU_CORS_ORIGINS` to your actual domain
- [ ] Enable auto-backups (`LU_BACKUP_INTERVAL_HOURS=6`)
- [ ] Enable log retention (`LU_LOG_RETENTION_DAYS=30`)
- [ ] Use JSON logging for log aggregation (`LU_LOG_FORMAT=json`)
- [ ] Run behind a reverse proxy (nginx) - never expose uvicorn directly
- [ ] Use firewall rules to restrict access to trusted IPs

## Monitoring

### Health Check

```bash
curl -s https://localhost/api/health | python -m json.tool
```

Returns `200 OK` with DB status, uptime, and active process count. Returns `503` if the database is unreachable.

### Logs

```bash
# Docker
docker compose -f docker-compose.prod.yml logs -f --tail=100 latent-underground

# systemd
journalctl -u latent-underground -f

# JSON log parsing (when LU_LOG_FORMAT=json)
journalctl -u latent-underground --output=cat | jq .
```

### Database Backup

Auto-backups are stored in `backend/backups/` (or `/app/backend/backups/` in Docker). Manual backup via API:

```bash
curl -H "Authorization: Bearer $LU_API_KEY" https://localhost/api/backup -o backup.sql
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| 401 on all API calls | Missing/wrong API key | Set `Authorization: Bearer <key>` header |
| 503 on health check | Database locked or missing | Check `LU_DB_PATH`, ensure writable |
| WebSocket won't connect | Nginx not upgrading | Verify `/ws` location block in nginx.conf |
| SSE stream hangs | Proxy buffering enabled | Ensure `proxy_buffering off` for SSE routes |
| 429 Too Many Requests | Rate limit hit | Increase `LU_RATE_LIMIT_RPM` or set to 0 |
