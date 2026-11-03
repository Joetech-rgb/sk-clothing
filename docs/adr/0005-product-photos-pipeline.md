# ADR 0005: Product photo pipeline, and approval of Pillow and boto3

Status: proposed

## Decision
Photos go **browser -> Cloudflare R2 directly** (presigned PUT), then a background worker validates and resizes them to WebP, then Cloudflare's CDN serves them. App servers never touch image bytes on either path.

1. Staff request an upload (staff permission, rate limited). The server creates a `ProductImage` row (status `pending`) and returns a presigned PUT URL for `uploads/{uuid}`, valid for 5 minutes, with the Content-Type signed.
2. The browser PUTs the file straight to R2, then calls "complete".
3. "Complete" enqueues a Celery task on a **dedicated `media` queue** so image work can never delay payment webhooks or OTP SMS.
4. The worker checks the object size (HEAD) before downloading, then runs `imaging.process_image()`, writes WebP sizes to `media/products/{product_id}/{uuid}/{width}.webp` with `Cache-Control: public, max-age=31536000, immutable`, marks the row `ready` (or `failed` with a code), and deletes the original. The task is idempotent. Transient storage errors retry with backoff. A bad image fails once and is never retried.
5. A bucket lifecycle rule expires `uploads/` after 24 hours as a backstop.

Every upload gets a new UUID, so a published URL never changes content and is cached forever. Nothing needs invalidating.

## Dependency proposal (CLAUDE.md rule 6)

### Pillow: approved, added in this change
- **What:** image decode, resize, WebP encode.
- **Why:** the brief requires WebP resizing. Pillow is pure wheels (libwebp, libjpeg and littlecms bundled), so no system packages in Docker or CI.
- **Alternatives:** *pyvips/libvips* streams images and is much lighter on memory and faster at high volume, but needs a system library and is harder to run on developers' Windows machines. *Cloudflare edge image transformation* removes the worker entirely but is a paid per-transformation service that changes the brief; I did not verify its current pricing, so it is not chosen. *ImageMagick* is the weakest option for server use.
- **Cost:** free. **Maintenance:** very active, with frequent security releases. Keep it updated with Dependabot and pin a compatible range (`~=12.1`).
- **Decision:** start with Pillow behind the single function `process_image()`. Switch to pyvips if sustained load passes roughly 100 photos per minute or worker memory becomes the limit. Callers do not change.

### boto3: approved, added in the next change when first used
- **What:** presigned URLs and object operations against R2.
- **Why:** Cloudflare's own R2 documentation uses boto3 for Python.
- **Alternatives:** `botocore` alone (smaller, same signing, no convenience layer), the MinIO SDK, hand-written SigV4 (rejected: security-sensitive code to own).
- **Cost:** free; larger install. **Maintenance:** AWS-maintained, frequent releases.
- **Known pitfalls to design for:**
  - R2 presigned URLs support GET, PUT, HEAD and DELETE. **POST policies are not supported**, so a size range cannot be enforced in the URL. We enforce size in the worker (HEAD before download), keep URLs short-lived, and expire `uploads/` by lifecycle rule.
  - Newer AWS SDKs add default request checksums that were reported to break R2. For boto3, set `request_checksum_calculation` and `response_checksum_validation` to `when_required`, and add a test that signs a URL with that config.
  - The bucket needs a CORS policy limited to the console origin, and R2 requires the browser to send the same Content-Type that was signed.

## Measured here (Pillow 12.1, one CPU core, includes WebP encoding of four sizes)
| Photo | Upload | Time | Memory added |
|---|---|---|---|
| 12 MP | 2.8 MB | 0.8 s | about 50 MB |
| 24 MP | 5.6 MB | 1.1 s | about 90 MB |
| 48 MP | 11 MB | 1.3 s | about 175 MB |

Planning rule: **about 200 MB per concurrent job at the 50 MP cap**, and roughly 50 to 75 photos per minute per core. A launch bulk import of 20,000 photos is about 4 hours on one core, or about 1 hour on four. Worker concurrency must be set from memory, not core count.

## Limits (in `imaging.py`)
25 MB upload, 50 megapixels, 10,000 px on a side, JPEG/PNG/WebP only, no animation. A 200 MP "high-resolution mode" phone photo is refused; staff should use the 50 MP mode. iPhone HEIC is not supported by Pillow alone; browsers usually convert to JPEG on upload, to be confirmed on a real device.

## Security properties (tested)
Format decided by decoding, not by name or header. Decompression bombs refused before decoding pixels. Truncated and animated files refused. EXIF (including GPS) removed after rotation is applied. Embedded colour profiles converted to sRGB so apparel colours match across devices; an unusable profile falls back instead of failing. Never upscales. Storage keys contain only numeric ids and server-made UUIDs.

## Scalability, stated honestly
- **Images are not the scaling risk.** They are served by the CDN, immutable, and uploads are a staff and vendor trickle.
- **The real risks for a very large audience** are catalog and search reads, checkout writes, stock contention on popular items, and a single Hostinger VPS as one machine and one point of failure. A full plan needs numbers I do not have: expected peak concurrent users, number of products, peak orders per hour, and the VPS plan size. Proposed follow-up: ADR 0006, a scalability plan with measured targets.
- The worker design scales sideways: more `media` workers, same queue.

## Not in this change
Models for upload status, the presign and complete endpoints, the Celery task, the R2 client, and CDN and bucket configuration. They come after the catalog is merged, because they extend `ProductImage`.

## Placement
`imaging.py` has no Django dependency and lives in `apps/catalog` for now. Returns (Phase 2), vendors (Phase 5) and ID documents (a private bucket, never this public pipeline) will need a shared home. Proposal: a `media` app when that phase starts. This needs approval under CLAUDE.md section 11.
