---
name: reverse-editing-workflow
description: "Turn a short-form reference video into an isolated, editable reverse-editing project: intake and project_id contracts, shot analysis, storyboard/previs, editable copy/voiceover/subtitle/audio layers with VTT/SRT, local Tesseract plus human visual QC, auditable internal-preview overrides/placeholders, and guarded N-slot Jianying seed-clone validation. Use for store, restaurant, product, or creator reference videos; same-structure remake planning; internal shooting previews; editable subtitle/voiceover preparation; or safe local workflow packaging before any download, LibTV, TTS, OCR installation, or Jianying mutation."
---

# Reverse Editing Workflow

## Operating mode

Work in small Loop Engineering cycles. Every loop report must contain, in order:

1. `目标`
2. `输入`
3. `动作`
4. `禁止事项`
5. `验收标准`
6. `产物`
7. `验证`
8. `复盘`
9. `下一轮`

Advance autonomously through safe local/read-only loops. Stop only for a real blocker or for authority that the user has not granted.

## Default-deny boundary

Unless the user explicitly authorizes the current loop, do not:

- Download a URL or reference video.
- Run LibTV or any remote video generation.
- Call TTS, paid voice, or paid OCR services.
- Install Tesseract, OCR language data, FFmpeg, or other system dependencies.
- Create, clone, register, or modify any Jianying draft.
- Delete, move, rename, or overwrite existing user artifacts.
- Burn subtitles or voiceover into preview media.
- Treat model-generated in-frame text as formal subtitles.
- Copy reference-video wording as final copy.
- Upload reference media, generated media, Jianying drafts, screenshots, project outputs, local absolute paths, account data, secrets, or experiment logs.

Authorization is loop-specific. Prior authorization does not silently carry into a later download, generation, TTS, OCR-install, or Jianying-write loop.

## 1. Intake and isolated project

Validate intake first:

```bash
python3 scripts/validate_intake.py --intake <intake.json>
```

Dry-run initialization, then create only when intake readiness and the output path are accepted:

```bash
python3 scripts/init_project.py --intake <intake.json> --output-root outputs --report <dry-run-report.json>
python3 scripts/init_project.py --intake <intake.json> --output-root outputs --create
```

Give every reference its own `project_id` and `outputs/<project_id>/` directory. Never mix two references unless the user explicitly requests a comparison project.

## 2. Shot structure, storyboard, and previs

When an already-authorized local source exists, run deterministic analysis:

```bash
python3 scripts/analyze_reference_video.py --project-dir <project_dir> --force
python3 scripts/validate_shot_index.py --project-dir <project_dir>
```

Treat shot-index errors as blockers and warnings as human-review items. After reviewed `shot_index`, `storyboard`, and `previs_plan` exist, render the local review page:

```bash
python3 scripts/render_previs_html.py --project-dir <project_dir> --force
```

Reference frames and HTML previs are internal structural evidence, not publishable media.

## 3. Editable content layer

Keep these source-of-truth files outside rendered video and Jianying:

- `content/copy_script.json`
- `content/voiceover_script.json`
- `subtitles/subtitle_track.json`
- `subtitles/word_timestamps.json`
- `audio/audio_mix_plan.json`

Validate and export review subtitles:

```bash
python3 scripts/validate_content_layer.py --project-dir <project_dir>
```

VTT/SRT export does not authorize subtitle burn-in, TTS, or Jianying insertion.

## 4. Visual OCR and human QC

Read `references/dirty_subtitle_qc.md` before media admission. Use existing local FFmpeg/Tesseract only; never install them implicitly.

```bash
python3 scripts/visual_ocr_qc.py --project-dir <project_dir>
# Human edits quality/visual_ocr_qc/manual_visual_review.json after viewing every contact sheet.
python3 scripts/validate_visual_qc.py --project-dir <project_dir>
```

OCR output is candidate evidence. A human contact-sheet review is mandatory, and OCR silence never proves that a frame has no text.

If the user accepts failed shots for internal preview, preserve the original report and append a scoped audit record:

```bash
python3 scripts/record_qc_override.py \
  --project-dir <project_dir> \
  --shot-id <shot_id> \
  --authorized-by user \
  --reason "<decision reason>" \
  --authorize-internal-preview-only
```

An override can unblock an internal preview only. It never creates publish readiness.

## 5. Local non-publish placeholders

Use a local placeholder only when a required internal-preview slot has no admissible media and the loop explicitly accepts that fallback. The placeholder must be visibly marked internal-only, recorded in `manual_visual_review.json`, stored inside the project, and kept `publish_ready=false`. Never describe it as a delivered ending.

## 6. Guarded N-slot Jianying internal previs

Read `references/jianying_boundaries.md` before this stage. Derive slot count `N` from the current video's reviewed `manifest.plan.json`; never hardcode 17. The 17-slot case is a regression example, not a workflow rule.

Build and validate without writing Jianying:

```bash
python3 scripts/build_jianying_manifest.py \
  --project-dir <project_dir> \
  --seed-draft <read-only-seed> \
  --output-root <jianying-draft-root> \
  --draft-name <new-unique-name> \
  --output <project_dir>/jianying_manifest/multi_slot_manifest.json

python3 scripts/validate_jianying_seed.py \
  --manifest <multi_slot_manifest.json> \
  --seed-draft <read-only-seed> \
  --output <seed-validation.json>
```

Only after explicit Jianying-write authorization, create a collision-free new clone and adapt clone-local media:

```bash
python3 scripts/clone_jianying_seed.py --manifest <manifest.json> --seed-validation <seed-validation.json> --output <clone-report.json> --authorize-jianying-write
python3 scripts/shift_jianying_timeline.py --draft <new-clone> --manifest <manifest.json> --clone-manifest <clone-report.json> --output <shift-report.json> --authorize-jianying-write
python3 scripts/fit_jianying_clone_slots.py --manifest <manifest.json> --clone-manifest <clone-report.json> --output <fit-report.json> --authorize-jianying-write
```

Never point mutation helpers at the seed or an existing working draft. Short clips may be padded by freezing only the clone-local final frame; source files must remain hash-identical.

## 7. File and GUI evidence levels

Run file-level validation first:

```bash
python3 scripts/validate_jianying_draft.py \
  --manifest <manifest.json> \
  --clone-manifest <clone-report.json> \
  --shift-manifest <shift-report.json> \
  --fit-manifest <fit-report.json> \
  --output <file-validation.json>
```

Then separately record GUI evidence with `record_jianying_gui_validation.py`. Match the observed segment count to the current video's `N`. Keep `user_report`, `screenshots`, and `screen_recording` evidence levels distinct. File-level or GUI playback pass proves internal-preview usability only; it does not prove export quality or publish readiness.

## References

Load only the current loop's reference:

- `references/project_contracts.md` — project isolation and release hygiene.
- `references/content_layer_contract.md` — editable copy/voiceover/subtitle/audio rules.
- `references/dirty_subtitle_qc.md` — Tesseract, contact sheets, manual decisions, override audit, placeholders.
- `references/jianying_boundaries.md` — N-slot clone safety, duration fitting, and evidence levels.
- `references/loop_engineering.md` — required report structure.

## Validated status

The package has passed a second real-reference forward test through storyboard/previs, editable content, local OCR plus human QC, audited override, seed clone, clone-local short-clip fitting, file validation, and full GUI playback. That evidence remains internal-preview evidence. Clean-package regression covers both the validated 17-slot case and a non-17 case to ensure slot count stays video-specific.

**v1 frozen** (2026-07-11): Single-video reverse-editing workflow is now complete. The end-to-end chain—intake, shot analysis, storyboard/previs, editable content layer (copy/voiceover/subtitle/audio), VTT/SRT export, visual OCR + human QC, QC override audit, N-slot Jianying seed clone with duration fitting, file/GUI validation, deterministic internal preview render, and structured delivery package—has been validated on one real reference video and packaged as a frozen v1. No further autonomous expansion unless explicitly requested.


The package has passed a second real-reference forward test through storyboard/previs, editable content, local OCR plus human QC, audited override, seed clone, clone-local short-clip fitting, file validation, and full GUI playback. That evidence remains internal-preview evidence. Clean-package regression covers both the validated 17-slot case and a non-17 case to ensure slot count stays video-specific.
