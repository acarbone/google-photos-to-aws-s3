# gphotos2s3

Back up a Google Takeout export of your Google Photos library to your own
AWS S3 bucket — cheaply, resumably, and without touching Google Photos
itself. Free up Google Account storage on your own terms: back up first,
verify the backup, then delete from Google Photos yourself whenever you're
ready. This tool never does that last step for you.

- **Resumable and idempotent.** Interrupt it any time — Ctrl+C, a crash, a
  laptop going to sleep mid-upload. Run it again and it picks up exactly
  where it left off, never re-uploading content that's already safely in S3.
- **Deduplicates automatically.** The same photo often lives in several
  Google Photos albums; Takeout exports it once per album. This tool uploads
  each unique photo's bytes exactly once, no matter how many albums
  reference it — a direct saving on your S3 bill.
- **Preserves Google's metadata.** GPS location, description, favorited
  status, and people tags from each photo's Takeout sidecar are uploaded
  alongside it, not discarded.
- **Cheap by default.** Uploads directly to S3 Glacier Instant Retrieval —
  a fraction of the cost of Google's storage, with instant (not
  restore-job) retrieval if you ever want a file back.
- **No Google account access required beyond Takeout itself.** This tool
  never calls any Google API and never touches your Google Photos library
  — it only reads the `.zip` files Takeout already gave you.

## Install

```bash
pip install gphotos2s3   # once published
```

Or, from a checkout of this repo — create and activate a virtualenv first,
then install into it:

```bash
python3 -m venv .venv
source .venv/bin/activate   # each new shell: re-run this before using gphotos2s3
pip install -e .
```

Requires Python 3.10+. If `pip install -e .` complains about the Python
version, it's picking up a global/older interpreter instead of the venv's —
confirm with `python3 --version` and `which pip` after activating.

## Quick start

1. **Export your library** with [Google Takeout](https://takeout.google.com/) — select only Google Photos, and download the resulting `.zip` file(s).
2. **Set up:**
   ```bash
   gphotos2s3 init
   ```
   This walks you through: where your Takeout `.zip` files are, your AWS
   credentials, which S3 bucket to use (or create), and a couple of
   preferences (storage class, deduplication). Credentials are saved to the
   standard `~/.aws/credentials` file under a dedicated profile — not a
   bespoke secret store — with owner-only file permissions.
3. **Run the backup:**
   ```bash
   gphotos2s3 run
   ```
   Safe to interrupt at any time. Run it again to resume.
4. **Check progress any time:**
   ```bash
   gphotos2s3 status
   ```
5. **Verify integrity after a run finishes:**
   ```bash
   gphotos2s3 verify
   ```
   Re-checks every uploaded file's checksum against S3 without re-uploading
   anything. Anything that doesn't match is flagged; `gphotos2s3 retry-failed`
   re-uploads it.

Only once you've verified your backup should you go delete anything from
Google Photos — that step is entirely manual and intentionally outside this
tool's scope (see [FAQ](#faq)).

## How resumability works

A local SQLite database (`~/.gphotos2s3/state.db` by default) tracks the
status of every photo/video discovered in your Takeout export: pending,
uploading, uploaded, or failed. Every status change is written to disk
immediately — never batched — so a killed process leaves at most one file
in an ambiguous state, and the next run resolves it automatically by
checking what's actually in S3 (S3 itself, not the local database, is the
ultimate source of truth). Even if you delete the local database entirely,
re-running discovery and upload reconstructs the correct state — content
already in S3 is detected and never re-uploaded.

Two things worth knowing:

- **Don't rename your Takeout `.zip` files while a backup is in progress**
  (moving them to a different folder is fine — only the filename matters
  for tracking).
- **The same photo in multiple albums**: only the bytes are deduplicated.
  Every album occurrence still gets its own small "pointer" record and its
  own metadata in S3, so nothing about which album it belonged to is lost.

## Browsing your backup in S3

Uploaded content is organized chronologically wherever a capture date could
be found embedded in the file itself (EXIF for photos, the video container's
own creation-time field for `.mp4`/`.mov`/`.m4v`):

```
<prefix>/content/2020/05/01/2020-05-01_143022__<sha256>.jpg
<prefix>/library/2020/05/01/2020-05-01_143022__<takeout-zip>/<original path>.pointer.json
```

A file with no extractable embedded date (common for screenshots,
downloaded images, HEIC/HEIF, and less common video containers) lands in a
flat `<prefix>/content/unknown-date/` bucket instead of a wrong guess — it's
still backed up correctly, just not date-sorted. The full content hash stays
in the filename either way, so nothing about deduplication changes: it's a
human-readable prefix layered on top, not a replacement for it. See
`spec/feat/chronological-s3-layout/plan.md` for the full design rationale
(in particular, why the date comes from the file's own bytes rather than
Google's sidecar JSON).

## Cost notes

The default storage class is **S3 Glacier Instant Retrieval** — cheaper
than S3 Standard-IA for cold storage, with millisecond retrieval (no
restore job, unlike Glacier Flexible Retrieval or Deep Archive). It carries
a 90-day minimum storage duration charge and a small per-request retrieval
fee — a reasonable trade for a personal photo backup you'll rarely touch.
Override with `gphotos2s3 init --reconfigure` if a different access
pattern suits you better (Standard-IA, Intelligent-Tiering, or plain
Standard are also supported).

Any interrupted large-file upload leaves a temporary, incomplete
multipart-upload record in S3; the bucket is configured (automatically, if
you let the wizard create it) with a lifecycle rule that aborts these after
7 days, so they never accumulate silent cost.

## Security

- AWS credentials are collected via a no-echo prompt and written only to
  the standard `~/.aws/credentials` file (permissions `0600`), under a
  profile name derived from your `--state-dir` — never into this tool's own
  config file, never logged.
- The wizard prints a minimum-privilege example IAM policy
  (`docs/iam-policy-example.json`) scoped to exactly the bucket/prefix you
  choose, split into a one-time **setup** tier (only needed if you ask it
  to create the bucket) and a smaller **operate** tier for ongoing runs —
  so you're not nudged toward broad, long-lived credentials.
- A bucket the wizard creates gets public access fully blocked, SSE-S3
  encryption by default, and the multipart-upload lifecycle rule above.

## FAQ

**Why doesn't this delete anything from Google Photos automatically?**
Deliberately out of scope. Automating deletion from your live photo library
would require Google Photos API/OAuth integration and turns a reversible,
low-risk backup tool into an irreversible one. Verify your S3 backup, then
delete from Google Photos yourself, on your own schedule.

**What if I add more Takeout `.zip` files later?**
Just point `--source` at them (or add them to the same folder you already
configured) and run `gphotos2s3 run` again — discovery picks up new files
without disturbing anything already tracked.

**Can I run more than one backup (e.g. two Google accounts)?**
Yes — use a separate `--state-dir` per account/bucket. Each instance gets
its own AWS profile automatically.

## Development

This project is built following a Spec-Driven process — decisions, plans,
and their review trail are preserved as a permanent record rather than
lost to chat history:

- [`spec/design/00_pipeline_tiers.md`](spec/design/00_pipeline_tiers.md) — the process this repo follows.
- [`spec/feat/google-photos-s3-backup/plan.md`](spec/feat/google-photos-s3-backup/plan.md) — the full plan for this tool, including its multi-round architecture/consistency/risk review trail.
- [`spec/feat/google-photos-s3-backup/research.md`](spec/feat/google-photos-s3-backup/research.md) — research behind the Google Takeout format and S3 mechanics this tool relies on.

Run the test suite and quality gates (with `.venv` activated, per Install
above):

```bash
pip install -e ".[dev]"
pytest
ruff check .
ruff format --check .
mypy src/gphotos2s3
```

All tests run against a mocked AWS (`moto`) and synthetic Takeout fixtures
— no real credentials or network access required.

## License

MIT — see [LICENSE](LICENSE).
