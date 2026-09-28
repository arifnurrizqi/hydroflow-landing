# SEO deployment check — 2026-09-28

Published at https://hydroflow.arnur.id/ using the existing ARM image, without
building or installing dependencies on the server. Only the CMS was recreated;
the tunnel configuration and unrelated containers were not changed.

Implemented:
- Indonesian search title and description focused on actual IoT water monitoring.
- Fixed public HTTPS canonical URL independent of incoming Host/query parameters.
- Open Graph/Twitter metadata; uploaded raster logos used for social-image metadata.
- Server-rendered Organization, WebSite, WebPage, and Service JSON-LD with live CMS
  contact information. No invented ratings, offers, prices, or customer counts.
- Clear H1, relevant section headings, and a visible FAQ describing supported uses.
- `/sitemap.xml` lists only the homepage. No fake change dates or fragment URLs.
- `/robots.txt` allows crawling and links to the sitemap.
- Every `/admin` response sends `X-Robots-Tag: noindex, nofollow` and `no-store`.
  Login and authenticated admin HTML also retain their noindex meta tag.
- Admin links are absent from the public landing page and sitemap; authentication
  remains required. Health and error responses also send noindex.

Verification:
- 13 functional/SEO tests passed inside the existing 256 MiB / 0.5 CPU test limits;
  process peak RSS 167368 KiB, zero cgroup OOM events.
- Public HTTPS checks passed for homepage canonical/JSON-LD, sitemap XML, robots.txt,
  and noindex headers on `/admin`, `/admin/`, and `/admin/login`.
- Public robots.txt permits Googlebot to fetch the homepage and read login noindex.
  This verifies served directives, not an actual request from a verified Googlebot.
- CMS returned healthy after deployment; no frontend build or browser was run.

Owner follow-up in Google Search Console:
1. Select/verify the domain property or https://hydroflow.arnur.id/ URL-prefix property.
2. Submit https://hydroflow.arnur.id/sitemap.xml under Sitemaps.
3. Inspect https://hydroflow.arnur.id/, test the live URL, and request indexing.
4. Monitor indexing and search performance. If any admin URL was previously indexed,
   let Google recrawl its noindex response or use the temporary removals tool.

Search Console ownership/submission is not performed: no owner's Google account
or verification token is available in this session. Ranking or immediate indexing
cannot be guaranteed. Noindex is a search instruction, not a replacement for login.
Do not disallow /admin in robots.txt, because that can hide noindex from Google.

References:
- https://developers.google.com/search/docs/crawling-indexing/block-indexing
- https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap
- https://developers.google.com/search/docs/appearance/structured-data/organization

## Google HTML verification file

The owner supplied `google195041c754aa4836.html`. An explicit route and read-only
Docker mount now expose exactly that file at the public root URL. Local and public
requests returned HTTP 200 without redirects and matched the original bytes.
Admin noindex remains active. Search Console's verification button still needs to
be completed in the owner's account; no account verification success is claimed.
