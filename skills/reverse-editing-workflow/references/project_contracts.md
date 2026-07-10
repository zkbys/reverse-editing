# Project Contracts

## Identity and isolation

Assign one independent `project_id` and one `outputs/<project_id>/` directory to every reference video. Do not merge unrelated reference evidence, generated previews, QC decisions, or Jianying manifests.

Use `project_config.json` to record source metadata, output directories, current evidence level, and default-deny flags for download, LibTV, remote generation, TTS, OCR installation, and Jianying mutation.

## Mature project shape

```text
<project_id>/
  intake.json
  project_config.json
  source/
  analysis/shot_index.reviewed.json
  content/copy_script.json
  content/voiceover_script.json
  subtitles/subtitle_track.json
  subtitles/word_timestamps.json
  subtitles/subtitles.vtt
  subtitles/subtitles.srt
  audio/audio_mix_plan.json
  storyboard/
  previs/
  media/
  quality/
  jianying_manifest/
  reports/
```

Rendered media never replaces the editable control layer.

## Initialization

Validate intake and dry-run before creation:

```bash
python3 scripts/validate_intake.py --intake <intake.json>
python3 scripts/init_project.py --intake <intake.json> --output-root outputs --report <dry-run-report.json>
```

Use `--create` only after readiness and the project path are accepted. Never create a real project for a speculative or incomplete intake.

## Release hygiene

Keep the reusable Skill generic. Do not commit or upload:

- real reference media or downloaded source caches
- LibTV/generated preview media
- Jianying drafts, `root_meta_info.json`, or draft backups
- screenshots, contact sheets, OCR frames, or project `outputs/`
- local absolute paths, user names, account data, credentials, keys, or tokens
- loop experiments, temporary reports, or private user statements

Release only the Skill, generic scripts/references/assets, synthetic samples, tests, and public-facing repository documentation. Local validation reports may contain machine paths, but they must stay outside the release repository.
