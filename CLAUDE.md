# Claude Code Entry

Use this repository as a local-first reverse-editing workflow package.

Before acting, read:

1. `skills/reverse-editing-workflow/SKILL.md`
2. The one relevant file under `skills/reverse-editing-workflow/references/`

## Loop Engineering

Work in bounded loops. Every loop report must contain:

1. 目标
2. 输入
3. 动作
4. 禁止事项
5. 验收标准
6. 产物
7. 验证
8. 复盘
9. 下一轮

Advance through safe local/read-only loops without repeated confirmation. Stop before any action that needs authority the user has not granted.

## Default-deny actions

Do not perform these unless the user explicitly authorizes the current loop:

- download a URL or reference video
- run LibTV or remote video generation
- call TTS, paid voice, or paid OCR
- install OCR, FFmpeg, or other system dependencies
- create, clone, register, or modify a Jianying draft
- delete, move, rename, or overwrite existing user artifacts
- burn subtitles/voiceover into preview media
- copy reference wording as final copy
- upload real media, Jianying drafts, screenshots, project outputs, local paths, account data, secrets, or experiments

## Core route

1. Validate intake and create an independent `project_id` directory.
2. Analyze an already-authorized local source; validate shot boundaries.
3. Produce storyboard/previs.
4. Keep copy, voiceover, subtitle, word timing, and audio plans editable; export VTT/SRT.
5. Run existing local Tesseract plus mandatory human contact-sheet review.
6. Preserve original QC findings; append internal-preview-only override records when explicitly authorized.
7. Record any local placeholder as visibly internal-only and never publish-ready.
8. Derive Jianying slot count `N` from the current video's reviewed plan; never hardcode 17.
9. Validate the seed read-only before any authorized new-clone write.
10. Keep file-level and GUI evidence levels separate, and never describe an internal previs as a publish result.

## Start commands

```bash
python3 skills/reverse-editing-workflow/scripts/validate_intake.py --intake <intake.json>
python3 skills/reverse-editing-workflow/scripts/init_project.py --intake <intake.json> --output-root outputs --report <dry-run-report.json>
```

For an already-authorized local video:

```bash
python3 skills/reverse-editing-workflow/scripts/analyze_reference_video.py --project-dir <project_dir> --force
python3 skills/reverse-editing-workflow/scripts/validate_shot_index.py --project-dir <project_dir>
```

For editable content and review subtitles:

```bash
python3 skills/reverse-editing-workflow/scripts/validate_content_layer.py --project-dir <project_dir>
```

For visual QC:

```bash
python3 skills/reverse-editing-workflow/scripts/visual_ocr_qc.py --project-dir <project_dir>
# Complete manual_visual_review.json after viewing every contact sheet.
python3 skills/reverse-editing-workflow/scripts/validate_visual_qc.py --project-dir <project_dir>
```

Read `SKILL.md` and `references/jianying_boundaries.md` for guarded N-slot Jianying commands. Never add `--authorize-jianying-write` unless the user explicitly authorized that loop and its new draft target.
