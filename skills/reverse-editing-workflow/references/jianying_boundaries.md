# Jianying Internal Previs Boundaries

## Dynamic slot contract

Derive slot count `N` from the current video's reviewed `jianying_manifest/manifest.plan.json`. Require the plan, asset manifest, QC whitelist, seed materials, timeline segments, clone-local assets, and GUI-loaded segments to agree on the same `N`.

Never hardcode 17. A 17-slot draft is one validated regression case; another video may use 5, 12, 23, or any other reviewed count.

## Default-deny writes

Building and validating a manifest are read-only. Creating/registering a new clone, shifting its timeline, or fitting its media are Jianying writes and require explicit authorization for the current loop.

Every mutation helper requires `--authorize-jianying-write`. Do not add that flag unless the user has authorized the named target and operation.

## Safe clone sequence

1. Build the manifest with `build_jianying_manifest.py`.
2. Read-only validate seed capability with `validate_jianying_seed.py`.
3. Create a new collision-free clone with `clone_jianying_seed.py`, passing the supported seed-validation report.
4. Shift clone segments to reviewed starts with `shift_jianying_timeline.py`, passing the just-created clone report.
5. Pad only short clone-local media with `fit_jianying_clone_slots.py`.
6. Run `validate_jianying_draft.py` before opening the GUI.

Never modify the seed or an existing working draft. The clone helper may register the new clone in `root_meta_info.json`; it must back up root metadata first. Source media hashes must remain unchanged.

## Short-material fitting

If a clip is shorter than its slot, freeze the final frame only in the clone-local copy. Do not extend, trim, transcode, or overwrite the project source. Record before/after duration, source hash, target hash, backup, and fit method.

Longer media may remain unchanged while the timeline consumes only the reviewed duration.

## Editable layers

Copy, voiceover, subtitle, word timing, and audio plans stay outside the draft as source-of-truth files. For the internal previs clone, require:

- `subtitle_inserted_in_this_loop=false`
- `subtitle_burned_in=false`
- `voiceover_audio_inserted_in_this_loop=false`
- `internal_only_policy.publish_ready=false`

## Evidence levels

Keep evidence levels separate:

- `file_level_pass`: paths, hashes, counts, timing, media coverage, root registration, and safety policies pass.
- `gui_user_reported_pass`: a human reports homepage/editor/playback success without stronger captured evidence.
- `gui_screenshot_evidence_pass`: required screenshots support homepage, editor, and end playback.
- `gui_recording_evidence_pass`: a recording supports the playback claim.

GUI acceptance should check homepage visibility, editor open, `N` segments loaded, playback from zero to end, no observed offline-media prompt, and any declared final placeholder. Do not upgrade one evidence level into another.

No file or GUI pass proves publish readiness, subtitle/voiceover completion, export quality, or client delivery.
