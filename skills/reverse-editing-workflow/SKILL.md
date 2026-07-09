---
name: reverse-editing-workflow
description: "Reverse-editing workflow for turning a short-form reference video into a reusable project package: intake contract, project_id isolation, shot/storyboard planning, editable copy/voiceover/subtitle/audio control layers, optional storyboard/previs handoff, Jianying manifest planning, dirty-subtitle QC, and validation reports. Use when a user asks Codex to process a restaurant/store/product short video reference, install or use the reverse-editing workflow, create a same-structure remake plan, prepare editable subtitles/voiceover, or generate a safe local workflow package before any LibTV, TTS, download, or Jianying draft modification."
---

# Reverse Editing Workflow

## Mode

Run this workflow as small loops. Each loop must declare input, action, forbidden actions, acceptance criteria, artifacts, validation, and retrospective before moving to the next loop.

Default to local files, schemas, manifests, and reports. Do not jump to remote generation or draft mutation.

## First Action

For a new request, create or validate an intake file first:

```bash
python3 skills/reverse-editing-workflow/scripts/validate_intake.py --intake <intake.json>
```

If the user provides only a video URL, fill `assets/new_reference_intake.template.json` with the URL and keep download disabled unless explicitly authorized.

## Safe Project Setup

Dry-run project initialization before creating files:

```bash
python3 skills/reverse-editing-workflow/scripts/init_project.py --intake <intake.json> --output-root outputs --report outputs/init_dry_run.json
```

Create the project only after the intake is ready:

```bash
python3 skills/reverse-editing-workflow/scripts/init_project.py --intake <intake.json> --output-root outputs --create
```

Each reference video must have its own `project_id` and output directory.

## Hard Boundaries

Unless the current loop and user explicitly authorize it, do not:

- Run LibTV or other remote video generation.
- Download a URL.
- Call TTS or paid voice services.
- Install OCR dependencies.
- Modify existing Jianying drafts.
- Delete, move, or rename existing user artifacts.
- Treat burned-in or model-generated frame text as formal subtitles.
- Copy reference-video wording as final copy.

Use `scripts/download_reference_optional.py` only when the user explicitly allows downloading.

## Content Layer

Keep copy, voiceover, subtitles, word timestamps, and audio planning editable:

- `content/copy_script.json`
- `content/voiceover_script.json`
- `subtitles/subtitle_track.json`
- `subtitles/word_timestamps.json`
- `audio/audio_mix_plan.json`

Validate and export review subtitles:

```bash
python3 skills/reverse-editing-workflow/scripts/validate_content_layer.py --project-dir <project_dir>
```

VTT/SRT exports are review artifacts. They are not approval to burn subtitles into video or write a Jianying draft.

## References

Load only what the current loop needs:

- `references/project_contracts.md`: project_id, directory, and artifact boundaries.
- `references/content_layer_contract.md`: editable copy/voiceover/subtitle/audio rules.
- `references/dirty_subtitle_qc.md`: text-in-frame risk policy.
- `references/jianying_boundaries.md`: Jianying draft safety and evidence levels.
- `references/loop_engineering.md`: required loop report format.

## Current Status

This is an alpha workflow package. It is safe for local intake, project setup, schema validation, and sample exploration. Real video analysis, LibTV generation, TTS, OCR installation, and Jianying draft modification remain explicit follow-up loops.
