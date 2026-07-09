# Claude Code Entry

Use this repository as a local-first reverse-editing workflow package.

Before acting, read:

1. `skills/reverse-editing-workflow/SKILL.md`
2. The relevant file in `skills/reverse-editing-workflow/references/`

## Operating Rules

Work in small loops:

- one target
- declared inputs
- concrete actions
- forbidden actions
- acceptance criteria
- checkable artifacts
- validation
- retrospective

## Default Forbidden Actions

Do not perform these unless the user explicitly authorizes the current loop:

- download a URL
- run LibTV or remote video generation
- call TTS or paid voice services
- install OCR dependencies
- modify existing Jianying drafts
- delete, move, or rename user artifacts
- copy reference-video wording as final copy
- treat generated in-frame text as formal subtitles

## First Workflow Step

For a new reference video, create or validate an intake file:

```bash
python3 skills/reverse-editing-workflow/scripts/validate_intake.py --intake <intake.json>
```

Then dry-run project initialization:

```bash
python3 skills/reverse-editing-workflow/scripts/init_project.py --intake <intake.json> --output-root outputs --report outputs/init_dry_run.json
```

Create a real project directory only after the intake is ready and the user agrees.

## Previs Rendering

After `analysis/shot_index.reviewed.json`, `storyboard/storyboard.json`, and `previs/previs_plan.json` exist, generate a local static review page:

```bash
python3 skills/reverse-editing-workflow/scripts/render_previs_html.py --project-dir <project_dir> --force
```

The generated HTML is an internal review artifact only. Do not treat reference frames as publishable media.
