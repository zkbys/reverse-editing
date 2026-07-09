# Project Contracts

## Project Identity

Every reference video must use an independent `project_id`.

Examples:

- `sample_corner_noodle_reference`
- `lamb_restaurant_reference_001`
- `glasses_store_reference_001`

Do not merge different reference videos into one project directory unless the user explicitly asks for a comparison project.

## Expected Directory Shape

A mature project should keep these artifacts separate:

- `analysis/shot_index.reviewed.json`
- `content/copy_script.json`
- `content/voiceover_script.json`
- `subtitles/subtitle_track.json`
- `subtitles/word_timestamps.json`
- `audio/audio_mix_plan.json`
- `storyboard/`
- `preview/`
- `jianying_manifest/` or `libtv_workflow/`
- `reports/`
- `quality/`

Each artifact should remain editable. Do not replace the editable control layer with only rendered video or burned-in subtitles.

## Project Config

Use `project_config.json` as the first project-level contract. It should record:

- `project_id`
- source/reference metadata
- output directories
- feature flags for LibTV, TTS, OCR, and Jianying mutation
- current effective result
- draft/evidence status

Default safety flags should keep remote generation, TTS, LibTV, and Jianying modification disabled until a loop explicitly authorizes them.

## New Project Initialization

For a new project, start with a dry run if the reference video and `project_id` are not fully confirmed.

Use:

```bash
python3 scripts/init_reverse_editing_project.py --project-id <project_id> --dry-run
```

Only create the real directory when the `project_id` is known and the loop accepts the output path as its artifact.
