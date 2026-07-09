# Dirty Subtitle QC

## Purpose

Generated preview clips can contain unwanted text in the frame. This text must be treated as a quality risk, not as official subtitles.

## Failure Items

Mark a clip or shot as failed or blocked if it contains:

- model-generated subtitles
- platform UI or account labels
- watermarks
- unapproved on-screen text
- wrong store names
- wrong product names
- text copied from the reference video
- text that conflicts with the editable content layer

## Local Scan

Use:

```bash
python3 scripts/dirty_subtitle_qc_scan.py --project-dir outputs/<project_id> --date-stamp YYYYMMDD
```

The script can sample frames locally. If OCR is unavailable, record the missing dependency as a validation gap and use manual frame review or contact sheets.

## OCR Boundary

Do not install OCR dependencies or run paid OCR services unless a loop explicitly authorizes it.

If OCR is unavailable, the report should say so directly. Never convert "OCR unavailable" into "no dirty subtitles found".

## Publish Boundary

Dirty subtitle QC is a gate before final publish material. Preview drafts can exist with known text risk, but final publish assets must clear or explicitly waive the risk.
