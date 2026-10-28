# Optional runtime recovery

`repositories.json` records the upstream URLs and exact revisions found before
the October 2026 local cleanup. These optional repositories are not needed for
the default Docker/Silero installation.

For an exact source recovery, clone the recorded URL, check out its recorded
commit, and apply the associated patch with `git apply /path/to/file.patch`.
Patches preserve local source changes; they are not a promise that experimental
runtime/model combinations work. Install each upstream project's own dependencies.

The Fish Speech snapshot used a newer, experimental runtime with S2 model folders.
The application's documented S1-mini integration is a separate setup; see
`README_REFERENCE.md`. The default Fish API is a placeholder, not real speech
generation. Python environments and downloaded checkpoints are deliberately not
stored as Git source. ComfyUI's supported portable package and selected video
models remain in the existing GitHub Releases, with manifests in `xtts_api/`.

`comfyui-source-changes.json` lists the only code differences from the published
portable archive: the two bridge modules already stored in this repository.
Reinstall them with `xtts_api/install_comfyui_project_nodes.cmd`; no duplicate
source archive is required.

Optional model recovery sources (checked before cleanup):

- The `1/` folder was the public Fish S1-mini checkpoint layout. Download it
  from https://huggingface.co/fishaudio/s1-mini after accepting that model's
  access conditions with your own Hugging Face account. It is not bundled in
  the basic Audio Studio installer.
- The experimental S2 checkpoint came from
  https://huggingface.co/fishaudio/s2-pro/tree/1de9996b6be38b745688de084d87a5633f714e4e .
  That revision and its files remain available upstream; use the recorded
  revision when recovering the experiment. The folder name `s2-pro-int8`
  alone does not establish that the copied weights were successfully quantized.
