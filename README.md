# Hydroflow landing + mini CMS

Flask + SQLite + Gunicorn. Landing page `/`, admin `/admin`.

## Local Docker

```sh
# First installation: copy .env.example to .env and choose strong secrets.
docker compose up -d --build
docker compose ps
```

This deployment uses **127.0.0.1:8091**, Compose project `hydroflow-landing-cms`, and its own named volume `hydroflow-landing-cms_cms_data`. It does not modify other Hydroflow containers or the host reverse proxy. If accessing from a different computer, use an SSH tunnel: `ssh -L 8091:127.0.0.1:8091 arnur@SERVER`, then open http://localhost:8091.

Initial credentials for this installation are in `.admin-credentials` (owner-readable only). Change the password in Admin → Akun. `ADMIN_PASSWORD` seeds the first account only; changing `.env` does not reset an existing account. Keep `.env` and credentials private.

## Content

- Documentation: multi-upload JPG/PNG/WebP, up to 10 MB per photo, 20 photos / 32 MB per request. Files are re-encoded to WebP and resized to at most 1920 px. No fixed gallery photo count. Set caption, numeric order, and visibility per photo; deletion asks for confirmation.
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
docker compose run --rm --no-deps -v "$PWD/tests:/app/tests:ro" cms python -m unittest discover -s tests -v
curl -fsS http://127.0.0.1:8091/healthz
```

The tests use an isolated temporary database; production data is unchanged.
