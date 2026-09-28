# Hydroflow CMS — ARM deployment audit

Audit date: 2026-09-28. Scope: all application, template, static, test, Docker,
configuration, and development-runner files in this repository; read-only inspection
of the host, other containers, and the existing tunnel. Secrets were not included
in this report. Existing video-demo and Windows development changes were retained.

## Findings

1. **Native architecture is correct.** Host is `aarch64`, four Cortex-A53 cores,
   approximately 1.8 GiB physical RAM. Existing CMS Docker image reports `arm64`;
   installed Pillow is an ARM-native wheel. There is no evidence of x86 emulation
   causing the reported crashes.
2. **Temporary files consume RAM.** `/tmp` is tmpfs. The earlier Playwright
   installation attempted to download a roughly 187 MB Chromium archive there;
   extraction and browser processes add further memory. This was unsuitable for
   this host alongside its other services. Browser tests/installers are no longer
   part of server-side verification.
3. **Swap is compressed RAM.** The host has about 900 MiB zram swap, not a disk
   swapfile. It does not provide another 900 MiB of independent physical memory.
4. **Original runtime concurrency increased peak memory risk.** Four Gunicorn
   threads could process several images concurrently. EXIF transpose happened
   before resizing, potentially making full-resolution copies of images up to
   25 MP. This has been corrected.
5. **Original resource limits did not cover the entire deployment workflow.**
   CMS runtime had a 384 MiB RAM cap, but default combined RAM/swap allowance was
   768 MiB. Browser installers and Docker builds were outside the CMS limits.
6. **Crash cause remains unproven.** Retained kernel journal entries contain no
   matching OOM-kill, panic, or I/O-error evidence. Previous-boot records are sparse,
   timestamps show clock jumps, and `/var/log` is on zram. Absence of a saved OOM
   entry does not rule out memory pressure, power supply issues, or a hard lockup.
   At audit time CPU temperature was approximately 53 C and disk had 91 GiB free;
   these current observations do not establish historical conditions.
7. **Other application state changed across the reported restarts.** At this
   audit only `safety-telemetry-dashboard` was running besides the new CMS. The
   previously observed Hydroflow dashboard stack was absent from `docker ps -a`.
   This audit did not remove, recreate, or restart those services.

## Corrections

- Compose explicitly requires ARM64 and never pulls/builds during deployment.
- Existing native image supplies pinned dependencies. Only application files,
  templates, logo, static assets, and Gunicorn config are mounted read-only.
  SQLite and media stay in the existing persistent named volume.
- One synchronous Gunicorn worker, one request at a time; periodic worker recycling.
- 256 MiB memory, zero container swap, half a CPU, 32 PIDs, 24 MiB temporary space.
- 12.5 MP decoded-image limit; resize before EXIF transpose; prompt image-buffer
  release. Up to eight files and 16 MiB total per request, still 10 MiB per file.
- Binary-only dependency installation when building elsewhere prevents unexpected
  source compilation on platforms without a matching wheel.
- Deployment preflight checks ARM architecture, at least 512 MiB available RAM,
  disk space, temperature, local image architecture, and environment file presence.
- Container restart retries capped at three. After a host reboot, run preflight
  and `scripts/deploy.sh` explicitly; no unconditional CMS restart loop at boot.

## Verification

- Ten functional tests pass in an offline container capped at 256 MiB and 0.5 CPU.
- Includes authentication/CSRF, contact validation, photo lifecycle, 4000×3000 PNG
  resize, oversized-header rejection without partial files, EXIF/alpha preservation,
  logo reset, password change, empty gallery, and YouTube URL validation.
- Test-process peak RSS: **169572 KiB (approximately 166 MiB)**. This includes test
  image generation and password hashing; it is not a container-wide peak figure.
- Cgroup confirms `memory.max=268435456`, `memory.swap.max=0`; `oom=0`, `oom_kill=0`,
  and `max=0` during the successful run. This kernel lacks `memory.peak`.
- Template parsing, inline JavaScript syntax, Compose validation, shell syntax,
  and whitespace checks passed. No browser was installed or launched for this audit.

The finite checks demonstrate ARM compatibility and bounded operation under the
exercised workload, not a guarantee against every hardware or host-wide failure.
Image processing is intentionally serialized and may briefly queue other requests.
Public gallery size is still flexible; very large galleries increase HTML/browser
work, so optimized photos and a practical gallery size remain advisable.

## Tunnel status

`/etc/cloudflared/config.yml` was unchanged at audit time:
`hydroflow.arnur.id` still points to port 8080. The new CMS uses localhost:8091.
The earlier DNS-helper result was interrupted by a restart and is not confirmed.
No tunnel restart or public-domain cutover was performed in this audit. The desired
future mapping remains landing=hydroflow.arnur.id and
dashboard=dashboard-hydroflow.arnur.id, once the dashboard service is available.

## Controlled local deployment result

After the bounded tests passed, `scripts/deploy.sh` recreated only the CMS using
its existing image and read-only source mounts. No build, package installation,
browser download, or tunnel change was performed.

- Local URL: http://127.0.0.1:8091; admin: /admin.
- Docker health: healthy, restart count 0, OOMKilled false.
- Live memory after authenticated login and ten sequential page requests:
  **42.82 MiB / 256 MiB**; CPU snapshot 0.04%.
- Host available RAM: approximately 793 MiB, load average 0.51 / 0.52 / 0.50.
- Verified live limits: RAM 268435456 bytes; RAM+swap same; CPU quota 0.5; PIDs 32.
- HTTP 200 for health, landing, login, admin CSS, and logo; authenticated admin
  login succeeded. Tests did not change production photos, contact, logo, or video.
- These are short-run observations, not a prolonged soak test or hardware diagnosis.

References consulted:
- https://docs.docker.com/engine/containers/resource_constraints/
- https://pillow.readthedocs.io/en/stable/reference/Image.html

## Public tunnel cutover — 2026-09-28

At the user's subsequent request, changed only `hydroflow.arnur.id` from port
8080 to 8091 in `/etc/cloudflared/config.yml`. Configuration was validated and
cloudflared was restarted successfully; no application container was restarted.
Backup: `/etc/cloudflared/config.yml.backup-20260928T131212Z`.

Public HTTPS checks with curl confirmed the expected CMS landing page, admin login
(via `/admin` redirect), and health response. Python urllib initially received a
403 while curl received 200; no Cloudflare security settings were changed.
The other ingress routes were retained. The old dashboard hostname migration is
not included in this cutover because its application is not currently running.
