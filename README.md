# dev-video-feed

Production-ready FastAPI server that normalizes selected technical YouTube RSS feeds into clean JSON for downstream automation.

This service only reads YouTube RSS XML. It does not scrape YouTube HTML and it does not write to Notion.

## Overview

`dev-video-feed` fetches configured YouTube RSS feeds, parses the latest entries, filters out Shorts, streams, clips, VODs, podcasts, and non-video items, deduplicates by video ID and URL, then returns deterministic metadata, topics, priority, score, summary, and practical value notes.

Configured channels:

- Theo / t3.gg
- ThePrimeTime
- ThePrimeagen
- Web Dev Simplified
- Matt Pocock
- Awesome / @awesome-coding
- Syntax

Web Dev Cody is intentionally not included because its channel ID is unverified.

## Architecture

```text
YouTube RSS URLs
      |
      v
async httpx fetcher
      |
      v
defusedxml Atom parser
      |
      v
normalized ParsedVideo models
      |
      +--> missing IDs / channel failures
      |
      v
filtering -> dedupe -> classification -> scoring
      |
      v
FastAPI endpoints: /health, /sample, /feed.json, optional /feed.xml
      |
      v
JSON consumer / automation
```

## Endpoints

- `GET /health`
- `GET /sample`
- `GET /sample?force=true`
- `GET /feed.json`
- `GET /feed.json?force=true`
- `GET /feed.xml`

`force=true` bypasses the in-memory TTL cache. The default cache TTL is 15 minutes.

## Configuration

Copy `.env.example` to `.env` for local shell usage if desired:

```bash
cp .env.example .env
```

Environment variables:

```text
APP_NAME=dev-video-feed
APP_VERSION=0.1.0
CACHE_TTL_SECONDS=900
HTTP_TIMEOUT_SECONDS=15
LOG_LEVEL=INFO
FEED_ENTRIES_PER_CHANNEL=7
```

## Local Development

Use Python 3.12.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Test the app:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/sample
curl http://127.0.0.1:8000/feed.json
```

## Tests

Tests use fixture XML and do not require live YouTube network access.

```bash
pytest
```

## Formatting and Linting

```bash
ruff format .
ruff check .
```

## Docker Compose

The Compose file binds the app to localhost only:

```yaml
127.0.0.1:8000:8000
```

Start the service:

```bash
docker compose up -d --build
docker compose logs -f
```

Check it locally on the host:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/sample
curl http://127.0.0.1:8000/feed.json
```

Do not expose Docker port `8000` publicly. Put Caddy or another reverse proxy in front of it.

## Push to GitHub

From inside this folder:

```bash
git init
git add .
git commit -m "Initial dev video feed service"
git branch -M main
git remote add origin git@github.com:YOUR_USER/dev-video-feed.git
git push -u origin main
```

If this folder is inside an existing repository, add and commit it according to that repository's workflow instead of running `git init`.

## VPS Deployment

On the VPS:

```bash
git clone git@github.com:YOUR_USER/dev-video-feed.git
cd dev-video-feed
docker compose up -d --build
```

Verify the container-bound app:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/sample
curl http://127.0.0.1:8000/feed.json
```

## Reverse Proxy with Caddy

Recommended production setup:

1. Buy or use a domain.
2. Create an A record such as `videos.example.com -> VPS IPv4 address`.
3. Open ports `80` and `443` on the VPS firewall.
4. Do not expose port `8000` publicly.
5. Let Caddy handle HTTPS automatically.

The FastAPI container listens on port `8000`, and Docker Compose binds it to `127.0.0.1:8000:8000`. Caddy runs on the VPS host, not inside this app container.

### Safer Production Caddyfile

Use a long, unguessable path for the private feed endpoint:

```caddyfile
videos.example.com {
    encode gzip

    handle /health {
        reverse_proxy 127.0.0.1:8000
    }

    handle /sample {
        reverse_proxy 127.0.0.1:8000
    }

    handle /dev-video-board-intake-CHANGE-THIS-LONG-RANDOM-TOKEN/feed.json {
        uri strip_prefix /dev-video-board-intake-CHANGE-THIS-LONG-RANDOM-TOKEN
        reverse_proxy 127.0.0.1:8000
    }

    handle {
        respond "Not found" 404
    }
}
```

The long random path is a lightweight security measure for a private feed endpoint. Configure your automation to call the long secret URL. Public `/feed.json` can be enabled temporarily for testing, but it should not be exposed permanently unless protected by a long secret path, authentication, or another access-control layer.

### Simple Testing Caddyfile

This exposes all routes directly and is convenient for a short test:

```caddyfile
videos.example.com {
    encode gzip
    reverse_proxy 127.0.0.1:8000
}
```

### Install Caddy on Ubuntu/Debian

Follow the official installation instructions:

https://caddyserver.com/docs/install#debian-ubuntu-raspbian

After editing `/etc/caddy/Caddyfile`:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
sudo systemctl status caddy
```

Test through Caddy:

```bash
curl https://videos.example.com/health
curl https://videos.example.com/sample
curl https://videos.example.com/dev-video-board-intake-CHANGE-THIS-LONG-RANDOM-TOKEN/feed.json
```

### No-Domain Temporary Option

A real domain is recommended for stable HTTPS and for a durable automation endpoint. For temporary testing, wildcard DNS services such as `sslip.io` or `nip.io` can map a hostname to your VPS IP.

Example hostname for VPS IP `203.0.113.10`:

```text
203-0-113-10.sslip.io
```

Plain HTTP by IP can be acceptable for quick local testing, but it is not recommended for the final automation endpoint.

### Firewall Guidance

Allow SSH, HTTP, and HTTPS. Do not allow public access to port `8000`.

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### Troubleshooting

If HTTPS fails:

- Verify the DNS A record points to the VPS.
- Verify ports `80` and `443` are open.
- Verify Caddy is running.
- Verify the FastAPI app responds locally on `127.0.0.1:8000`.

Logs:

```bash
journalctl -u caddy -f
docker compose logs -f
```

## Notes for Future Extension

Duration and live metadata are intentionally not guessed from RSS. Items currently use `"duration": "Unknown"`. The parsing and classification modules are small pure functions so YouTube Data API metadata can be added later without changing the public JSON shape.

