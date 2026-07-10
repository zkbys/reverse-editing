# Visual OCR and Human QC

## Purpose

Prevent burned subtitles, platform UI, watermarks, wrong brands, random generated text, and reference-account text from silently entering a draft or publish package.

## Evidence sequence

1. Sample every candidate shot at 20%, 50%, and 80% by default.
2. Run an already-installed local Tesseract engine and preserve raw candidates, confidence, and bounding boxes.
3. Build contact sheets in small shot groups.
4. Have a human inspect every contact sheet and any high-risk full-size frame.
5. Record one classification and reason per shot.
6. Validate the review and create an internal-draft whitelist.

```bash
python3 scripts/visual_ocr_qc.py --project-dir <project_dir>
python3 scripts/validate_visual_qc.py --project-dir <project_dir>
```

Do not install Tesseract or language data without explicit authorization. If OCR is unavailable, use `--allow-manual-only` for evidence extraction and later `--allow-ocr-gap` only when the loop explicitly accepts that gap. Never translate “OCR unavailable” or “OCR found nothing” into “the frame has no text.”

## Human classifications

- `pass_internal_draft`: no confirmed dirty text in sampled evidence; still not publish-ready.
- `warn_internal_draft_only`: small, blurred, approved, or unresolved environmental text; internal preview only.
- `fail_dirty_text`: salient generated, random, wrong-brand, UI, watermark, or conflicting text; block the slot.

Manual review must set `contact_sheets_reviewed=true`, identify the reviewer/time, preserve `publish_ready=false`, and include a concrete reason for every shot.

## Human override audit

When the user accepts a failed shot for internal preview, never edit or delete the original finding. Append an audit record:

```bash
python3 scripts/record_qc_override.py \
  --project-dir <project_dir> \
  --shot-id <shot_id> \
  --authorized-by user \
  --reason "<reason>" \
  --authorize-internal-preview-only
```

The record must preserve the source report hash, original classification, accepted slot list, decision source, reason, and `publish_or_client_delivery=not_allowed`.

## Local placeholder policy

Use a local placeholder only for an internal previs gap. Store it inside the isolated project and add a `local_non_publish_placeholder_slots` record containing:

- unique `slot_id`
- project-relative asset path
- `visibly_marked_internal_only=true`
- `publish_ready=false`
- reason for the fallback

Do not use a placeholder to conceal a failed publish gate. Replace it before any publish or client delivery.
