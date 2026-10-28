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
