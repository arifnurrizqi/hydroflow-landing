# Version management — 2026-09-29

Implemented using the existing Flask/SQLite service and persistent volume. New
release/document tables are additive; current gallery, contacts, logo, video,
Google verification file, and equal-height gallery changes are retained.

Features: version CRUD, unique version labels, dates, summary and plain-text notes,
one optimized cover photo, up to three PDFs (10 MiB each, single-file upload),
draft/published states, per-document public/private visibility, admin preview,
paginated public changelog, individual release pages, three latest homepage cards,
and sitemap URLs for published pages only.

19 functional tests passed in the existing bounded ARM runner. They include
unauthenticated draft/media denial, publish/unpublish access changes, private-PDF
checks and no public-upload bypass, byte-range downloads, size/signature limits,
file cleanup, replacement, validation, escaping, pagination and sitemap filtering.
Peak test-process RSS: 171328 KiB (about 167 MiB); cgroup OOM/kill/max events all zero.
No browser, PDF renderer, OCR, package installation, or image build was run.

Before migration, the live SQLite database was backed up in the existing volume:
/app/data/backups/before-releases-20260929T110234Z.sqlite3

Private assets are stored outside /uploads and served only through checked routes.
Public/private assets send no-store; PDF responses additionally send a restrictive
sandbox CSP. PDF validation is structural signature checking, not a malware scan.
Media access uses the same admin session-version checks as the CMS.

No production release/photo/PDF content is fabricated or seeded by this change.

Deployment completed with scripts/deploy.sh and the existing ARM64 image. CMS
health is healthy. Public HTTPS checks passed for /, /changelog, and releases.css.
Authenticated read-only checks passed for /admin, /admin/versions, and the new
version form; their noindex headers remain active. No production release data was
created or published during verification. The empty public changelog is noindex
until a release is published.
