# Editable Content Layer Contract

## Required source files

- `content/copy_script.json`
- `content/voiceover_script.json`
- `subtitles/subtitle_track.json`
- `subtitles/word_timestamps.json`
- `audio/audio_mix_plan.json`

Keep these files editable and outside rendered video and Jianying. They remain the source of truth even after an internal preview draft exists.

## Copy and voiceover

Customize copy by `shot_id` for the target business. Do not copy reference-video wording as final copy. Record missing facts as blockers or explicit placeholders; do not invent them.

Keep voiceover text editable. Estimated timing must be labeled `estimated_placeholder`. Do not call TTS or generate audio without explicit authorization for the current loop.

## Subtitles and word timing

Follow the voiceover timeline and export both WebVTT and SRT:

```bash
python3 scripts/validate_content_layer.py --project-dir <project_dir>
```

VTT/SRT are review and import artifacts. They do not authorize subtitle burn-in or Jianying insertion. Model-generated in-frame text is a visual QC risk, never subtitle truth.

## Audio plan

Separate voiceover, original audio, music, and effects/ambience. When no audio has been generated, preserve `no_tts_generated_in_mvp=true` and state the missing alignment source.

## Acceptance

Passing validation must prove schema validity, shot coverage/order, positive timing, declared export targets, and the no-TTS boundary. Final voice alignment and audio quality require a later evidence loop.
