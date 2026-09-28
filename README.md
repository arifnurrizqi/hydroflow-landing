# Hydroflow landing + mini CMS

Flask + SQLite + Gunicorn. Landing page `/`, admin `/admin`.

## Local development (Windows)

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python run_local.py
```

Open http://127.0.0.1:8091 and http://127.0.0.1:8091/admin.
The development runner generates a persistent secret and initial admin credentials
in `data/local/credentials.json` (ignored by Git). Its SQLite database and uploads
are kept in `data/local`, separate from Docker data. After changing the password
in the CMS, use the new password; the file only records the initial credentials.
Stop with Ctrl+C. This server is for local development.

Run checks with `.\.venv\Scripts\python -m unittest discover -s tests -v`.

## Local Docker

```sh
# First installation: copy .env.example to .env and choose strong secrets.
./scripts/deploy.sh
docker compose ps
```

This deployment uses **127.0.0.1:8091**, Compose project `hydroflow-landing-cms`, and its own named volume `hydroflow-landing-cms_cms_data`. It does not modify other Hydroflow containers or the host reverse proxy. If accessing from a different computer, use an SSH tunnel: `ssh -L 8091:127.0.0.1:8091 arnur@SERVER`, then open http://localhost:8091.

Initial credentials for this installation are in `.admin-credentials` (owner-readable only). Change the password in Admin → Akun. `ADMIN_PASSWORD` seeds the first account only; changing `.env` does not reset an existing account. Keep `.env` and credentials private.

## Content

- Video demo: Admin → Video Demo accepts YouTube watch, youtu.be, Shorts, live, and embed links. Saving shows a responsive YouTube iframe and a hero demo link. Clear the field to hide them. Use a public/unlisted video with embedding enabled. Existing databases receive the empty setting automatically.
- Documentation: multi-upload JPG/PNG/WebP, up to 10 MB per photo, 8 photos / 16 MB per request, with a 12.5-megapixel image limit. Files are re-encoded to WebP and resized to at most 1920 px. No fixed gallery photo count. Set caption, numeric order, and visibility per photo; deletion asks for confirmation.
- Contact: phone, WhatsApp number, email, and initial WhatsApp message update all landing-page contact links.
- Logo: JPG/PNG/WebP uploads update header, dashboard illustration, footer, and favicon. The supplied SVG remains available as the reset default.
- The nine initial Picsum images are placeholders; remove or hide them when real project photos are ready.
- The original `index.html` is retained as a static reference. The live Docker application renders **`templates/landing.html`**.
- SQLite and uploaded media persist in the Docker volume when containers are recreated. Do not use `docker compose down -v` unless you intend to delete all CMS data.
- The existing public design still loads Tailwind and fonts from CDNs; the admin styles are served locally.

## Back up

Stop only this Compose service briefly for a consistent database/media backup:

```sh
mkdir -p backups
docker compose stop cms
docker compose cp cms:/app/data ./backups/cms-data
docker compose start cms
```

Store the backup and `.env` securely. Restore into the service's `/app/data` volume while stopped, preserving ownership UID/GID 10001. A new backup destination is recommended each time.

## Checks

```sh
./scripts/test-arm.sh
curl -fsS http://127.0.0.1:8091/healthz
```

The tests use an isolated temporary database; production data is unchanged.

## Armbian / ARM64 deployment

This repository has been audited for the Cortex-A53 ARM64 host with approximately
1.8 GiB RAM. `compose.yaml` explicitly selects `linux/arm64`, caps the CMS at
256 MiB RAM, disables container swap, limits it to half a CPU and 32 processes,
and serves one request at a time. Uploaded images are resized before EXIF rotation
and large pixel dimensions are rejected before decoding.

The existing native image supplies the pinned Python dependencies. Application
code, templates, static assets, logo, and Gunicorn configuration are mounted
read-only from this repository. Therefore code updates require a container
recreation, **not an image build**. Keep these files in place while the service runs.

```sh
./scripts/preflight.py       # architecture, RAM, disk, temperature, local image
./scripts/test-arm.sh        # offline tests, 256 MiB RAM cap
./scripts/deploy.sh          # no build and no pull
```

`restart: on-failure:3` limits container failure retries. It does not automatically
start the CMS after a host reboot; run `./scripts/deploy.sh` after checking host
health. An already unhealthy host should not be redeployed until investigated.

Do not download Chromium/Playwright or run frontend builds on this 2 GB server.
`/tmp` is tmpfs (RAM-backed) and swap is zram (compressed RAM), not extra disk RAM.
The application's browser animation and YouTube video run in visitors' browsers.

When dependencies change, build an ARM64 image on a separate build machine:

```sh
# Run on a build machine, with ARM64 build support configured there.
docker buildx build --platform linux/arm64 --load -t hydroflow-landing-cms-cms:latest .
docker save -o hydroflow-cms-arm64.tar hydroflow-landing-cms-cms:latest
# Transfer the tar to disk-backed storage on this server, not /tmp.
docker load -i hydroflow-cms-arm64.tar
./scripts/deploy.sh
```

Do not use `compose.build.yaml` on the constrained server. Runtime Compose limits
do not automatically constrain builds or host npm/browser installer processes.
See `audit/ARM-AUDIT.md` for measured results and remaining uncertainty.
