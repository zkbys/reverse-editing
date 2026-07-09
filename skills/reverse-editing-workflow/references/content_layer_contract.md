# Content Layer Contract

## Purpose

The content layer keeps copy, voiceover, subtitles, word timing, and audio planning editable before any final render, TTS call, or Jianying import.

## Required Files

- `content/copy_script.json`
- `content/voiceover_script.json`
- `subtitles/subtitle_track.json`
- `subtitles/word_timestamps.json`
- `audio/audio_mix_plan.json`

Schema candidates live in `assets/schemas/`.

## Copy Rules

Copy must be customized per `shot_id`. It should describe the replacement store, owner, product, and shot intent, not copy the original reference wording.

Every shot should be reviewable independently. Missing store facts should be recorded as blockers or placeholders, not filled with invented facts.

## Voiceover Rules

Voiceover text must remain editable in JSON and Markdown review formats. Do not generate audio unless the loop explicitly authorizes TTS or the user provides human-recorded audio.

Estimated timing is allowed only as `estimated_placeholder`. It is not final voiceover alignment.

## Subtitle Rules

Subtitles must follow the voiceover timeline and must export to WebVTT and SRT.

Valid subtitle exports are intermediate artifacts. They do not mean the subtitles should be burned into the video or written into a Jianying draft by default.

## Audio Rules

`audio_mix_plan.json` should separate:

- voiceover track
- original video audio
- background music
- effects or ambience

In MVP loops, set voiceover generation to disabled and record `no_tts_generated_in_mvp=true`.

## Validation

Run the local validator after changing content-layer files:

```bash
python3 scripts/validate_and_export_content_layer.py --project-dir outputs/<project_id> --date-stamp YYYYMMDD
```

Passing validation should confirm schema validity, shot coverage, timing bounds, export readiness, and no-TTS boundaries.
