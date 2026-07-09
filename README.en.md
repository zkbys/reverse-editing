# Reverse Editing Workflow

Language: [中文](README.md) | English

> Alpha preview. This repository packages a local-first reverse-editing workflow as a Codex Skill plus Claude Code instructions.

## What It Does

`reverse-editing-workflow` turns a short-form reference video into an editable workflow package:

- intake contract
- isolated `project_id`
- shot structure, storyboard, and previs planning
- editable copy, voiceover, subtitle, word-timing, and audio-mix control layers
- Jianying/CutCap manifest planning before draft mutation
- dirty-subtitle and in-frame text QC boundaries
- local validation reports

The current version focuses on the workflow skeleton and editable control layer. By default it does not download videos, run remote generation, call TTS, or modify Jianying drafts.

## Install as a Codex Skill

```bash
git clone https://github.com/zkbys/reverse-editing.git
mkdir -p ~/.codex/skills
cp -R reverse-editing/skills/reverse-editing-workflow ~/.codex/skills/
```

Restart Codex, then ask:

```text
Use $reverse-editing-workflow to process this reference video as a safe local workflow package: <video link or local file>
```

## Claude Code

Clone the repo, then ask Claude Code to read:

```text
CLAUDE.md
skills/reverse-editing-workflow/SKILL.md
```

Example prompt:

```text
Use the reverse-editing workflow to process this reference video URL. Keep download disabled until I explicitly authorize it.
```

## Try the Sample

```bash
pip install -r requirements.txt
python3 skills/reverse-editing-workflow/scripts/validate_intake.py --intake samples/fake-corner-noodle/intake.json
python3 skills/reverse-editing-workflow/scripts/init_project.py --intake samples/fake-corner-noodle/intake.json --output-root /tmp/reverse-editing-demo --report /tmp/reverse-editing-demo-init.json
python3 skills/reverse-editing-workflow/scripts/validate_content_layer.py --project-dir samples/fake-corner-noodle
```

When an authorized local video already exists in a project, run local analysis with system `ffmpeg/ffprobe`:

```bash
python3 skills/reverse-editing-workflow/scripts/analyze_reference_video.py --project-dir outputs/<project_id> --force
```

After `analysis/shot_index.reviewed.json` exists, validate continuity and evidence links:

```bash
python3 skills/reverse-editing-workflow/scripts/validate_shot_index.py --project-dir outputs/<project_id>
```

After a project has `analysis/shot_index.reviewed.json`, `storyboard/storyboard.json`, and `previs/previs_plan.json`, render a local low-fidelity previs page:

```bash
python3 skills/reverse-editing-workflow/scripts/render_previs_html.py --project-dir outputs/<project_id> --force
```

## Safety Defaults

Unless explicitly authorized, the workflow should not:

- download a reference video
- run LibTV or remote video generation
- call TTS or voice services
- install OCR
- modify Jianying drafts
- treat dirty in-frame text as formal subtitles
- copy reference-video wording as final copy

## Status

Alpha. Good for intake, project setup, schema validation, editable control-layer checks, static HTML previs, and sample exploration.

Not complete yet:

- full video URL to storyboard/previs automation
- second real-reference forward test
- real LibTV/TTS/OCR/Jianying mutation execution path

## License

MIT
