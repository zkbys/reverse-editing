# Reverse Editing Workflow

Language: [中文](README.md) | English

> A local-first Codex Skill and Claude Code workflow that turns a short-video reference into an editable internal production package.

## What it covers

Each reference gets an isolated `project_id` and a small-loop workflow for:

- intake, local video analysis, and reviewed shot structure
- storyboard and HTML previs
- editable copy, voiceover, subtitle, word-timing, and audio plans
- WebVTT and SRT export
- Tesseract frame OCR plus mandatory human contact-sheet review
- auditable human QC overrides and local non-publish placeholders
- Jianying seed clones with a video-specific dynamic slot count `N`
- clone-local final-frame padding for short media
- distinct file, user-report, screenshot, and screen-recording evidence levels

The validated 17-slot draft is a regression case, not a fixed workflow rule. Every video derives `N` from its own reviewed storyboard/previs plan.

## Install as a Codex Skill

```bash
git clone https://github.com/zkbys/reverse-editing.git
mkdir -p ~/.codex/skills
cp -R reverse-editing/skills/reverse-editing-workflow ~/.codex/skills/
```

Restart Codex, then ask:

```text
Use $reverse-editing-workflow to process this reference as a safe local editable workflow package. Keep download, LibTV, TTS, OCR installation, and Jianying writes disabled until I explicitly authorize the current loop.
```

## Claude Code

Clone the repository, then read:

```text
CLAUDE.md
skills/reverse-editing-workflow/SKILL.md
```

## Local sample

```bash
pip install -r requirements.txt
python3 skills/reverse-editing-workflow/scripts/validate_intake.py \
  --intake samples/fake-corner-noodle/intake.json
python3 skills/reverse-editing-workflow/scripts/init_project.py \
  --intake samples/fake-corner-noodle/intake.json \
  --output-root /tmp/reverse-editing-demo \
  --report /tmp/reverse-editing-demo-init.json
python3 skills/reverse-editing-workflow/scripts/validate_content_layer.py \
  --project-dir samples/fake-corner-noodle --force
```

Run the isolated package smoke test with existing local `ffmpeg/ffprobe`. A missing Tesseract installation is recorded as an OCR gap and is never installed automatically.

```bash
python3 tests/run_clean_package_smoke.py
```

The smoke test installs the Skill into a temporary directory and exercises intake, editable content, visual QC, override auditing, the default-deny Jianying guard, the 17-slot regression, and a dynamic 5-slot case. It never touches a real Jianying directory.

## Default safety boundary

Without explicit authorization for the current loop, do not:

- download a reference video
- run LibTV or remote video generation
- call TTS, paid voice, or paid OCR services
- install OCR or FFmpeg dependencies
- create, register, or modify Jianying drafts
- burn subtitles or voiceover
- upload real/generated media, Jianying drafts, screenshots, project outputs, local paths, account data, secrets, or experiments

OCR, a human override, file validation, or GUI playback can admit an internal preview. None of them creates publish readiness.

## Status

The package has passed a second real-reference forward test plus clean-package regression for both the validated 17-slot case and a non-17 case. The public repository contains only generic Skill files, a fictional sample, and synthetic tests.

## License

MIT
