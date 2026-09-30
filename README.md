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

## SEO and search indexing

The live page renders its title, Indonesian description, canonical URL, Open Graph /
Twitter metadata, and Organization/WebSite/WebPage/Service JSON-LD on the server.
Structured contact data and uploaded-logo references follow CMS settings. The
public origin defaults to `https://hydroflow.arnur.id` and can be configured with
`PUBLIC_SITE_URL`; incoming Host headers and tracking queries do not alter it.

- `/sitemap.xml` lists only the canonical public landing page.
- `/robots.txt` allows crawling and advertises the sitemap.
- Every `/admin` response, including redirects and errors, sends
  `X-Robots-Tag: noindex, nofollow`; admin HTML also has a noindex meta tag.
- Admin content and operations still require login. No admin links appear in the
  public landing page or sitemap. `noindex` controls search visibility, not access.
- Do not add `Disallow: /admin` to robots.txt: Google must be able to crawl the
  login response to see noindex. Health and error responses are also noindex.
- A visible FAQ explains actual supported uses. No fabricated ratings, prices,
  customer counts, or guaranteed search ranking are included.

After deployment, verify `https://hydroflow.arnur.id/` in Google Search Console,
submit `https://hydroflow.arnur.id/sitemap.xml`, and use URL Inspection to request
indexing of the homepage. Search Console requires the owner's Google account;
this repository does not submit or verify ownership automatically. If an admin URL
was already indexed, its removal takes recrawling; Search Console's removals tool
can request faster temporary removal.

Rankings and indexing are decided by Google. Useful original project photos,
case studies, accurate descriptions, and relevant external links support ongoing
SEO. The existing Tailwind CDN remains a frontend performance dependency; any
future CSS compilation should happen on a separate build machine, not this ARM host.

References: https://developers.google.com/search/docs/crawling-indexing/block-indexing
and https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap

Google HTML verification file `google195041c754aa4836.html` is served unchanged at
`https://hydroflow.arnur.id/google195041c754aa4836.html` via an explicit route and a
read-only Docker mount. It is also included in future images. Keep this file in
place for ongoing ownership checks. The owner must finish verification in Google
Search Console; serving the file alone does not confirm account ownership.

## Riwayat versi, foto alat, dan lampiran

Open **Admin → Riwayat versi** (`/admin/versions`) to create or edit a release.
Each release has a unique version number, title, release date, summary, plain-text
change notes, one optional cover photo, and draft/published status. Dates control
sorting, not scheduled publication. Set Published only when the release is ready.

Recommended workflow:
1. Create the version as Draft and upload its cover (JPG/PNG/WebP, max 10 MiB and
   12.5 MP). Cover processing uses the existing bounded WebP optimization.
2. Save, then add manual book/report PDFs individually: max three per version,
   each at most 10 MiB. Existing 16 MiB request limits are retained.
3. Mark individual PDFs public or private. Draft releases keep all media private
   regardless of the PDF visibility checkbox. Private PDFs require an admin login.
4. Preview the saved release, then change its status to Published.

Published releases appear at `/changelog` (10 per page), have individual pages,
and the three most recent by date appear on the homepage. Their public page URLs
are added to the sitemap. Empty changelog and all admin/preview pages are noindex.
No example releases are created automatically.

PDFs and release covers live under `/app/data/releases` in the existing persistent
volume, outside `/uploads`. Every media request checks publication/access state,
and media responses use `no-store` so shared caches do not retain private data.
Public PDFs may be indexed by search engines; private PDFs are noindex and require
an authenticated admin session. Previously downloaded public files cannot be
recalled if a release later becomes private.

PDF files are copied to storage without rendering, OCR, or conversion. Basic PDF
signature/end-marker checks reject obvious non-PDF or incomplete uploads; they do
not constitute document sanitization. Files can be opened in the visitor's browser
or downloaded with their sanitized original filename. Deleting a release removes
its cover and documents; replacing a cover deletes the old one. Existing backup
instructions include these files. No additional dependencies or Docker services
are required.
