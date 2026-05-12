const FRONTEND_BUILD = "2026-05-12-group-media-workflow-v1";
const REALVISXL_CHECKPOINT = "RealVisXL_V5.0_fp16.safetensors";
const SVD_XT_CHECKPOINT = "svd_xt.safetensors";
const VIDEO_I2V_BACKEND_LABELS = {
  generated_svd: "SVD/SVD-XT",
  generated_animatediff: "AnimateDiff SD1.5",
  generated_hotshotxl: "HotshotXL / AnimateDiff SDXL",
  generated_grok_imagine_video: "Grok Imagine Video",
};
const GROK_IMAGE_MODEL = "grok-2-image";
const IMAGE_QUALITY_PRESETS = {
  fast: { label: "Быстро", vertical: [832, 1216], horizontal: [1216, 832], steps: 16, cfg: 5.5, sampler: "dpmpp_2m_sde", scheduler: "karras" },
  balanced: { label: "Баланс", vertical: [896, 1152], horizontal: [1152, 896], steps: 22, cfg: 6.0, sampler: "dpmpp_2m_sde", scheduler: "karras" },
  quality: { label: "Качество", vertical: [1024, 1536], horizontal: [1536, 1024], steps: 28, cfg: 6.0, sampler: "dpmpp_2m_sde", scheduler: "karras" },
};
const IMAGE_QUALITY_ORDER = ["fast", "balanced", "quality"];
const VIDEO_I2V_QUALITY_PRESETS = {
  fast: { label: "Быстро", frames: 14, fps: 6, motion_bucket_id: 96, augmentation_level: 0.01, min_cfg: 1.0, cfg: 2.0, steps: 12, sampler: "euler", scheduler: "normal" },
  balanced: { label: "Баланс", frames: 25, fps: 6, motion_bucket_id: 104, augmentation_level: 0.01, min_cfg: 1.0, cfg: 2.2, steps: 20, sampler: "euler", scheduler: "normal" },
  quality: { label: "Качество", frames: 49, fps: 8, motion_bucket_id: 140, augmentation_level: 0.02, min_cfg: 1.0, cfg: 3.0, steps: 30, sampler: "euler", scheduler: "normal" },
};
const VIDEO_I2V_QUALITY_ORDER = ["fast", "balanced", "quality"];
const GROK_IMAGINE_VIDEO_RESOLUTION_PRESETS = { fast: "480p", balanced: "720p", quality: "720p" };
const VIDEO_I2V_MOTION_STYLE_PRESETS = {
  object_locked: { label: "Object motion, locked camera", hint: "objects move; camera stays locked", motion_bucket_id: 56, augmentation_level: 0.0, cfg: 1.8, max_frames: 25, max_fps: 6, steps_delta: 0 },
  still_life: { label: "Still life", hint: "minimal drift", motion_bucket_id: 48, augmentation_level: 0.0, cfg: 1.8, max_frames: 25, max_fps: 6, steps_delta: 0 },
  ambient_nature: { label: "Ambient nature", hint: "subtle grass/leaves/water/smoke", motion_bucket_id: 72, augmentation_level: 0.005, cfg: 2.0, max_frames: 25, max_fps: 6, steps_delta: 0 },
  human_subtle: { label: "Human subtle", hint: "very small face/body drift", motion_bucket_id: 64, augmentation_level: 0.005, cfg: 1.9, max_frames: 25, max_fps: 6, steps_delta: 0 },
  cinematic_slow: { label: "Cinematic slow", hint: "controlled slow motion", motion_bucket_id: 96, augmentation_level: 0.01, cfg: 2.2, max_frames: 49, max_fps: 8, steps_delta: 2 },
  landscape_long_loop: { label: "Landscape long loop", hint: "more unique landscape motion, lower steps", motion_bucket_id: 112, augmentation_level: 0.02, cfg: 2.1, max_frames: 49, max_fps: 6, steps_delta: -4 },
};
const TIMELINE_ZOOM_MIN = 0.2;
const TIMELINE_ZOOM_MAX = 640;
const TIMELINE_PAUSE_PRECISION_SEC = 0.01;
const TIMELINE_PAUSE_MIN_SEC = 0;
const TIMELINE_PAUSE_MAX_SEC = 10;
const SPLIT_SENTENCE_PAUSE_MIN_SEC = 0.18;
const SPLIT_SENTENCE_PAUSE_MAX_SEC = 0.35;
const TIMELINE_DEFAULT_VISIBLE_SECONDS = 3600;
const TIMELINE_PANEL_HEIGHT_KEY = "xttsStudioTimelinePanelHeight";
const TIMELINE_PANEL_MIN_HEIGHT = 180;
const TIMELINE_PANEL_MAX_WINDOW_RATIO = 0.7;
const VIDEO_SPEED_DEFAULT = 1.0;
const VIDEO_SPEED_MIN = 0.25;
const VIDEO_SPEED_MAX = 2;
const state = {
  project: null,
  projects: [],
  activeProjectId: "",
  queue: [],
  progress: null,
  health: null,
  pollTimer: null,
  taskStatuses: new Map(),
  refreshingChunks: new Set(),
  sequence: { active: false, audio: null, timer: null, stopAudio: null, runId: 0, status: "Stopped" },
  timeline: { cursorSec: 0, durationSec: 0, arrangement: [], userScrubbing: false, draggingPlayhead: false, pixelsPerSecond: Number(localStorage.getItem("xttsStudioPixelsPerSecond") || 96), minWorkspaceWidth: 1600 },
  pauseDrag: { active: false, chunkId: null, pauseAfter: 0 },
  preview: { ctx: null, sources: [], gains: [], raf: null, runId: 0, startedAtContextTime: 0, startedAtTimelineTime: 0, musicBufferDuration: 0, groupId: "", followPlayhead: true },
  envelope: { selectedIndex: -1, draggingIndex: -1, target: "music" },
  videoSpeed: { selectedIndex: -1, draggingIndex: -1 },
  musicClip: { selectedId: "", draggingId: "", selectedSourceId: "", selectedLaneId: "" },
  chunkNav: { activeId: "", signature: "" },
  sidePanelMode: "chunks",
  screenMode: "projects",
  selectedChunkId: "",
  selectedGroupId: "",
  groupDetail: { signature: "" },
  groupMedia: { selectedId: "", libraryTab: "image" },
  comfyuiStatus: null,
  audioDecodeCache: new Map(),
};

const $ = (id) => document.getElementById(id);

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, Number(value) || 0));
}

function roundTime(value, precision = TIMELINE_PAUSE_PRECISION_SEC) {
  const step = Math.max(0.001, Number(precision) || TIMELINE_PAUSE_PRECISION_SEC);
  return Math.round((Number(value) || 0) / step) * step;
}

function timelinePanelMaxHeight() {
  return Math.max(TIMELINE_PANEL_MIN_HEIGHT, Math.floor((window.innerHeight || 900) * TIMELINE_PANEL_MAX_WINDOW_RATIO));
}

function clampTimelinePanelHeight(value) {
  return clamp(value, TIMELINE_PANEL_MIN_HEIGHT, timelinePanelMaxHeight());
}

function setTimelinePanelHeight(height, { persist = false } = {}) {
  const safeHeight = clampTimelinePanelHeight(height);
  document.documentElement.style.setProperty("--timeline-height", `${safeHeight}px`);
  if (persist) localStorage.setItem(TIMELINE_PANEL_HEIGHT_KEY, String(Math.round(safeHeight)));
  updatePlayheadPosition();
  return safeHeight;
}

function initTimelinePanelResize() {
  const savedHeight = Number(localStorage.getItem(TIMELINE_PANEL_HEIGHT_KEY));
  if (Number.isFinite(savedHeight) && savedHeight > 0) setTimelinePanelHeight(savedHeight);
  else setTimelinePanelHeight(Number(getComputedStyle(document.documentElement).getPropertyValue("--timeline-height").replace("px", "")) || 660);

  const handle = $("timelineResizeHandle");
  const panel = $("timelineTransport");
  if (!handle || !panel) return;
  handle.addEventListener("pointerdown", (event) => {
    if (event.button !== 0) return;
    event.preventDefault();
    const startY = event.clientY;
    const startHeight = panel.getBoundingClientRect().height;
    document.body.classList.add("resizingTimelinePanel");
    handle.setPointerCapture?.(event.pointerId);
    const onMove = (moveEvent) => {
      const nextHeight = startHeight + (startY - moveEvent.clientY);
      setTimelinePanelHeight(nextHeight);
    };
    const onUp = () => {
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerup", onUp);
      document.body.classList.remove("resizingTimelinePanel");
      setTimelinePanelHeight(panel.getBoundingClientRect().height, { persist: true });
    };
    document.addEventListener("pointermove", onMove);
    document.addEventListener("pointerup", onUp, { once: true });
  });
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: options.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = await res.text();
    try { detail = JSON.parse(detail).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

function setStatus(message, busy = false) {
  $("status").textContent = message || "Ready";
  $("status").className = busy ? "busy" : "";
}

function setSequenceStatus(message) {
  state.sequence.status = message || "Stopped";
  const el = $("sequenceStatus");
  if (el) el.textContent = state.sequence.status;
}

function renderProgress() {
  const p = state.progress || { percent: 0, message: "Idle", active: false };
  const fill = $("progressFill");
  const activeTask = (state.queue || []).find((task) => task.status === "running");
  const queuedCount = (state.queue || []).filter((task) => task.status === "queued").length;
  const rawPercent = Number(p.percent || activeTask?.progress_percent || 0);
  const percent = p.active || activeTask ? Math.max(8, rawPercent) : rawPercent;
  fill.style.width = `${percent}%`;
  fill.className = p.active || activeTask ? "active" : "";
  const runningLabel = activeTask ? `${taskDisplayName(activeTask)}${activeTask.chunk_id ? ` · chunk ${chunkNumber(activeTask.chunk_id)}` : ""}` : "";
  $("progressText").textContent = p.active || activeTask
    ? `${p.message || "Working…"}${runningLabel ? ` (${runningLabel})` : ""}${queuedCount ? ` · ${queuedCount} queued` : ""}`
    : (p.message || "Idle");
}

function taskDisplayName(task) {
  if (task?.kind === "grok_groups") return "Grok AI grouping";
  if (task?.kind === "image_group") return "Image generation / Картинка группы";
  if (task?.kind === "video_group") return `${videoBackendLabel()} video generation`;
  if (task?.kind === "generate_chunk") return "Generate chunk";
  if (task?.kind === "export") return "Export";
  return task?.label || task?.kind || "Task";
}

function videoBackendLabel(mode = $("videoI2vWorkflowMode")?.value || state.project?.settings?.video_i2v_workflow_mode || "generated_svd") {
  return VIDEO_I2V_BACKEND_LABELS[String(mode).toLowerCase()] || "SVD/SVD-XT";
}

function syncBulkVideoButtonLabel() {
  const button = $("queueAllVideosBtn");
  if (!button) return;
  const backend = videoBackendLabel();
  const enabled = $("videoI2vEnabled")?.checked ?? state.project?.settings?.video_i2v_enabled ?? false;
  button.textContent = `Generate all ${backend} videos`;
  button.title = enabled
    ? `Queue all missing group videos using the currently selected ${backend} workflow/backend.`
    : `Image-to-video buttons are disabled; enable the ${backend} backend in Video settings first.`;
  button.setAttribute("aria-label", button.textContent);
}

function chunkNumber(chunkId) {
  const chunk = getChunks().find((c) => c.id === chunkId);
  return chunk ? chunk.order + 1 : chunkId;
}

function renderHealth() {
  const h = state.health;
  const warning = $("buildWarning");
  const warningText = $("buildWarningText");
  if (!h) {
    $("buildInfo").textContent = `Frontend ${FRONTEND_BUILD} · backend not checked`;
    $("buildInfo").className = "buildInfo stale";
    if (warning) warning.hidden = true;
    return;
  }
  const mismatch = h.build !== FRONTEND_BUILD;
  const queueOk = h.queue_routes?.["GET /api/queue"]?.available;
  const serverFile = h.server_file ? ` · ${h.server_file}` : "";
  $("buildInfo").textContent = `Frontend ${FRONTEND_BUILD} · Backend ${h.build || "unknown"} · queue ${queueOk ? "OK" : "MISSING"} · pid ${h.pid || "?"}${serverFile}`;
  $("buildInfo").className = mismatch ? "buildInfo stale" : "buildInfo";
  if (warning && warningText) {
    warning.hidden = !mismatch;
    warningText.textContent = mismatch
      ? `Frontend/backend build mismatch detected (frontend ${FRONTEND_BUILD}, backend ${h.build || "unknown"}). Queue polling continues without automatic page reload; use the manual reload button when playback is stopped.`
      : "";
    if (mismatch) console.warn("[XTTS Studio] Frontend/backend build mismatch", { frontendBuild: FRONTEND_BUILD, backendBuild: h.build || "unknown", pid: h.pid || null, serverFile: h.server_file || "" });
  }
}

function renderQueue() {
  const root = $("queueList");
  const tasks = (state.queue && state.queue.length ? state.queue : state.project?.queue) || [];
  if (!tasks.length) {
    root.innerHTML = "No tasks.";
    return;
  }
  root.innerHTML = "";
  for (const task of tasks) {
    const chunk = getChunks().find((c) => c.id === task.chunk_id);
    const label = chunk ? `Chunk ${chunk.order + 1}` : (task.project_id ? `Project ${task.project_id}` : "project");
    const taskPercent = task.progress_percent ?? (task.status === "done" ? 100 : task.status === "running" ? (state.progress?.percent || 15) : 0);
    const stage = task.stage && task.stage !== task.message ? ` · ${task.stage}` : "";
    const item = document.createElement("div");
    item.className = "queueItem";
    item.innerHTML = `
      <span class="statusTag status-${task.status}">${task.status}</span>
      <div>
        <strong>${escapeHtml(taskDisplayName(task))}</strong>
        <small>${escapeHtml(label)} · ${escapeHtml(task.message || "")}${escapeHtml(stage)}</small>
        <div class="taskProgress"><div style="width:${taskPercent}%"></div></div>
      </div>
      <button type="button" class="secondary moveUp">↑</button>
      <button type="button" class="secondary moveDown">↓</button>
      <button type="button" class="secondary removeTask">✕</button>
    `;
    item.querySelector(".moveUp").disabled = task.status !== "queued";
    item.querySelector(".moveDown").disabled = task.status !== "queued";
    item.querySelector(".removeTask").disabled = task.status !== "queued";
    item.querySelector(".moveUp").onclick = () => moveQueueTask(task.id, "up");
    item.querySelector(".moveDown").onclick = () => moveQueueTask(task.id, "down");
    item.querySelector(".removeTask").onclick = () => removeQueueTask(task.id);
    root.appendChild(item);
  }
}

function isFinishedTask(task) {
  return ["done", "failed", "cancelled", "succeeded", "success", "error"].includes(task?.status);
}

function fieldValue(id, fallback = "") {
  const el = $(id);
  return el ? el.value : fallback;
}

function trimmedFieldValue(id, fallback = "") {
  return String(fieldValue(id, fallback)).trim();
}

function numericFieldValue(id, fallback = 0) {
  const value = fieldValue(id, fallback);
  const number = Number(value);
  return Number.isFinite(number) ? number : Number(fallback) || 0;
}

function settingsPayload() {
  const quality = selectedImageQualityPreset();
  const videoQuality = selectedVideoI2vQualityPreset();
  const aspect = $("imageAspectRatio")?.value || "vertical";
  const resolved = resolvedImagePreset(quality, aspect);
  const videoResolved = resolvedVideoI2vPreset(videoQuality);
  const imageProviderModel = window.XTTSStudio?.SettingsHelpers?.normalizeImageProviderModel?.(
    $("imageProvider")?.value || state.project?.settings?.image_provider || "comfyui",
    $("imageModel")?.value || state.project?.settings?.image_model || "realvisxl",
    { preferProvider: true },
  ) || { provider: $("imageProvider")?.value || "comfyui", model: $("imageModel")?.value || "realvisxl" };
  const payload = {
    reference_path: trimmedFieldValue("referencePath"),
    music_path: trimmedFieldValue("musicPath"),
    voice_volume: numericFieldValue("voiceVolume", 1),
    music_volume: numericFieldValue("musicVolume", 0.18),
    image_provider: imageProviderModel.provider,
    image_model: imageProviderModel.model,
    image_grok_model: $("imageGrokModel")?.value?.trim() || GROK_IMAGE_MODEL,
    image_quality_preset: quality,
    image_aspect_ratio: aspect,
    image_width: Number($("imageWidth")?.value || resolved.width),
    image_height: Number($("imageHeight")?.value || resolved.height),
    image_style_preset: $("imageStylePreset")?.value?.trim() || "sleep_documentary",
    image_comfyui_url: $("imageComfyuiUrl")?.value?.trim() || "http://127.0.0.1:8188",
    image_comfyui_path: $("imageComfyuiPath")?.value?.trim() || "ComfyUI_windows_portable",
    image_comfyui_python: $("imageComfyuiPython")?.value?.trim() || "",
    image_comfyui_launch_cmd: $("imageComfyuiLaunchCmd")?.value?.trim() || "",
    image_comfyui_autostart: Boolean($("imageComfyuiAutostart")?.checked),
    image_workflow_mode: $("imageWorkflowMode")?.value || "generated",
    image_workflow_path: $("imageWorkflowPath")?.value?.trim() || "",
    image_model_checkpoint: $("imageModelCheckpoint")?.value?.trim() || REALVISXL_CHECKPOINT,
    image_steps: Number($("imageSteps")?.value || resolved.steps),
    image_cfg: Number($("imageCfg")?.value || resolved.cfg),
    image_sampler: $("imageSampler")?.value?.trim() || resolved.sampler,
    image_scheduler: $("imageScheduler")?.value?.trim() || resolved.scheduler,
    image_negative_preset: $("imageNegativePreset")?.value?.trim() || "default",
    image_exclude_people: Boolean($("imageExcludePeople")?.checked),
    image_seed: Number($("imageSeed")?.value || 0),
    video_i2v_enabled: Boolean($("videoI2vEnabled")?.checked),
    video_i2v_quality_preset: videoQuality,
    video_i2v_motion_style: selectedVideoI2vMotionStyle(),
    video_i2v_workflow_mode: $("videoI2vWorkflowMode")?.value || "generated_svd",
    video_i2v_model_checkpoint: $("videoI2vModelCheckpoint")?.value?.trim() || SVD_XT_CHECKPOINT,
    video_i2v_grok_model: $("videoI2vGrokModel")?.value?.trim() || "grok-imagine-video",
    video_i2v_grok_duration_sec: clamp($("videoI2vGrokDurationSec")?.value || 5, 1, 30),
    video_i2v_grok_resolution: $("videoI2vGrokResolution")?.value || GROK_IMAGINE_VIDEO_RESOLUTION_PRESETS[videoQuality] || "480p",
    video_i2v_grok_aspect_ratio_mode: $("videoI2vGrokAspectRatioMode")?.value || "auto",
    video_i2v_grok_loop_postprocess: $("videoI2vGrokLoopPostprocess")?.value || "pingpong",
    video_i2v_grok_crossfade_sec: clamp($("videoI2vGrokCrossfadeSec")?.value || 0.5, 0.1, 2),
    video_i2v_frames: Number($("videoI2vFrames")?.value || videoResolved.frames),
    video_i2v_fps: Number($("videoI2vFps")?.value || videoResolved.fps),
    video_i2v_motion_bucket_id: Number($("videoI2vMotionBucketId")?.value || videoResolved.motion_bucket_id),
    video_i2v_augmentation_level: Number($("videoI2vAugmentationLevel")?.value || videoResolved.augmentation_level),
    video_i2v_min_cfg: Number($("videoI2vMinCfg")?.value || videoResolved.min_cfg),
    video_i2v_cfg: Number($("videoI2vCfg")?.value || videoResolved.cfg),
    video_i2v_steps: Number($("videoI2vSteps")?.value || videoResolved.steps),
    video_i2v_sampler: $("videoI2vSampler")?.value?.trim() || videoResolved.sampler,
    video_i2v_scheduler: $("videoI2vScheduler")?.value?.trim() || videoResolved.scheduler,
    video_i2v_pingpong: Boolean($("videoI2vPingpong")?.checked ?? true),
    video_i2v_target_duration_sec: clamp($("videoI2vTargetDurationSec")?.value || 20, 2, 60),
    video_i2v_preview_playback_rate: clamp($("videoI2vPreviewPlaybackRate")?.value || 1, 0.25, 2),
    tts_backend: $("ttsBackend")?.value || "xtts",
    tts_pronunciation_preprocess_enabled: Boolean($("ttsPronunciationPreprocessEnabled")?.checked ?? true),
    tts_pronunciation_dictionary_path: $("ttsPronunciationDictionaryPath")?.value?.trim() || "xtts_api/pronunciation_dictionary.json",
    tts_stress_mark_style: $("ttsStressMarkStyle")?.value || "acute",
    silero_api_url: $("sileroApiUrl")?.value?.trim() || "http://127.0.0.1:7866",
    silero_speaker: $("sileroSpeaker")?.value?.trim() || "baya",
    silero_sample_rate: Number($("sileroSampleRate")?.value || 48000),
    silero_realism_enabled: Boolean($("sileroRealismEnabled")?.checked ?? true),
    silero_realism_preset: $("sileroRealismPreset")?.value?.trim() || "sleep_safe",
    ai_add_russian_stress_marks: Boolean($("aiAddRussianStressMarks")?.checked),
    ai_stress_model: $("aiStressModel")?.value?.trim() || "",
    ai_generate_group_prompts_on_split: Boolean($("aiGenerateGroupPromptsOnSplit")?.checked ?? true),
  };
  const xaiInput = $("xaiApiKey");
  const clearXai = $("clearXaiApiKey");
  if (clearXai?.checked) {
    payload.xai_api_key = "";
  } else if (xaiInput?.value?.trim()) {
    payload.xai_api_key = xaiInput.value.trim();
  }
  return payload;
}

function selectedImageQualityPreset() {
  const slider = $("imageQualityPreset");
  const raw = state.project?.settings?.image_quality_preset || "balanced";
  if (slider && document.activeElement === slider) return IMAGE_QUALITY_ORDER[clamp(slider.value, 0, 2)] || "balanced";
  if (IMAGE_QUALITY_PRESETS[$("imageQualityPreset")?.dataset?.quality || ""]) return $("imageQualityPreset").dataset.quality;
  return IMAGE_QUALITY_PRESETS[raw] ? raw : "balanced";
}

function resolvedImagePreset(quality = selectedImageQualityPreset(), aspect = $("imageAspectRatio")?.value || "vertical") {
  const preset = IMAGE_QUALITY_PRESETS[quality] || IMAGE_QUALITY_PRESETS.balanced;
  const size = preset[aspect === "horizontal" ? "horizontal" : "vertical"];
  return { quality, label: preset.label, width: size[0], height: size[1], steps: preset.steps, cfg: preset.cfg, sampler: preset.sampler, scheduler: preset.scheduler };
}

function setImageQualityPreset(quality, { updateFields = true } = {}) {
  const safeQuality = IMAGE_QUALITY_PRESETS[quality] ? quality : "balanced";
  const slider = $("imageQualityPreset");
  if (slider) {
    slider.value = String(IMAGE_QUALITY_ORDER.indexOf(safeQuality));
    slider.dataset.quality = safeQuality;
  }
  document.querySelectorAll(".imageQualityButton").forEach((button) => {
    button.classList.toggle("active", button.dataset.quality === safeQuality);
    button.classList.toggle("secondary", button.dataset.quality !== safeQuality);
  });
  const label = $("imageQualityLabel");
  if (label) label.textContent = IMAGE_QUALITY_PRESETS[safeQuality].label;
  if (updateFields) updateResolvedImageSettingsHint();
}

function updateResolvedImageSettingsHint() {
  const resolved = resolvedImagePreset();
  const hint = $("imageResolvedSettings");
  const provider = $("imageProvider")?.value || state.project?.settings?.image_provider || "comfyui";
  const model = $("imageModel")?.value || state.project?.settings?.image_model || "realvisxl";
  const isGrok = [provider, model].some((value) => String(value || "").toLowerCase() === "grok");
  if (hint) hint.textContent = isGrok
    ? `Grok/xAI image API · ${$("imageGrokModel")?.value || GROK_IMAGE_MODEL} · ${resolved.label} sizing hint ${resolved.width}×${resolved.height}`
    : `RealVisXL · ${resolved.label} · ${resolved.width}×${resolved.height} · ${resolved.steps} steps · CFG ${resolved.cfg}`;
  const active = document.activeElement;
  const setValue = (id, value) => { const el = $(id); if (el && active !== el) el.value = String(value); };
  setValue("imageWidth", resolved.width);
  setValue("imageHeight", resolved.height);
  setValue("imageSteps", resolved.steps);
  setValue("imageCfg", resolved.cfg);
  setValue("imageSampler", resolved.sampler);
  setValue("imageScheduler", resolved.scheduler);
  if (!isGrok) setValue("imageModelCheckpoint", REALVISXL_CHECKPOINT);
}

function selectedVideoI2vQualityPreset() {
  const slider = $("videoI2vQualityPreset");
  const raw = state.project?.settings?.video_i2v_quality_preset || "balanced";
  if (slider && document.activeElement === slider) return VIDEO_I2V_QUALITY_ORDER[clamp(slider.value, 0, 2)] || "balanced";
  if (VIDEO_I2V_QUALITY_PRESETS[$("videoI2vQualityPreset")?.dataset?.quality || ""]) return $("videoI2vQualityPreset").dataset.quality;
  return VIDEO_I2V_QUALITY_PRESETS[raw] ? raw : "balanced";
}

function selectedVideoI2vMotionStyle() {
  const raw = $("videoI2vMotionStyle")?.value || state.project?.settings?.video_i2v_motion_style || "ambient_nature";
  return VIDEO_I2V_MOTION_STYLE_PRESETS[raw] ? raw : "ambient_nature";
}

function resolvedVideoI2vPreset(quality = selectedVideoI2vQualityPreset(), motionStyle = selectedVideoI2vMotionStyle()) {
  const preset = VIDEO_I2V_QUALITY_PRESETS[quality] || VIDEO_I2V_QUALITY_PRESETS.balanced;
  const style = VIDEO_I2V_MOTION_STYLE_PRESETS[motionStyle] || VIDEO_I2V_MOTION_STYLE_PRESETS.ambient_nature;
  return {
    quality,
    motionStyle,
    ...preset,
    style_label: style.label,
    style_hint: style.hint,
    frames: Math.min(preset.frames, style.max_frames || preset.frames),
    fps: Math.min(preset.fps, style.max_fps || preset.fps),
    motion_bucket_id: style.motion_bucket_id,
    augmentation_level: style.augmentation_level,
    cfg: style.cfg,
    steps: Math.max(1, preset.steps + (style.steps_delta || 0)),
  };
}

function setVideoI2vQualityPreset(quality, { updateFields = true } = {}) {
  const safeQuality = VIDEO_I2V_QUALITY_PRESETS[quality] ? quality : "balanced";
  const slider = $("videoI2vQualityPreset");
  if (slider) {
    slider.value = String(VIDEO_I2V_QUALITY_ORDER.indexOf(safeQuality));
    slider.dataset.quality = safeQuality;
  }
  document.querySelectorAll(".videoI2vQualityButton").forEach((button) => {
    button.classList.toggle("active", button.dataset.quality === safeQuality);
    button.classList.toggle("secondary", button.dataset.quality !== safeQuality);
  });
  const label = $("videoI2vQualityLabel");
  if (label) label.textContent = VIDEO_I2V_QUALITY_PRESETS[safeQuality].label;
  if (updateFields) updateResolvedVideoI2vSettingsHint();
}

function syncGrokImagineVideoSettingsUi(workflowMode = $("videoI2vWorkflowMode")?.value || state.project?.settings?.video_i2v_workflow_mode || "generated_svd") {
  const selected = workflowMode === "generated_grok_imagine_video";
  const panel = $("videoI2vGrokSettings");
  if (panel) {
    panel.classList.toggle("active", selected);
    panel.classList.toggle("inactive", !selected);
    panel.setAttribute("aria-disabled", selected ? "false" : "true");
  }
  for (const id of ["videoI2vGrokModel", "videoI2vGrokDurationSec", "videoI2vGrokResolution", "videoI2vGrokAspectRatioMode", "videoI2vGrokLoopPostprocess", "videoI2vGrokCrossfadeSec"]) {
    const el = $(id);
    if (el) el.disabled = !selected;
  }
  const hint = $("videoI2vGrokEnableHint");
  if (hint) hint.textContent = selected
    ? "Grok Imagine Video is selected. Save settings, then use group video buttons to queue hosted xAI generation. Downloaded clips are ffmpeg loop-processed by default."
    : "To enable: select “Grok Imagine Video (xAI API)” in the Workflow / video backend dropdown above, then Save settings. Uses the project Grok/xAI API key or XAI_API_KEY.";
}

function updateResolvedVideoI2vSettingsHint() {
  const resolved = resolvedVideoI2vPreset();
  const workflowMode = $("videoI2vWorkflowMode")?.value || state.project?.settings?.video_i2v_workflow_mode || "generated_svd";
  const backend = videoBackendLabel(workflowMode);
  const grokResolution = $("videoI2vGrokResolution")?.value || state.project?.settings?.video_i2v_grok_resolution || GROK_IMAGINE_VIDEO_RESOLUTION_PRESETS[resolved.quality] || "480p";
  const grokDuration = clamp($("videoI2vGrokDurationSec")?.value || state.project?.settings?.video_i2v_grok_duration_sec || 5, 1, 30);
  const grokAspectMode = $("videoI2vGrokAspectRatioMode")?.value || state.project?.settings?.video_i2v_grok_aspect_ratio_mode || "auto";
  const grokLoopMode = $("videoI2vGrokLoopPostprocess")?.value || state.project?.settings?.video_i2v_grok_loop_postprocess || "pingpong";
  const targetDuration = clamp($("videoI2vTargetDurationSec")?.value || state.project?.settings?.video_i2v_target_duration_sec || 20, 2, 60);
  const pingpong = $("videoI2vPingpong")?.checked !== false;
  const baseFrames = pingpong && resolved.frames > 1 ? resolved.frames * 2 - 2 : resolved.frames;
  const baseDuration = baseFrames / Math.max(1, resolved.fps);
  const repeats = Math.max(1, Math.ceil(targetDuration / Math.max(0.001, baseDuration)));
  const hint = $("videoI2vResolvedSettings");
  const uniqueSeconds = resolved.frames / Math.max(1, resolved.fps);
  const uniqueNote = resolved.motionStyle === "landscape_long_loop" ? " · more unique landscape mode trades speed/quality for fewer visible repeats" : "";
  const animatediffNote = workflowMode === "generated_animatediff" ? " · SD1.5 experimental: use only with an SD1.5 checkpoint/motion model; SDXL RealVisXL fidelity can drop" : "";
  const hotshotNote = workflowMode === "generated_hotshotxl" ? " · SDXL/HotshotXL experimental: requires an SDXL motion model in animatediff_models and more VRAM; diagnostics endpoint reports blockers" : "";
  const grokNote = workflowMode === "generated_grok_imagine_video" ? ` · hosted xAI image-to-video · ${grokDuration}s · ${grokResolution} · aspect ${grokAspectMode} (auto: 16:9 landscape, 9:16 portrait) · loop postprocess ${grokLoopMode} · uses project Grok/xAI key · paid API call when queued` : "";
  if (hint) hint.textContent = workflowMode === "generated_grok_imagine_video"
    ? `${backend} enabled via Workflow / video backend dropdown · Save settings, then use group video buttons · ${resolved.label}${grokNote}`
    : `${backend} · ${resolved.label} · ${resolved.style_label} (${resolved.style_hint}) · ${resolved.frames} sampled frames (~${uniqueSeconds.toFixed(1)}s raw) · ${resolved.fps} fps · ~${targetDuration}s output via ${repeats > 1 ? `${repeats} ${pingpong ? "ping-pong repeats" : "repeats"}` : "single loop"} · ${resolved.steps} steps · motion ${resolved.motion_bucket_id} · aug ${resolved.augmentation_level} · CFG ${resolved.cfg}${uniqueNote}${animatediffNote}${hotshotNote}`;
  syncGrokImagineVideoSettingsUi(workflowMode);
  syncBulkVideoButtonLabel();
  const active = document.activeElement;
  const setValue = (id, value) => { const el = $(id); if (el && active !== el) el.value = String(value); };
  setValue("videoI2vFrames", resolved.frames);
  setValue("videoI2vFps", resolved.fps);
  setValue("videoI2vMotionBucketId", resolved.motion_bucket_id);
  setValue("videoI2vAugmentationLevel", resolved.augmentation_level);
  setValue("videoI2vMinCfg", resolved.min_cfg);
  setValue("videoI2vCfg", resolved.cfg);
  setValue("videoI2vSteps", resolved.steps);
  setValue("videoI2vSampler", resolved.sampler);
  setValue("videoI2vScheduler", resolved.scheduler);
  if (workflowMode === "generated_svd") setValue("videoI2vModelCheckpoint", SVD_XT_CHECKPOINT);
  if (workflowMode === "generated_hotshotxl") setValue("videoI2vModelCheckpoint", REALVISXL_CHECKPOINT);
  if (workflowMode === "generated_grok_imagine_video") {
    setValue("videoI2vGrokModel", "grok-imagine-video");
    setValue("videoI2vGrokDurationSec", grokDuration);
    setValue("videoI2vGrokResolution", grokResolution);
    setValue("videoI2vGrokAspectRatioMode", grokAspectMode);
    setValue("videoI2vGrokLoopPostprocess", grokLoopMode);
  }
  const speed = $("videoI2vPreviewPlaybackRate");
  const speedValue = $("videoI2vPreviewPlaybackRateValue");
  if (speed && speedValue) speedValue.textContent = `${Number(speed.value || 1).toFixed(2)}×`;
}

function activeProjectQuery() {
  return state.activeProjectId ? `?project_id=${encodeURIComponent(state.activeProjectId)}` : "";
}

async function saveSettings() {
  state.project = await api(`/api/project/settings${activeProjectQuery()}`, { method: "POST", body: JSON.stringify(settingsPayload()) });
  if ($("xaiApiKey")) $("xaiApiKey").value = "";
  if ($("clearXaiApiKey")) $("clearXaiApiKey").checked = false;
  render();
}

function musicArrangement() {
  const music = state.project?.arrangement?.music || {};
  const legacyPath = state.project?.settings?.music_path || "";
  const sources = (Array.isArray(music.sources) ? music.sources : [])
    .map((source, index) => ({
      id: source.id || `source_${index}_${Math.random().toString(16).slice(2)}`,
      path: source.path || "",
      label: source.label || shortPath(source.path || `Music source ${index + 1}`),
      duration: Number(source.duration || 0) || undefined,
    }))
    .filter((source) => source.path);
  const hasExplicitLanes = Array.isArray(music.lanes);
  if (!hasExplicitLanes && legacyPath && !sources.some((source) => source.path === legacyPath)) {
    sources.push({ id: "legacy_music", path: legacyPath, label: shortPath(legacyPath) });
  }
  const sourceById = new Map(sources.map((source) => [source.id, source]));
  const sourceByPath = new Map(sources.map((source) => [source.path, source]));
  const legacyTracks = (Array.isArray(music.tracks) && music.tracks.length
    ? music.tracks
    : (!hasExplicitLanes && legacyPath ? [{ id: crypto.randomUUID?.() || String(Date.now()), source_id: sourceByPath.get(legacyPath)?.id || "legacy_music", path: legacyPath, start_time: 0, offset_sec: 0, volume: 1, label: shortPath(legacyPath) }] : []))
    .map((track, index) => ({
      source_id: track.source_id || sourceByPath.get(track.path || legacyPath || "")?.id || "",
      id: track.id || `clip_${index}_${Math.random().toString(16).slice(2)}`,
      path: track.path || sourceById.get(track.source_id || "")?.path || legacyPath || "",
      label: track.label || sourceById.get(track.source_id || "")?.label || shortPath(track.path || legacyPath || `Music clip ${index + 1}`),
      start_time: clamp(track.start_time ?? track.offset ?? 0, 0, Math.max(0, state.timeline.durationSec || 0)),
      offset_sec: clamp(track.offset_sec ?? 0, 0, 999999),
      duration_sec: clamp(track.duration_sec ?? track.duration ?? 0, 0, 999999),
      volume: clamp(track.volume ?? 1, 0, 2),
    }));
  const lanes = (hasExplicitLanes
    ? music.lanes
    : groupTracksIntoLanes(legacyTracks))
    .map((lane, index) => normalizeMusicLane(lane, index, sources))
    .filter((lane) => lane.path);
  const tracks = flattenMusicLanes(lanes);
  return {
    mode: ["loop", "once", "chain_loop"].includes(music.mode) ? music.mode : "loop",
    volume_envelope: Array.isArray(music.volume_envelope) ? music.volume_envelope : [],
    sources,
    lanes,
    tracks,
  };
}

function normalizeMusicClip(clip, index = 0) {
  return {
    id: clip.id || crypto.randomUUID?.() || `clip_${Date.now()}_${index}`,
    start_time: clamp(clip.start_time ?? clip.offset ?? 0, 0, Math.max(0, state.timeline.durationSec || clip.start_time || 0)),
    offset_sec: clamp(clip.offset_sec ?? 0, 0, 999999),
    duration_sec: clamp(clip.duration_sec ?? clip.duration ?? 0, 0, 999999),
    volume: clamp(clip.volume ?? 1, 0, 2),
  };
}

function normalizeMusicLane(lane, index = 0, sources = musicArrangement().sources) {
  const source = sources.find((item) => item.id === lane.source_id || item.path === lane.path) || {};
  const path = lane.path || source.path || "";
  const laneVolume = clamp(lane.volume ?? 1, 0, 2);
  return {
    id: lane.id || crypto.randomUUID?.() || `lane_${Date.now()}_${index}`,
    source_id: lane.source_id || source.id || "",
    path,
    label: lane.label || source.label || shortPath(path || `Music lane ${index + 1}`),
    enabled: lane.enabled !== false,
    loop: Boolean(lane.loop),
    volume: laneVolume,
    volume_envelope: normalizeLaneEnvelope(lane.volume_envelope),
    order: Number.isFinite(Number(lane.order)) ? Number(lane.order) : index,
    clips: (Array.isArray(lane.clips) ? lane.clips : []).map(normalizeMusicClip),
  };
}

function normalizeLaneEnvelope(points, fallbackVolume = 1) {
  const duration = Math.max(0, state.timeline.durationSec || 0);
  const cleaned = (Array.isArray(points) ? points : [])
    .map((point) => ({ time: clamp(point?.time ?? 0, 0, duration), volume: clamp(point?.volume ?? fallbackVolume, 0, 2) }))
    .sort((a, b) => a.time - b.time);
  return cleaned.length ? cleaned : [{ time: 0, volume: 1 }];
}

function groupTracksIntoLanes(tracks) {
  const grouped = new Map();
  tracks.forEach((track) => {
    const key = `${track.source_id || ""}|${track.path || ""}`;
    if (!grouped.has(key)) grouped.set(key, { id: crypto.randomUUID?.() || `lane_${Date.now()}_${grouped.size}`, source_id: track.source_id, path: track.path, label: track.label || shortPath(track.path), enabled: true, loop: false, volume: 1, volume_envelope: [{ time: 0, volume: 1 }], order: grouped.size, clips: [] });
    grouped.get(key).clips.push(normalizeMusicClip(track));
  });
  return [...grouped.values()];
}

function flattenMusicLanes(lanes) {
  return lanes.flatMap((lane) => lane.clips.map((clip) => ({ ...clip, source_id: lane.source_id, path: lane.path, label: lane.label, lane_id: lane.id, volume: clip.volume })));
}

function ensureProjectArrangement() {
  state.project.arrangement = state.project.arrangement || {};
  state.project.arrangement.music = state.project.arrangement.music || {};
  state.project.arrangement.voice = state.project.arrangement.voice || {};
  return state.project.arrangement;
}

function voiceArrangement() {
  const voice = state.project?.arrangement?.voice || {};
  return { volume_envelope: Array.isArray(voice.volume_envelope) ? voice.volume_envelope : [{ time: 0, volume: 1 }] };
}

function videoArrangement() {
  const video = state.project?.arrangement?.video || {};
  return { ...video, speed_envelope: Array.isArray(video.speed_envelope) ? video.speed_envelope : [{ time: 0, speed: VIDEO_SPEED_DEFAULT }] };
}

function normalizeGroupMediaItems(group) {
  const items = Array.isArray(group?.media_items) ? group.media_items.slice() : [];
  const addLegacy = (meta, type, label) => {
    if (!meta || !(meta.path || meta.url)) return;
    const key = meta.path || meta.url;
    if (items.some((item) => (item.path || item.url || item.id) === key)) return;
    items.push({ id: `legacy_${type}`, type, path: meta.path || "", url: meta.url || "", label, role: "background", start_offset_sec: 0, duration_sec: Number(meta.duration_sec || 0), fit: "cover" });
  };
  addLegacy(group?.image, "image", "Generated image");
  addLegacy(group?.video, "video", "Generated video");
  return items.map((item, index) => ({
    id: item.id || `media_${Date.now()}_${index}`,
    type: ["image", "video"].includes(item.type) ? item.type : (String(item.path || item.url || "").match(/\.(mp4|webm|gif|mov)$/i) ? "video" : "image"),
    path: item.path || "",
    url: item.url || "",
    label: item.label || shortPath(item.path || item.url || `Media ${index + 1}`),
    role: item.role || "main",
    start_offset_sec: clamp(item.start_offset_sec ?? 0, 0, 36000),
    duration_sec: clamp(item.duration_sec ?? 0, 0, 36000),
    fit: ["cover", "contain", "fill"].includes(item.fit) ? item.fit : "cover",
    volume: item.volume === undefined || item.volume === null ? undefined : clamp(item.volume, 0, 2),
    order: index,
  }));
}

function persistedVideoSpeedEnvelope() {
  const duration = Math.max(0, state.timeline.durationSec || 0);
  const raw = videoArrangement().speed_envelope;
  const points = (Array.isArray(raw) ? raw : [])
    .map((point) => ({ time: clamp(point.time, 0, duration), speed: clamp(point.speed ?? point.playback_rate ?? VIDEO_SPEED_DEFAULT, VIDEO_SPEED_MIN, VIDEO_SPEED_MAX) }))
    .sort((a, b) => a.time - b.time);
  return points.length ? points : [{ time: 0, speed: VIDEO_SPEED_DEFAULT }];
}

function effectiveVideoSpeedEnvelope() {
  const duration = Math.max(0, state.timeline.durationSec || 0);
  const points = persistedVideoSpeedEnvelope().map((point) => ({ ...point })).sort((a, b) => a.time - b.time);
  if (!points.length) points.push({ time: 0, speed: VIDEO_SPEED_DEFAULT });
  if (points[0].time > 0.001) points.unshift({ time: 0, speed: points[0].speed });
  if (duration > 0 && points[points.length - 1].time < duration - 0.001) points.push({ time: duration, speed: points[points.length - 1].speed });
  return points;
}

function videoSpeedAt(timeSec) {
  const points = effectiveVideoSpeedEnvelope();
  const time = clamp(timeSec, 0, state.timeline.durationSec || 0);
  for (let i = 1; i < points.length; i += 1) {
    const prev = points[i - 1];
    const next = points[i];
    if (time <= next.time) {
      const ratio = clamp((time - prev.time) / Math.max(0.0001, next.time - prev.time), 0, 1);
      return prev.speed + (next.speed - prev.speed) * ratio;
    }
  }
  return points[points.length - 1]?.speed ?? VIDEO_SPEED_DEFAULT;
}

function applyPreviewVideoPlaybackRate() {
  const previewVideo = $("previewVideo");
  if (!previewVideo) return;
  previewVideo.playbackRate = clamp(videoSpeedAt(state.timeline.cursorSec), VIDEO_SPEED_MIN, VIDEO_SPEED_MAX);
}

function persistedEnvelope(target = "music") {
  const duration = Math.max(0, state.timeline.durationSec || 0);
  const lane = laneFromEnvelopeTarget(target);
  const raw = lane ? lane.volume_envelope : (target === "voice" ? voiceArrangement().volume_envelope : musicArrangement().volume_envelope);
  const base = lane || target === "voice" ? 1 : Number(state.project?.settings?.music_volume ?? $("musicVolume")?.value ?? 0.18);
  const points = (Array.isArray(raw) ? raw : [])
    .map((point) => ({ time: clamp(point.time, 0, duration), volume: clamp(point.volume, 0, 2) }))
    .sort((a, b) => a.time - b.time);
  return points.length ? points : [{ time: 0, volume: base }];
}

function laneTarget(laneId) { return `lane:${laneId}`; }

function isLaneEnvelopeTarget(target) { return String(target || "").startsWith("lane:"); }

function laneIdFromEnvelopeTarget(target) { return isLaneEnvelopeTarget(target) ? String(target).slice(5) : ""; }

function laneFromEnvelopeTarget(target) {
  const laneId = laneIdFromEnvelopeTarget(target);
  return laneId ? musicArrangement().lanes.find((lane) => lane.id === laneId) || null : null;
}

function envelopeTargetLabel(target = "music") {
  if (target === "voice") return "voice";
  if (target === "music") return "music master";
  const lane = laneFromEnvelopeTarget(target);
  return lane ? `lane ${lane.label || shortPath(lane.path)}` : "lane";
}

function effectiveEnvelope(target = "music") {
  const duration = Math.max(0, state.timeline.durationSec || 0);
  const points = persistedEnvelope(target).map((point) => ({ ...point })).sort((a, b) => a.time - b.time);
  if (!points.length) points.push({ time: 0, volume: target === "voice" ? 1 : Number(state.project?.settings?.music_volume ?? 0.18) });
  if (points[0].time > 0.001) points.unshift({ time: 0, volume: points[0].volume });
  if (duration > 0 && points[points.length - 1].time < duration - 0.001) points.push({ time: duration, volume: points[points.length - 1].volume });
  return points;
}

function envelopeValueAt(target, timeSec) {
  const points = effectiveEnvelope(target);
  const time = clamp(timeSec, 0, state.timeline.durationSec || 0);
  for (let i = 1; i < points.length; i += 1) {
    const prev = points[i - 1];
    const next = points[i];
    if (time <= next.time) {
      const ratio = clamp((time - prev.time) / Math.max(0.0001, next.time - prev.time), 0, 1);
      return prev.volume + (next.volume - prev.volume) * ratio;
    }
  }
  return points[points.length - 1]?.volume ?? 1;
}

function effectiveMusicEnvelope() {
  return effectiveEnvelope("music");
}

function persistedMusicEnvelope() {
  return persistedEnvelope("music");
}

function musicVolumeAt(timeSec) {
  return envelopeValueAt("music", timeSec);
}

function envelopeBreakpointsInSpan(start, end, ...pointSets) {
  const byTime = new Map();
  const addTime = (time) => {
    const safe = roundTime(clamp(time, start, end), 0.001);
    byTime.set(safe.toFixed(3), safe);
  };
  addTime(start);
  addTime(end);
  pointSets.flat().forEach((point) => {
    const time = Number(point?.time);
    if (Number.isFinite(time) && time >= start && time <= end) addTime(time);
  });
  return [...byTime.values()].sort((a, b) => a - b);
}

function laneEnvelopeValueAt(lane, timeSec) {
  const points = normalizeLaneEnvelope(lane?.volume_envelope);
  const time = clamp(timeSec, 0, state.timeline.durationSec || 0);
  for (let i = 1; i < points.length; i += 1) {
    const prev = points[i - 1];
    const next = points[i];
    if (time <= next.time) {
      const ratio = clamp((time - prev.time) / Math.max(0.0001, next.time - prev.time), 0, 1);
      return prev.volume + (next.volume - prev.volume) * ratio;
    }
  }
  return points[points.length - 1]?.volume ?? 1;
}

function voiceAutomationAt(timeSec) { return envelopeValueAt("voice", timeSec); }

async function saveMusicArrangement(patch = {}) {
  const payload = patch && typeof patch === "object" ? { ...patch } : {};
  state.project = await api(`/api/project/arrangement/music${activeProjectQuery()}`, { method: "POST", body: JSON.stringify(payload) });
  if (patch.mode) setStatus(`Music mode saved: ${payload.mode}`);
  if (patch.volume_envelope) setStatus("Music automation saved");
  render();
}

function saveFullMusicArrangement() {
  return saveMusicArrangement(musicArrangement());
}

function defaultMusicEnvelopePoint() {
  return { time: 0, volume: Number(state.project?.settings?.music_volume ?? $("musicVolume")?.value ?? 0.18) };
}

function resetMusicEnvelope() {
  state.envelope.selectedIndex = -1;
  state.envelope.target = "music";
  saveMusicArrangement({ volume_envelope: [defaultMusicEnvelopePoint()] }).catch((err) => setStatus(`Music automation reset failed: ${err.message}`));
}

function resetVoiceEnvelope() {
  state.envelope.selectedIndex = -1;
  state.envelope.target = "voice";
  saveVoiceArrangement({ volume_envelope: [{ time: 0, volume: 1 }] }).catch((err) => setStatus(`Voice automation reset failed: ${err.message}`));
}

async function saveVoiceArrangement(patch = {}) {
  const payload = { ...voiceArrangement(), ...patch };
  state.project = await api(`/api/project/arrangement/voice${activeProjectQuery()}`, { method: "POST", body: JSON.stringify(payload) });
  if (patch.volume_envelope) setStatus("Voice automation saved");
  render();
}

async function saveVideoArrangement(patch = {}) {
  const payload = patch && typeof patch === "object" ? { ...patch } : {};
  state.project = await api(`/api/project/arrangement/video${activeProjectQuery()}`, { method: "POST", body: JSON.stringify(payload) });
  if (patch.speed_envelope) setStatus("Video speed automation saved");
  render();
}

function renderSettings() {
  const p = state.project;
  if (document.activeElement !== $("fullText")) $("fullText").value = p.full_text || "";
  $("referencePath").value = p.settings.reference_path || "";
  $("musicPath").value = p.settings.music_path || "";
  $("voiceVolume").value = p.settings.voice_volume ?? 1;
  $("musicVolume").value = p.settings.music_volume ?? 0.18;
  $("voiceVolumeValue").textContent = Number($("voiceVolume").value).toFixed(2);
  $("musicVolumeValue").textContent = Number($("musicVolume").value).toFixed(2);
  const transportMusic = $("transportMusicVolume");
  if (transportMusic && document.activeElement !== transportMusic) {
    transportMusic.value = p.settings.music_volume ?? 0.18;
    $("transportMusicVolumeValue").textContent = Number(transportMusic.value).toFixed(2);
  }
  const musicMode = $("musicMode");
  if (musicMode) musicMode.value = musicArrangement().mode;
  const imageDefaults = { image_provider: "comfyui", image_model: "realvisxl", image_grok_model: GROK_IMAGE_MODEL, image_quality_preset: "balanced", image_aspect_ratio: "vertical", image_width: 896, image_height: 1152, image_style_preset: "sleep_documentary", image_comfyui_url: "http://127.0.0.1:8188", image_comfyui_path: "ComfyUI_windows_portable", image_comfyui_python: "", image_comfyui_launch_cmd: "", image_comfyui_autostart: false, image_workflow_mode: "generated", image_workflow_path: "", image_model_checkpoint: REALVISXL_CHECKPOINT, image_steps: 22, image_cfg: 6.0, image_sampler: "dpmpp_2m_sde", image_scheduler: "karras", image_negative_preset: "default", image_exclude_people: false, image_seed: 0, video_i2v_enabled: false, video_i2v_quality_preset: "balanced", video_i2v_motion_style: "ambient_nature", video_i2v_workflow_mode: "generated_svd", video_i2v_model_checkpoint: SVD_XT_CHECKPOINT, video_i2v_grok_model: "grok-imagine-video", video_i2v_grok_duration_sec: 5, video_i2v_grok_resolution: "480p", video_i2v_grok_aspect_ratio_mode: "auto", video_i2v_grok_loop_postprocess: "pingpong", video_i2v_grok_crossfade_sec: 0.5, video_i2v_frames: 25, video_i2v_fps: 6, video_i2v_motion_bucket_id: 72, video_i2v_augmentation_level: 0.005, video_i2v_min_cfg: 1.0, video_i2v_cfg: 2.0, video_i2v_steps: 20, video_i2v_sampler: "euler", video_i2v_scheduler: "normal", video_i2v_pingpong: true, video_i2v_target_duration_sec: 20, video_i2v_preview_playback_rate: 1, tts_backend: "xtts", tts_pronunciation_preprocess_enabled: true, tts_pronunciation_dictionary_path: "xtts_api/pronunciation_dictionary.json", tts_stress_mark_style: "acute", silero_api_url: "http://127.0.0.1:7866", silero_speaker: "baya", silero_sample_rate: 48000, silero_realism_enabled: true, silero_realism_preset: "sleep_safe", ai_add_russian_stress_marks: false, ai_stress_model: "" };
  const setIfNotFocused = (id, value) => {
    const el = $(id);
    if (el && document.activeElement !== el) el.value = value;
  };
  setIfNotFocused("imageProvider", p.settings.image_provider ?? imageDefaults.image_provider);
  setIfNotFocused("imageModel", p.settings.image_model ?? imageDefaults.image_model);
  setIfNotFocused("imageGrokModel", p.settings.image_grok_model ?? imageDefaults.image_grok_model);
  setIfNotFocused("imageAspectRatio", p.settings.image_aspect_ratio ?? imageDefaults.image_aspect_ratio);
  setImageQualityPreset(p.settings.image_quality_preset ?? imageDefaults.image_quality_preset, { updateFields: false });
  setIfNotFocused("imageWidth", p.settings.image_width ?? imageDefaults.image_width);
  setIfNotFocused("imageHeight", p.settings.image_height ?? imageDefaults.image_height);
  setIfNotFocused("imageStylePreset", p.settings.image_style_preset ?? imageDefaults.image_style_preset);
  setIfNotFocused("imageComfyuiUrl", p.settings.image_comfyui_url ?? imageDefaults.image_comfyui_url);
  setIfNotFocused("imageComfyuiPath", p.settings.image_comfyui_path ?? imageDefaults.image_comfyui_path);
  setIfNotFocused("imageComfyuiPython", p.settings.image_comfyui_python ?? imageDefaults.image_comfyui_python);
  setIfNotFocused("imageComfyuiLaunchCmd", p.settings.image_comfyui_launch_cmd ?? imageDefaults.image_comfyui_launch_cmd);
  const comfyAutostart = $("imageComfyuiAutostart");
  if (comfyAutostart && document.activeElement !== comfyAutostart) comfyAutostart.checked = Boolean(p.settings.image_comfyui_autostart ?? imageDefaults.image_comfyui_autostart);
  setIfNotFocused("imageWorkflowMode", p.settings.image_workflow_mode ?? imageDefaults.image_workflow_mode);
  setIfNotFocused("imageWorkflowPath", p.settings.image_workflow_path ?? imageDefaults.image_workflow_path);
  setIfNotFocused("imageModelCheckpoint", p.settings.image_model_checkpoint ?? imageDefaults.image_model_checkpoint);
  setIfNotFocused("imageSteps", p.settings.image_steps ?? imageDefaults.image_steps);
  setIfNotFocused("imageCfg", p.settings.image_cfg ?? imageDefaults.image_cfg);
  setIfNotFocused("imageSampler", p.settings.image_sampler ?? imageDefaults.image_sampler);
  setIfNotFocused("imageScheduler", p.settings.image_scheduler ?? imageDefaults.image_scheduler);
  setIfNotFocused("imageNegativePreset", p.settings.image_negative_preset ?? imageDefaults.image_negative_preset);
  const excludePeople = $("imageExcludePeople");
  if (excludePeople && document.activeElement !== excludePeople) excludePeople.checked = Boolean(p.settings.image_exclude_people ?? imageDefaults.image_exclude_people);
  setIfNotFocused("imageSeed", p.settings.image_seed ?? imageDefaults.image_seed);
  const videoEnabled = $("videoI2vEnabled");
  if (videoEnabled && document.activeElement !== videoEnabled) videoEnabled.checked = Boolean(p.settings.video_i2v_enabled ?? imageDefaults.video_i2v_enabled);
  setVideoI2vQualityPreset(p.settings.video_i2v_quality_preset ?? imageDefaults.video_i2v_quality_preset, { updateFields: false });
  setIfNotFocused("videoI2vMotionStyle", p.settings.video_i2v_motion_style ?? imageDefaults.video_i2v_motion_style);
  setIfNotFocused("videoI2vWorkflowMode", p.settings.video_i2v_workflow_mode ?? imageDefaults.video_i2v_workflow_mode);
  setIfNotFocused("videoI2vModelCheckpoint", p.settings.video_i2v_model_checkpoint ?? imageDefaults.video_i2v_model_checkpoint);
  setIfNotFocused("videoI2vGrokModel", p.settings.video_i2v_grok_model ?? imageDefaults.video_i2v_grok_model);
  setIfNotFocused("videoI2vGrokDurationSec", p.settings.video_i2v_grok_duration_sec ?? imageDefaults.video_i2v_grok_duration_sec);
  setIfNotFocused("videoI2vGrokResolution", p.settings.video_i2v_grok_resolution ?? imageDefaults.video_i2v_grok_resolution);
  setIfNotFocused("videoI2vGrokAspectRatioMode", p.settings.video_i2v_grok_aspect_ratio_mode ?? imageDefaults.video_i2v_grok_aspect_ratio_mode);
  setIfNotFocused("videoI2vGrokLoopPostprocess", p.settings.video_i2v_grok_loop_postprocess ?? imageDefaults.video_i2v_grok_loop_postprocess);
  setIfNotFocused("videoI2vGrokCrossfadeSec", p.settings.video_i2v_grok_crossfade_sec ?? imageDefaults.video_i2v_grok_crossfade_sec);
  setIfNotFocused("videoI2vFrames", p.settings.video_i2v_frames ?? imageDefaults.video_i2v_frames);
  setIfNotFocused("videoI2vFps", p.settings.video_i2v_fps ?? imageDefaults.video_i2v_fps);
  setIfNotFocused("videoI2vMotionBucketId", p.settings.video_i2v_motion_bucket_id ?? imageDefaults.video_i2v_motion_bucket_id);
  setIfNotFocused("videoI2vAugmentationLevel", p.settings.video_i2v_augmentation_level ?? imageDefaults.video_i2v_augmentation_level);
  setIfNotFocused("videoI2vMinCfg", p.settings.video_i2v_min_cfg ?? imageDefaults.video_i2v_min_cfg);
  setIfNotFocused("videoI2vCfg", p.settings.video_i2v_cfg ?? imageDefaults.video_i2v_cfg);
  setIfNotFocused("videoI2vSteps", p.settings.video_i2v_steps ?? imageDefaults.video_i2v_steps);
  setIfNotFocused("videoI2vSampler", p.settings.video_i2v_sampler ?? imageDefaults.video_i2v_sampler);
  setIfNotFocused("videoI2vScheduler", p.settings.video_i2v_scheduler ?? imageDefaults.video_i2v_scheduler);
  const videoPingpong = $("videoI2vPingpong");
  if (videoPingpong && document.activeElement !== videoPingpong) videoPingpong.checked = Boolean(p.settings.video_i2v_pingpong ?? imageDefaults.video_i2v_pingpong);
  setIfNotFocused("videoI2vTargetDurationSec", p.settings.video_i2v_target_duration_sec ?? imageDefaults.video_i2v_target_duration_sec);
  setIfNotFocused("videoI2vPreviewPlaybackRate", p.settings.video_i2v_preview_playback_rate ?? imageDefaults.video_i2v_preview_playback_rate);
  setIfNotFocused("ttsBackend", p.settings.tts_backend ?? imageDefaults.tts_backend);
  const ttsPreprocess = $("ttsPronunciationPreprocessEnabled");
  if (ttsPreprocess && document.activeElement !== ttsPreprocess) ttsPreprocess.checked = Boolean(p.settings.tts_pronunciation_preprocess_enabled ?? imageDefaults.tts_pronunciation_preprocess_enabled);
  setIfNotFocused("ttsPronunciationDictionaryPath", p.settings.tts_pronunciation_dictionary_path ?? imageDefaults.tts_pronunciation_dictionary_path);
  setIfNotFocused("ttsStressMarkStyle", p.settings.tts_stress_mark_style ?? imageDefaults.tts_stress_mark_style);
  setIfNotFocused("sileroApiUrl", p.settings.silero_api_url ?? imageDefaults.silero_api_url);
  setIfNotFocused("sileroSpeaker", p.settings.silero_speaker ?? imageDefaults.silero_speaker);
  setIfNotFocused("sileroSampleRate", p.settings.silero_sample_rate ?? imageDefaults.silero_sample_rate);
  const sileroRealism = $("sileroRealismEnabled");
  if (sileroRealism && document.activeElement !== sileroRealism) sileroRealism.checked = Boolean(p.settings.silero_realism_enabled ?? imageDefaults.silero_realism_enabled);
  setIfNotFocused("sileroRealismPreset", p.settings.silero_realism_preset ?? imageDefaults.silero_realism_preset);
  const aiStress = $("aiAddRussianStressMarks");
  if (aiStress && document.activeElement !== aiStress) aiStress.checked = Boolean(p.settings.ai_add_russian_stress_marks ?? imageDefaults.ai_add_russian_stress_marks);
  setIfNotFocused("aiStressModel", p.settings.ai_stress_model ?? imageDefaults.ai_stress_model);
  const aiSplitGroups = $("aiGenerateGroupPromptsOnSplit");
  if (aiSplitGroups && document.activeElement !== aiSplitGroups) aiSplitGroups.checked = Boolean(p.settings.ai_generate_group_prompts_on_split ?? true);
  updateResolvedImageSettingsHint();
  syncGrokImageSettingsUi();
  updateResolvedVideoI2vSettingsHint();
  renderFluxWorkflowNote();
  renderComfyuiStatus();
  const xaiInput = $("xaiApiKey");
  if (xaiInput && document.activeElement !== xaiInput) xaiInput.value = "";
  const clearXai = $("clearXaiApiKey");
  if (clearXai && document.activeElement !== clearXai) clearXai.checked = false;
  const xaiHint = $("xaiApiKeyHint");
  if (xaiHint) {
    const keyHint = String(p.settings.xai_api_key_hint || "").trim();
    const configured = Boolean(p.settings.xai_api_key_configured) || (/configured|using xai_api_key/i.test(keyHint) && !/^not configured$/i.test(keyHint));
    xaiHint.textContent = configured
      ? `Grok key configured · ${keyHint || "project/env key available"}`
      : "Grok key not configured · set it here or via XAI_API_KEY.";
    xaiHint.className = `xaiApiKeyHint ${configured ? "configured" : "missing"}`;
  }
}

function renderFluxWorkflowNote() {
  const note = $("imageFluxWorkflowNote");
  if (!note) return;
  const model = $("imageModel")?.value || state.project?.settings?.image_model || "sdxl";
  const workflowMode = $("imageWorkflowMode")?.value || state.project?.settings?.image_workflow_mode || "generated";
  note.hidden = !(model === "flux" && workflowMode === "generated");
}

function syncGrokImageSettingsUi() {
  const provider = $("imageProvider");
  const model = $("imageModel");
  const normalized = window.XTTSStudio?.SettingsHelpers?.normalizeImageProviderModel?.(provider?.value, model?.value, { preferProvider: document.activeElement === provider }) || { provider: provider?.value, model: model?.value };
  const selected = normalized.provider === "grok" || normalized.model === "grok";
  if (provider && document.activeElement !== provider) provider.value = normalized.provider;
  if (model && document.activeElement !== model) model.value = normalized.model;
  const panel = $("grokImageSettingsPanel");
  if (panel) panel.classList.toggle("active", selected);
  const grokModel = $("imageGrokModel");
  if (grokModel) grokModel.disabled = !selected;
  updateResolvedImageSettingsHint();
}

function renderComfyuiStatus() {
  const badge = $("comfyuiStatusBadge");
  const line = $("comfyuiStatusLine");
  if (!badge || !line) return;
  const info = state.comfyuiStatus;
  if (!info) {
    badge.textContent = "ComfyUI: not checked";
    badge.className = "comfyuiStatusBadge unknown";
    line.textContent = "Use Check ComfyUI to query /api/comfyui/status.";
    return;
  }
  const running = Boolean(info.running);
  badge.textContent = running ? "ComfyUI: running" : "ComfyUI: not running";
  badge.className = `comfyuiStatusBadge ${running ? "running" : "stopped"}`;
  const parts = [
    running ? "running" : "not running",
    `url: ${info.url || "—"}`,
    `autostart: ${info.autostart_enabled ? "on" : "off"}`,
    `workflow: ${info.workflow_mode || "—"}`,
    `checkpoint: ${info.model_checkpoint || "not configured"} (${info.model_check || "unknown"})`,
  ];
  if (info.note) parts.push(`note: ${info.note}`);
  line.textContent = parts.join(" · ");
}

async function checkComfyuiStatus() {
  try {
    setStatus("Checking ComfyUI status…", true);
    state.comfyuiStatus = await api(`/api/comfyui/status${activeProjectQuery()}`);
    renderComfyuiStatus();
    setStatus(state.comfyuiStatus.running ? "ComfyUI is running" : "ComfyUI is not running");
  } catch (err) {
    state.comfyuiStatus = { running: false, url: $("imageComfyuiUrl")?.value || "", autostart_enabled: $("imageComfyuiAutostart")?.checked || false, workflow_mode: $("imageWorkflowMode")?.value || "generated", model_checkpoint: $("imageModelCheckpoint")?.value || "", model_check: "error", note: err.message };
    renderComfyuiStatus();
    setStatus(`ComfyUI status failed: ${err.message}`);
  }
}

function applyImageSizePreset(button) {
  const aspect = button?.dataset?.aspect || "vertical";
  const width = Number(button?.dataset?.width || 1024);
  const height = Number(button?.dataset?.height || 1792);
  if ($("imageAspectRatio")) $("imageAspectRatio").value = aspect;
  if ($("imageWidth")) $("imageWidth").value = String(width);
  if ($("imageHeight")) $("imageHeight").value = String(height);
  document.querySelectorAll(".imageSizePreset").forEach((item) => item.classList.toggle("active", item === button));
  setStatus(`Image size preset: ${width}×${height}`);
}

function formatTime(seconds) {
  const safe = Math.max(0, Number(seconds) || 0);
  const minutes = Math.floor(safe / 60);
  const secs = Math.floor(safe % 60);
  const ms = Math.floor((safe - Math.floor(safe)) * 1000);
  return `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}.${String(ms).padStart(3, "0")}`;
}

function chunkSummaryText(text, maxWords = 12) {
  const words = String(text || "").replace(/\s+/g, " ").trim().split(" ").filter(Boolean);
  return words.slice(0, maxWords).join(" ") + (words.length > maxWords ? "…" : "");
}

function computeChunkGroups(chunks = getChunks(), size = 4) {
  const sorted = [...chunks].sort((a, b) => a.order - b.order);
  const groups = [];
  for (let index = 0; index < sorted.length; index += size) {
    const groupChunks = sorted.slice(index, index + size);
    if (!groupChunks.length) continue;
    const groupNumber = groups.length + 1;
    const firstOrder = groupChunks[0].order + 1;
    const lastOrder = groupChunks[groupChunks.length - 1].order + 1;
    groups.push({
      id: `group_${groupNumber}`,
      order: groupNumber - 1,
      title: `Группа ${groupNumber} · чанки ${firstOrder}–${lastOrder}`,
      summary: chunkSummaryText(groupChunks[0].text) || "Без текста",
      chunk_ids: groupChunks.map((chunk) => chunk.id),
    });
  }
  return groups;
}

function videoGroups() {
  const saved = state.project?.arrangement?.video?.groups;
  if (Array.isArray(saved) && saved.length) return saved;
  return computeChunkGroups();
}

function activeImageGroupTask(groupId = "") {
  const projectId = state.project?.id || state.activeProjectId || "";
  const queues = [state.queue || [], state.project?.queue || []];
  for (const tasks of queues) {
    const task = (tasks || []).find((item) => item?.kind === "image_group"
      && (!projectId || item.project_id === projectId)
      && (!groupId || item.group_id === groupId || item.result_group_id === groupId || item.payload?.group_id === groupId || item.params?.group_id === groupId)
      && ["queued", "running"].includes(item.status));
    if (task) return task;
  }
  return null;
}


function activeVideoGroupTask(groupId = "") {
  const projectId = state.project?.id || state.activeProjectId || "";
  const queues = [state.queue || [], state.project?.queue || []];
  for (const tasks of queues) {
    const task = (tasks || []).find((item) => item?.kind === "video_group"
      && (!projectId || item.project_id === projectId)
      && (!groupId || item.payload?.group_id === groupId || item.params?.group_id === groupId)
      && ["queued", "running"].includes(item.status));
    if (task) return task;
  }
  return null;
}

function groupImageStatus(group) {
  const activeTask = activeImageGroupTask(group?.id || "");
  if (activeTask) return activeTask.status === "running" ? "running" : "queued";
  const image = group?.image || {};
  if (!image || !Object.keys(image).length) return "missing";
  const status = String(image.status || "").toLowerCase();
  if (["done", "fallback", "failed", "running", "queued"].includes(status)) return status;
  if (image.url || image.path) return "done";
  return "missing";
}

function groupVideoStatus(group) {
  const activeTask = activeVideoGroupTask(group?.id || "");
  if (activeTask) return activeTask.status === "running" ? "running" : "queued";
  const video = group?.video || {};
  if (!video || !Object.keys(video).length) return "missing";
  const status = String(video.status || "").toLowerCase();
  if (["ready", "done", "failed", "running", "queued"].includes(status)) return status === "ready" ? "done" : status;
  if (video.url || video.path) return "done";
  return "missing";
}

function groupVideoMetaText(group) {
  const video = group?.video || {};
  const status = groupVideoStatus(group);
  if (status === "missing") return "no SVD video";
  const parts = [status];
  if (video.loop) parts.push("loop video");
  if (video.pingpong) parts.push("ping-pong");
  if (video.duration_sec) parts.push(formatTime(video.duration_sec));
  if (video.frames) parts.push(`${video.frames} frames`);
  if (video.fps) parts.push(`${video.fps} fps`);
  if (video.model_checkpoint) parts.push(shortPath(video.model_checkpoint));
  return parts.join(" · ");
}

function groupImageStatusLabel(status) {
  return ({ missing: "missing", queued: "queued", running: "running", done: "done", fallback: "fallback", failed: "failed" })[status] || status || "missing";
}

function groupImageMetaText(group) {
  const image = group?.image || {};
  const status = groupImageStatus(group);
  const parts = [groupImageStatusLabel(status)];
  if (image.provider) parts.push(image.provider);
  if (image.model) parts.push(image.model);
  if (image.aspect_ratio) parts.push(image.aspect_ratio);
  if (image.seed !== undefined && image.seed !== null && image.seed !== "") parts.push(`seed ${image.seed}`);
  return parts.join(" · ");
}

function selectedPreviewGroup() {
  const groups = groupTimelineSpans();
  const previewGroupId = state.preview.followPlayhead ? state.preview.groupId : "";
  return groups.find((group) => group.id === previewGroupId)
    || groups.find((group) => group.id === state.selectedGroupId)
    || groups.find((group) => group.video?.url)
    || groups.find((group) => group.image?.url)
    || groups[0]
    || null;
}

function groupTimelineSpans(groups = videoGroups()) {
  const byChunkId = new Map((state.timeline.arrangement || []).map((part) => [part.chunk.id, part]));
  return groups.map((group) => {
    const chunkIds = Array.isArray(group.chunk_ids) ? group.chunk_ids : [];
    const parts = chunkIds.map((id) => byChunkId.get(id)).filter(Boolean);
    const start = parts.length ? Math.min(...parts.map((part) => part.start)) : 0;
    const end = parts.length ? Math.max(...parts.map((part) => part.end)) : start;
    return { ...group, chunk_ids: chunkIds, start, end, duration: Math.max(0, end - start), parts };
  });
}

function videoGroupAtTime(seconds) {
  const time = Math.max(0, Number(seconds) || 0);
  const groups = groupTimelineSpans();
  return groups.find((group) => time >= group.start && time < group.end)
    || groups.find((group) => group.duration === 0 && Math.abs(time - group.start) < 0.001)
    || (time >= state.timeline.durationSec ? groups.find((group) => group.end === state.timeline.durationSec) : null)
    || null;
}

function syncPreviewGroupToPlayhead({ forceRender = false } = {}) {
  if (!state.preview.followPlayhead) return;
  const group = videoGroupAtTime(state.timeline.cursorSec);
  const nextGroupId = group?.id || "";
  if (state.preview.groupId === nextGroupId && !forceRender) return;
  state.preview.groupId = nextGroupId;
  if (nextGroupId) {
    state.selectedGroupId = nextGroupId;
    setActiveGroupNav(nextGroupId);
    renderVideoGroupLanesHost();
  }
  if (state.screenMode === "preview") renderPreviewScreen();
}

function selectedGroup() {
  return groupTimelineSpans().find((group) => group.id === state.selectedGroupId) || null;
}

function buildTimelineArrangement() {
  let cursor = 0;
  const arrangement = [];
  for (const chunk of getChunks()) {
    const selected = selectedVersionForChunk(chunk);
    const duration = Math.max(0, Number(selected?.duration_sec ?? chunk.duration_sec ?? 0));
    const start = cursor;
    const end = start + duration;
    const pauseAfter = clampPauseAfter(chunk.pause_after);
    arrangement.push({ chunk, selected, audioUrl: selectedAudioUrlForChunk(chunk), start, end, duration, pauseAfter, nextStart: end + pauseAfter });
    cursor = end + pauseAfter;
  }
  state.timeline.arrangement = arrangement;
  state.timeline.durationSec = Math.max(0, cursor, Number(state.project?.timeline_duration_sec || 0));
  state.timeline.cursorSec = Math.min(state.timeline.cursorSec, state.timeline.durationSec);
  return arrangement;
}

function updateTransportReadout() {
  const time = $("transportTime");
  if (time) time.textContent = `${formatTime(state.timeline.cursorSec)} / ${formatTime(state.timeline.durationSec)}`;
  const scrubber = $("timelineScrubber");
  if (scrubber && !state.timeline.userScrubbing) scrubber.value = String(state.timeline.cursorSec);
  applyPreviewVideoPlaybackRate();
  updatePlayheadPosition();
  updateAutomationCursorReadout();
}

function setTimelineCursor(seconds, { fromPlayback = false } = {}) {
  state.timeline.cursorSec = Math.max(0, Math.min(Number(seconds) || 0, state.timeline.durationSec || 0));
  updateTransportReadout();
  syncPreviewGroupToPlayhead();
  if (!fromPlayback) setSequenceStatus(`Cursor ${formatTime(state.timeline.cursorSec)}`);
}

function renderTimeline() {
  const timeline = $("timeline");
  timeline.innerHTML = "";
  const arrangement = buildTimelineArrangement();
  for (const part of arrangement) {
    const chunk = part.chunk;
    const item = document.createElement("div");
    item.className = "timelineItem";
    item.style.left = `${timelinePx(part.start)}px`;
    item.style.width = `${timelinePx(part.duration)}px`;
    item.innerHTML = `<span>${chunk.order + 1}</span>`;
    item.title = `Start ${part.start.toFixed(3)}s, duration ${part.duration.toFixed(3)}s, selected ${part.selected?.label || "none"}, pause after ${part.pauseAfter}s.`;
    timeline.appendChild(item);
  }
  renderTransportLanes();
}

function renderTransportLanes() {
  const music = musicArrangement();
  const scrubber = $("timelineScrubber");
  if (scrubber) {
    scrubber.max = String(state.timeline.durationSec || 0);
    scrubber.disabled = state.timeline.durationSec <= 0;
  }
  updateTimelineWorkspaceWidth();
  updateTransportReadout();
  const voiceLane = $("voiceTimelineLane");
  if (voiceLane) {
    voiceLane.innerHTML = "";
    state.timeline.arrangement.forEach((part, index) => {
      const block = document.createElement("div");
      block.className = `laneBlock ${part.audioUrl ? "ready" : "missing"}`;
      block.style.left = `${timelinePx(part.start)}px`;
      block.style.width = `${timelinePx(part.duration)}px`;
      block.innerHTML = `<span>${part.chunk.order + 1}</span>`;
      block.title = `Chunk ${part.chunk.order + 1}: ${formatTime(part.start)} - ${formatTime(part.end)}${part.audioUrl ? "" : " · missing selected audio"}`;
      voiceLane.appendChild(block);
      if (index < state.timeline.arrangement.length - 1 || part.pauseAfter > 0) {
        voiceLane.appendChild(renderPauseRegion(part, index));
      }
    });
  }
  const voiceAutomationLane = $("voiceAutomationLane");
  if (voiceAutomationLane) {
    voiceAutomationLane.innerHTML = "";
    renderEnvelope(voiceAutomationLane, "voice");
  }
  const musicLane = $("musicTimelineLane");
  if (musicLane) {
    musicLane.innerHTML = "";
    renderEnvelope(musicLane, "music");
  }
  renderMusicLanesHost(music);
  renderVideoGroupLanesHost();
  const videoSpeedLane = $("videoSpeedAutomationLane");
  if (videoSpeedLane) {
    videoSpeedLane.innerHTML = "";
    videoSpeedLane.style.width = `${Math.max(1, timelinePx(state.timeline.durationSec || 1))}px`;
    renderVideoSpeedEnvelope(videoSpeedLane);
  }
  const label = $("musicLaneLabel");
  if (label) label.textContent = music.sources.length ? `Music: ${music.sources.length} source(s) · ${music.lanes.length} lane(s) · ${music.tracks.length} clip(s)` : "Music: none loaded";
  renderMusicClipEditor();
}

function renderVideoGroupLanesHost() {
  const host = $("videoGroupLanesHost");
  if (!host) return;
  host.innerHTML = "";
  host.style.setProperty("--video-group-timeline-width", `${Math.max(1, timelinePx(state.timeline.durationSec || 1))}px`);
  const groups = groupTimelineSpans();
  const timelineWidth = Math.max(1, timelinePx(state.timeline.durationSec || 1));
  const row = document.createElement("div");
  row.className = "videoGroupLaneRow videoGroupSingleLaneRow";
  const head = document.createElement("div");
  head.className = "videoGroupLaneControls";
  head.innerHTML = `<strong>All video groups</strong><small>${groups.length ? `${groups.length} group(s) · one shared lane` : "No chunk groups yet"}</small>`;
  const lane = document.createElement("div");
  lane.className = "timelineLane videoGroupLane videoGroupSingleLane";
  lane.style.width = `${timelineWidth}px`;
  if (!groups.length) {
    lane.innerHTML = `<div class="videoGroupBlock missing" style="left:0;width:${Math.max(180, timelineWidth)}px">No chunk groups yet</div>`;
    row.appendChild(head);
    row.appendChild(lane);
    host.appendChild(row);
    return;
  }
  for (const group of groups) {
    const imageStatus = groupImageStatus(group);
    const block = document.createElement("button");
    block.type = "button";
    block.className = `videoGroupBlock image-${imageStatus} ${group.id === state.selectedGroupId ? "active selected" : ""}`;
    block.dataset.groupId = group.id;
    block.style.left = `${timelinePx(group.start)}px`;
    block.style.width = `${Math.max(44, timelinePx(group.duration || 0.05))}px`;
    block.title = `${group.title}: ${formatTime(group.start)} - ${formatTime(group.end)} · image ${imageStatus} · ${group.summary}`;
    block.innerHTML = `<span>${escapeHtml(group.title)}</span><small>${escapeHtml(groupImageMetaText(group))}</small>`;
    block.onclick = () => selectGroup(group.id);
    lane.appendChild(block);
  }
  row.appendChild(head);
  row.appendChild(lane);
  host.appendChild(row);
}

function renderMusicLanesHost(music = musicArrangement()) {
  const host = $("musicLanesHost");
  if (!host) return;
  host.innerHTML = "";
  host.style.removeProperty("width");
  if (!music.lanes.length) {
    const empty = document.createElement("div");
    empty.className = "timelineLane musicLane musicLaneRow empty";
    empty.innerHTML = `<div class="musicBlock missing" style="left:0;width:${Math.max(180, timelinePx(state.timeline.durationSec || 1))}px">No music lanes — drag a source here</div>`;
    attachMusicLaneDrop(empty, "");
    host.appendChild(empty);
    return;
  }
  for (const lane of music.lanes) {
    const row = document.createElement("div");
    row.className = `musicLaneGrid ${lane.id === state.musicClip.selectedLaneId ? "selected" : ""} ${lane.enabled ? "" : "disabled"}`;
    row.dataset.laneId = lane.id;
    const head = document.createElement("div");
    head.className = "musicLaneControls";
    head.innerHTML = `
      <strong title="${escapeHtml(lane.path || lane.label || "")}">${escapeHtml(lane.label || shortPath(lane.path))}</strong>
      <div class="musicLaneControlLine">
        <label class="musicLaneVolumeLabel">Vol <input class="musicLaneVolume" type="number" min="0" max="2" step="0.01" value="${Number(lane.volume ?? 1).toFixed(2)}" /></label>
        <span class="musicLaneCurveValue">Curve ${Number(laneEnvelopeValueAt(lane, 0)).toFixed(2)}</span>
        <label><input class="musicLaneLoop" type="checkbox" ${lane.loop ? "checked" : ""} /> Loop</label>
        <label><input class="musicLaneEnabled" type="checkbox" ${lane.enabled ? "checked" : ""} /> On</label>
      </div>
      <button type="button" class="secondary resetLaneCurveBtn">Reset lane curve</button>
      <button type="button" class="secondary deleteMusicLaneBtn">Delete lane</button>
    `;
    head.onclick = (event) => { if (!event.target.closest?.("input,button,label")) selectMusicLane(lane.id); };
    head.querySelector(".musicLaneVolume").onchange = (event) => updateMusicLane(lane.id, { volume: Number(event.target.value) });
    head.querySelector(".musicLaneLoop").onchange = (event) => updateMusicLane(lane.id, { loop: event.target.checked });
    head.querySelector(".musicLaneEnabled").onchange = (event) => updateMusicLane(lane.id, { enabled: event.target.checked });
    head.querySelector(".resetLaneCurveBtn").onclick = () => resetMusicLaneCurve(lane.id);
    head.querySelector(".deleteMusicLaneBtn").onclick = () => { selectMusicLane(lane.id); deleteSelectedMusicLane(); };
    const body = document.createElement("div");
    body.className = "timelineLane musicLane musicLaneRow";
    body.style.width = `${Math.max(1, timelinePx(state.timeline.durationSec || 1))}px`;
    body.onclick = (event) => { if (!event.target.closest?.(".musicClip")) selectMusicLane(lane.id); };
    attachMusicLaneDrop(body, lane.id);
    renderLaneClipInstances(lane).forEach((item, index) => body.appendChild(renderMusicClipBlock(item.clip, timelinePx(item.start_time), Math.max(36, timelinePx(item.duration || state.preview.musicBufferDuration || 8)), lane.loop && item.repeated, index, item.repeated, lane)));
    const automation = document.createElement("div");
    automation.className = "timelineLane musicLaneAutomationLane";
    automation.dataset.laneId = lane.id;
    automation.dataset.target = laneTarget(lane.id);
    automation.style.width = `${Math.max(1, timelinePx(state.timeline.durationSec || 1))}px`;
    automation.title = `Lane volume automation: ${lane.label || shortPath(lane.path)}. Click to add a point, drag points, Alt/right-click to delete.`;
    automation.addEventListener("click", (event) => {
      if (event.target.closest?.(".envelopePoint")) return;
      event.preventDefault();
      event.stopPropagation();
      selectMusicLane(lane.id);
      addEnvelopePoint(event, laneTarget(lane.id));
    });
    automation.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      event.stopPropagation();
      if (state.envelope.target === laneTarget(lane.id) && state.envelope.selectedIndex >= 0) deleteEnvelopePoint(laneTarget(lane.id));
    });
    renderEnvelope(automation, laneTarget(lane.id));
    row.appendChild(head);
    row.appendChild(body);
    row.appendChild(automation);
    host.appendChild(row);
  }
}

function renderLaneClipInstances(lane) {
  const base = lane.clips.map((clip) => ({ clip, start_time: Number(clip.start_time || 0), duration: clipDurationForClip(lane, clip), repeated: false }));
  if (!lane.loop || !base.length) return base;
  const patternStart = Math.min(...base.map((item) => item.start_time));
  const patternEnd = Math.max(...base.map((item) => item.start_time + Math.max(0.001, item.duration || 8)));
  const patternLen = Math.max(0.001, patternEnd - patternStart);
  const out = [];
  for (let repeatStart = patternStart, repeatIndex = 0; repeatStart < (state.timeline.durationSec || patternEnd); repeatStart += patternLen, repeatIndex += 1) {
    base.forEach((item) => out.push({ ...item, start_time: repeatStart + (item.start_time - patternStart), repeated: repeatIndex > 0 }));
  }
  return out;
}

function safeRenderStep(label, fn) {
  try {
    fn();
  } catch (err) {
    console.error(`XTTS Studio render step failed: ${label}`, err);
    setStatus(`Render warning (${label}): ${err.message}`);
  }
}

function clipDurationForTrack(track) {
  const source = musicArrangement().sources.find((item) => item.id === track.source_id || item.path === track.path);
  const explicitDuration = Number(track.duration_sec || track.duration || 0);
  if (explicitDuration > 0) return Math.max(0, explicitDuration);
  return Math.max(0, Number(source?.duration || 0) - Number(track.offset_sec || 0));
}

function sourceDurationForTrack(track) {
  const source = musicArrangement().sources.find((item) => item.id === track.source_id || item.path === track.path);
  return Math.max(0, Number(source?.duration || 0));
}

function visualClipDuration(track) {
  return Math.max(0.05, clipDurationForTrack(track) || state.preview.musicBufferDuration || 8);
}

function expandedChainClips(tracks) {
  const sorted = [...tracks].sort((a, b) => Number(a.start_time || 0) - Number(b.start_time || 0));
  if (!sorted.length) return [];
  const spans = sorted.map((track) => ({ track, start: Number(track.start_time || 0), end: Number(track.start_time || 0) + Math.max(0.001, clipDurationForTrack(track) || state.preview.musicBufferDuration || 8) }));
  const chainStart = Math.min(...spans.map((item) => item.start));
  const chainEnd = Math.max(...spans.map((item) => item.end));
  const chainLen = Math.max(0.001, chainEnd - chainStart);
  const out = [];
  for (let repeatStart = chainStart, repeatIndex = 0; repeatStart < (state.timeline.durationSec || chainEnd); repeatStart += chainLen, repeatIndex += 1) {
    spans.forEach((item) => out.push({ track: item.track, start_time: repeatStart + (item.start - chainStart), duration: item.end - item.start, repeatIndex }));
  }
  return out;
}

function updateTimelineWorkspaceWidth() {
  const workspace = $("timelineWorkspace");
  if (!workspace) return;
  const duration = Math.max(1, state.timeline.durationSec || 1);
  const width = Math.max(state.timeline.minWorkspaceWidth || 1600, Math.ceil(duration * (state.timeline.pixelsPerSecond || 96) + 195));
  workspace.style.width = `${width}px`;
  const timelineColumnWidth = `${width - 195}px`;
  for (const lane of [$("voiceTimelineLane"), $("voiceAutomationLane"), $("musicTimelineLane")]) if (lane) lane.style.width = timelineColumnWidth;
  const musicLanesHost = $("musicLanesHost");
  if (musicLanesHost) {
    musicLanesHost.style.removeProperty("width");
    musicLanesHost.style.setProperty("--music-lane-timeline-width", timelineColumnWidth);
  }
  const videoGroupLanesHost = $("videoGroupLanesHost");
  if (videoGroupLanesHost) videoGroupLanesHost.style.setProperty("--video-group-timeline-width", timelineColumnWidth);
  const videoSpeedLane = $("videoSpeedAutomationLane");
  if (videoSpeedLane) videoSpeedLane.style.width = timelineColumnWidth;
  const zoomLabel = $("zoomValue");
  if (zoomLabel) zoomLabel.textContent = `${Number(state.timeline.pixelsPerSecond).toFixed(state.timeline.pixelsPerSecond < 10 ? 2 : 0)} px/s`;
}

function renderPauseRegion(part, index) {
  const region = document.createElement("div");
  const pause = clampPauseAfter(part.pauseAfter);
  const left = timelinePx(part.end);
  const width = timelinePx(pause);
  region.className = `pauseRegion ${state.pauseDrag.active && state.pauseDrag.chunkId === part.chunk.id ? "editing" : ""}`;
  region.style.left = `${left}px`;
  region.style.width = `${width}px`;
  region.dataset.chunkId = part.chunk.id;
  region.dataset.index = String(index);
  region.dataset.pauseSeconds = String(pause);
  region.innerHTML = `<span>${pause.toFixed(2)}s</span><b aria-hidden="true"></b>`;
  region.title = `Pause after chunk ${part.chunk.order + 1}: ${pause.toFixed(2)}s. Drag the divider horizontally to edit (0–10s).`;
  region.addEventListener("pointerdown", beginPauseDrag);
  return region;
}

function clampPauseAfter(value) {
  return roundTime(clamp(value, TIMELINE_PAUSE_MIN_SEC, TIMELINE_PAUSE_MAX_SEC));
}

function updatePauseAfterLocal(chunkId, pauseAfter) {
  const chunk = getChunks().find((item) => item.id === chunkId);
  if (!chunk) return null;
  chunk.pause_after = clampPauseAfter(pauseAfter);
  buildTimelineArrangement();
  return chunk;
}

function pauseSecondsFromDelta(deltaPx, event) {
  const precisionMultiplier = event?.shiftKey ? 0.2 : event?.altKey ? 0.05 : 1;
  return (deltaPx / Math.max(TIMELINE_ZOOM_MIN, state.timeline.pixelsPerSecond || 96)) * precisionMultiplier;
}

function syncChunkPauseInput(chunkId, pauseAfter) {
  const card = document.querySelector(`[data-chunk-id="${CSS.escape(chunkId)}"]`);
  const input = card?.querySelector?.(".pauseAfter");
  if (input && document.activeElement !== input) input.value = String(Number(pauseAfter).toFixed(2));
  const meta = card?.querySelector?.(".chunkHead span");
  const chunk = getChunks().find((item) => item.id === chunkId);
  if (meta && chunk) {
    const selectedVersion = selectedVersionForChunk(chunk);
    const selectedLabel = selectedVersion ? (selectedVersion.label || selectedVersion.id) : "none";
    meta.textContent = `start ${chunk.start_time || 0}s · selected ${selectedLabel} · duration ${chunk.duration_sec || 0}s · pause after ${Number(pauseAfter).toFixed(2)}s`;
  }
}

function beginPauseDrag(event) {
  if (event.button !== 0) return;
  event.preventDefault();
  event.stopPropagation();
  const region = event.currentTarget;
  const chunkId = region.dataset.chunkId;
  const part = state.timeline.arrangement.find((item) => item.chunk.id === chunkId);
  if (!part) return;
  const lane = $("voiceTimelineLane");
  const laneWidth = lane?.getBoundingClientRect?.().width || 1;
  const startX = event.clientX;
  const startPause = clampPauseAfter(part.pauseAfter);
  state.pauseDrag = { active: true, chunkId, pauseAfter: startPause };
  region.setPointerCapture?.(event.pointerId);
  setStatus(`Editing pause after chunk ${part.chunk.order + 1}: ${startPause.toFixed(2)}s`, true);
  setSequenceStatus("Drag pause divider horizontally · release to save");

  const onMove = (moveEvent) => {
    const nextPause = clampPauseAfter(startPause + pauseSecondsFromDelta(moveEvent.clientX - startX, moveEvent));
    state.pauseDrag.pauseAfter = nextPause;
    updatePauseAfterLocal(chunkId, nextPause);
    syncChunkPauseInput(chunkId, nextPause);
    renderTransportLanes();
    setStatus(`Pause after chunk ${part.chunk.order + 1}: ${nextPause.toFixed(2)}s`, true);
  };
  const onUp = () => {
    document.removeEventListener("pointermove", onMove);
    document.removeEventListener("pointerup", onUp);
    const finalPause = clampPauseAfter(state.pauseDrag.pauseAfter);
    state.pauseDrag = { active: false, chunkId: null, pauseAfter: 0 };
    updatePauseAfterLocal(chunkId, finalPause);
    renderTransportLanes();
    api(`/api/chunks/${chunkId}${activeProjectQuery()}`, { method: "PATCH", body: JSON.stringify({ pause_after: finalPause }) })
      .then((project) => {
        state.project = project;
        renderTimeline();
        setStatus(`Saved pause after chunk ${part.chunk.order + 1}: ${finalPause.toFixed(2)}s`);
      })
      .catch((err) => setStatus(`Pause save failed: ${err.message}`));
  };
  document.addEventListener("pointermove", onMove);
  document.addEventListener("pointerup", onUp, { once: true });
}

function timelinePercent(seconds) {
  return state.timeline.durationSec > 0 ? clamp(seconds / state.timeline.durationSec, 0, 1) * 100 : 0;
}

function timelinePx(seconds) { return Math.max(0, Number(seconds) || 0) * Math.max(TIMELINE_ZOOM_MIN, state.timeline.pixelsPerSecond || 96); }

function timeFromLaneClientX(clientX, lane) {
  const rect = lane.getBoundingClientRect();
  return clamp((clientX - rect.left) / Math.max(TIMELINE_ZOOM_MIN, state.timeline.pixelsPerSecond || 96), 0, state.timeline.durationSec || 0);
}

function renderEnvelope(lane, target = "music") {
  const points = persistedEnvelope(target);
  const width = Math.max(1, lane.clientWidth || timelinePx(state.timeline.durationSec || 10));
  const height = Math.max(1, lane.clientHeight || 36);
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", `musicEnvelope ${target === "voice" ? "voiceEnvelope" : isLaneEnvelopeTarget(target) ? "laneEnvelope" : "musicEnvelopeMaster"}`);
  svg.dataset.target = target;
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("preserveAspectRatio", "none");
  const coords = points.map((point) => ({ x: timelinePx(point.time), y: height - (clamp(point.volume, 0, 2) / 2) * height }));
  const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
  line.setAttribute("class", "envelopeLine");
  line.setAttribute("points", coords.map((p) => `${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(" "));
  svg.appendChild(line);
  points.forEach((point, index) => {
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("class", `envelopePoint ${target === "voice" ? "voicePoint" : ""} ${isLaneEnvelopeTarget(target) ? "lanePoint" : ""} ${target === state.envelope.target && index === state.envelope.selectedIndex ? "selected" : ""}`);
    circle.setAttribute("cx", String(coords[index].x));
    circle.setAttribute("cy", String(coords[index].y));
    circle.setAttribute("r", "9");
    circle.dataset.index = String(index);
    circle.dataset.target = target;
    circle.addEventListener("pointerdown", beginEnvelopeDrag);
    circle.addEventListener("contextmenu", (event) => { event.preventDefault(); event.stopPropagation(); deleteEnvelopePoint(target, index); });
    svg.appendChild(circle);
  });
  lane.appendChild(svg);
}

function renderVideoSpeedEnvelope(lane) {
  const points = persistedVideoSpeedEnvelope();
  const width = Math.max(1, lane.clientWidth || timelinePx(state.timeline.durationSec || 10));
  const height = Math.max(1, lane.clientHeight || 36);
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", "musicEnvelope videoSpeedEnvelope");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("preserveAspectRatio", "none");
  const coords = points.map((point) => ({ x: timelinePx(point.time), y: height - ((clamp(point.speed, VIDEO_SPEED_MIN, VIDEO_SPEED_MAX) - VIDEO_SPEED_MIN) / (VIDEO_SPEED_MAX - VIDEO_SPEED_MIN)) * height }));
  const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
  line.setAttribute("class", "envelopeLine");
  line.setAttribute("points", coords.map((p) => `${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(" "));
  svg.appendChild(line);
  points.forEach((point, index) => {
    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("class", `envelopePoint videoSpeedPoint ${index === state.videoSpeed.selectedIndex ? "selected" : ""}`);
    circle.setAttribute("cx", String(coords[index].x));
    circle.setAttribute("cy", String(coords[index].y));
    circle.setAttribute("r", "8");
    circle.dataset.index = String(index);
    circle.addEventListener("pointerdown", beginVideoSpeedDrag);
    circle.addEventListener("contextmenu", (event) => { event.preventDefault(); event.stopPropagation(); deleteVideoSpeedPoint(index); });
    svg.appendChild(circle);
  });
  lane.appendChild(svg);
}

function videoSpeedPointFromEvent(event) {
  const lane = $("videoSpeedAutomationLane");
  const rect = lane.getBoundingClientRect();
  return {
    time: clamp((event.clientX - rect.left) / Math.max(1, state.timeline.pixelsPerSecond || 96), 0, state.timeline.durationSec || 0),
    speed: clamp(VIDEO_SPEED_MAX - ((event.clientY - rect.top) / Math.max(1, rect.height)) * (VIDEO_SPEED_MAX - VIDEO_SPEED_MIN), VIDEO_SPEED_MIN, VIDEO_SPEED_MAX),
  };
}

function envelopePointFromEvent(event, target = "music") {
  const lane = isLaneEnvelopeTarget(target)
    ? document.querySelector(`[data-target="${CSS.escape(target)}"]`)
    : (target === "voice" ? $("voiceAutomationLane") : $("musicTimelineLane"));
  const rect = lane.getBoundingClientRect();
  return {
    time: clamp((event.clientX - rect.left) / Math.max(1, state.timeline.pixelsPerSecond || 96), 0, state.timeline.durationSec || 0),
    volume: clamp(2 - ((event.clientY - rect.top) / Math.max(1, rect.height)) * 2, 0, 2),
  };
}

function updateAutomationCursorReadout(point = null) {
  const el = $("automationPointReadout");
  if (!el) return;
  const target = state.envelope.target || "music";
  if (state.videoSpeed.selectedIndex >= 0) {
    const speedPoint = persistedVideoSpeedEnvelope()[state.videoSpeed.selectedIndex] || { time: state.timeline.cursorSec, speed: videoSpeedAt(state.timeline.cursorSec) };
    el.textContent = `Video speed point selected · ${formatTime(speedPoint.time)} · ${speedPoint.speed.toFixed(2)}× · default ${VIDEO_SPEED_DEFAULT.toFixed(2)}×`;
    return;
  }
  const value = point || { time: state.timeline.cursorSec, volume: envelopeValueAt(target, state.timeline.cursorSec) };
  const label = envelopeTargetLabel(target);
  const selected = state.envelope.selectedIndex >= 0 ? `${label} point selected` : "Volume automation";
  el.textContent = `${selected} · ${formatTime(value.time)} · vol ${value.volume.toFixed(2)} · video speed ${videoSpeedAt(state.timeline.cursorSec).toFixed(2)}× · music gain = master curve × lane curve × lane base × clip`;
}

function renderMusicClipBlock(track, leftPx, widthPx, looped = false, index = 0, repeated = false, lane = null) {
  const block = document.createElement("div");
  block.className = `musicBlock ready musicClip ${track.id === state.musicClip.selectedId ? "selected" : ""} ${repeated ? "repeated" : ""}`;
  block.style.left = `${leftPx}px`;
  block.style.width = `${widthPx}px`;
  block.dataset.clipId = track.id;
  if (lane) block.dataset.laneId = lane.id;
  block.innerHTML = `<span>${escapeHtml(lane?.label || track.label || shortPath(track.path))} · ${formatTime(lane ? clipDurationForClip(lane, track) : visualClipDuration(track))} · vol ${Number(track.volume ?? 1).toFixed(2)}${looped ? " · loop" : repeated ? " · repeat" : ""}</span>`;
  block.title = `${lane?.path || track.path}\nstart ${Number(track.start_time || 0).toFixed(2)}s · offset ${Number(track.offset_sec || 0).toFixed(2)}s · duration ${(lane ? clipDurationForClip(lane, track) : visualClipDuration(track)).toFixed(2)}s`;
  block.onclick = (event) => { event.stopPropagation(); selectMusicClip(track.id, lane?.id || track.lane_id || ""); };
  if (!repeated && !looped) {
    const leftHandle = document.createElement("b");
    leftHandle.className = "musicClipHandle left";
    leftHandle.title = "Trim left edge";
    leftHandle.addEventListener("pointerdown", (event) => beginMusicClipResize(event, track.id, "left", lane?.id || track.lane_id || ""));
    const rightHandle = document.createElement("b");
    rightHandle.className = "musicClipHandle right";
    rightHandle.title = "Trim right edge";
    rightHandle.addEventListener("pointerdown", (event) => beginMusicClipResize(event, track.id, "right", lane?.id || track.lane_id || ""));
    block.appendChild(leftHandle);
    block.appendChild(rightHandle);
    block.addEventListener("pointerdown", (event) => beginMusicClipDrag(event, track.id, lane?.id || track.lane_id || ""));
  }
  return block;
}

function clipDurationForClip(lane, clip) {
  const source = musicArrangement().sources.find((item) => item.id === lane.source_id || item.path === lane.path);
  const explicitDuration = Number(clip.duration_sec || clip.duration || 0);
  if (explicitDuration > 0) return Math.max(0, explicitDuration);
  return Math.max(0, Number(source?.duration || 0) - Number(clip.offset_sec || 0));
}

function selectedMusicClip() {
  const music = musicArrangement();
  const lane = selectedMusicLane();
  return lane?.clips.find((clip) => clip.id === state.musicClip.selectedId) || music.tracks.find((track) => track.id === state.musicClip.selectedId) || null;
}

function selectedMusicLane() {
  const music = musicArrangement();
  return music.lanes.find((lane) => lane.id === state.musicClip.selectedLaneId) || music.lanes.find((lane) => lane.clips.some((clip) => clip.id === state.musicClip.selectedId)) || music.lanes[0] || null;
}

function renderMusicClipEditor() {
  const root = $("musicClipControls");
  if (!root) return;
  const music = musicArrangement();
  const selected = selectedMusicClip();
  const selectedLane = selectedMusicLane();
  const sourceOptions = music.sources.map((source) => `<option value="${escapeHtml(source.id)}">${escapeHtml(source.label || shortPath(source.path))}</option>`).join("");
  root.innerHTML = `
    <label>Source <select id="musicSourceSelect">${sourceOptions}</select></label>
    <button id="addMusicClipBtn" type="button" class="secondary" ${music.sources.length ? "" : "disabled"}>Add at cursor</button>
    <button id="appendMusicClipBtn" type="button" class="secondary" ${music.sources.length ? "" : "disabled"}>Append</button>
    <label>Lane <select id="musicLaneSelect">${music.lanes.map((lane) => `<option value="${escapeHtml(lane.id)}" ${lane.id === selectedLane?.id ? "selected" : ""}>${escapeHtml(lane.label || shortPath(lane.path))}</option>`).join("")}</select></label>
    <label>Clip <select id="musicClipSelect">${music.tracks.map((track) => `<option value="${escapeHtml(track.id)}" ${track.id === selected?.id ? "selected" : ""}>${escapeHtml(track.label || shortPath(track.path))}</option>`).join("")}</select></label>
    <label>Start <input id="musicClipStart" type="number" min="0" step="0.05" value="${selected ? Number(selected.start_time || 0).toFixed(2) : "0.00"}" ${selected ? "" : "disabled"} /></label>
    <label>Volume <input id="musicClipVolume" type="number" min="0" max="2" step="0.01" value="${selected ? Number(selected.volume ?? 1).toFixed(2) : "1.00"}" ${selected ? "" : "disabled"} /></label>
    <button id="deleteMusicClipBtn" type="button" class="secondary" ${selected ? "" : "disabled"}>Delete clip</button>
  `;
  $("addMusicClipBtn").onclick = () => addCurrentMusicClip(false);
  $("appendMusicClipBtn").onclick = () => addCurrentMusicClip(true);
  const laneSelect = $("musicLaneSelect");
  if (laneSelect) laneSelect.onchange = () => selectMusicLane(laneSelect.value);
  const select = $("musicClipSelect");
  if (select) select.onchange = () => selectMusicClip(select.value, music.tracks.find((track) => track.id === select.value)?.lane_id || "");
  const sourceSelect = $("musicSourceSelect");
  if (sourceSelect) {
    sourceSelect.value = state.musicClip.selectedSourceId || sourceSelect.value;
    sourceSelect.onchange = () => selectMusicSource(sourceSelect.value);
  }
  const start = $("musicClipStart");
  if (start) start.onchange = () => updateSelectedMusicClip({ start_time: Number(start.value) });
  const volume = $("musicClipVolume");
  if (volume) volume.onchange = () => updateSelectedMusicClip({ volume: Number(volume.value) });
  $("deleteMusicClipBtn").onclick = deleteSelectedMusicClip;
}

function saveMusicTracks(tracks) {
  return saveMusicArrangement({ tracks });
}

function saveMusicLanes(lanes) {
  return saveMusicArrangement({ lanes, tracks: flattenMusicLanes(lanes) });
}

function selectMusicClip(id, laneId = "") {
  state.musicClip.selectedId = id;
  if (laneId) state.musicClip.selectedLaneId = laneId;
  renderTransportLanes();
}

function selectMusicLane(id) {
  state.musicClip.selectedLaneId = id;
  renderTransportLanes();
}

function createMusicLaneFromSource(source, clip = null) {
  return { id: crypto.randomUUID?.() || `lane_${Date.now()}_${Math.random().toString(16).slice(2)}`, source_id: source.id, path: source.path, label: source.label || shortPath(source.path), enabled: true, loop: false, volume: 1, volume_envelope: [{ time: 0, volume: 1 }], order: musicArrangement().lanes.length, clips: clip ? [clip] : [] };
}

function selectedMusicSource() {
  const music = musicArrangement();
  return music.sources.find((item) => item.id === state.musicClip.selectedSourceId) || music.sources[0] || null;
}

function selectMusicSource(id) {
  state.musicClip.selectedSourceId = id;
  const select = $("musicSourceSelect");
  if (select) select.value = id;
  renderMusicLibraryPanel();
}

function createMusicClipFromSource(source, startTime = state.timeline.cursorSec || 0) {
  return {
    id: crypto.randomUUID?.() || `clip_${Date.now()}_${Math.random().toString(16).slice(2)}`,
    source_id: source.id,
    path: source.path,
    label: source.label || shortPath(source.path),
    start_time: clamp(startTime, 0, Math.max(0, state.timeline.durationSec || startTime || 0)),
    offset_sec: 0,
    duration_sec: 0,
    volume: 1,
  };
}

function addClipToLaneOrNewLane(source, startTime = state.timeline.cursorSec || 0, laneId = "") {
  const music = musicArrangement();
  const clip = createMusicClipFromSource(source, startTime);
  const lanes = music.lanes.slice();
  let lane = lanes.find((item) => item.id === laneId && (item.source_id === source.id || item.path === source.path)) || lanes.find((item) => item.source_id === source.id || item.path === source.path);
  if (!lane) {
    lane = createMusicLaneFromSource(source, clip);
    lanes.push(lane);
  } else {
    lane.clips = lane.clips.concat([clip]);
  }
  state.musicClip.selectedId = clip.id;
  state.musicClip.selectedLaneId = lane.id;
  state.musicClip.selectedSourceId = source.id;
  return saveMusicLanes(lanes);
}

function addCurrentMusicClip(append = false) {
  const music = musicArrangement();
  const sourceId = $("musicSourceSelect")?.value || state.musicClip.selectedSourceId || music.sources[0]?.id || "";
  const source = music.sources.find((item) => item.id === sourceId) || music.sources[0];
  if (!source?.path) { setStatus("Upload or enter a music source first"); return; }
  const lastEnd = music.tracks.reduce((maxEnd, track) => Math.max(maxEnd, Number(track.start_time || 0) + visualClipDuration(track)), 0);
  const startTime = append ? lastEnd : (state.timeline.cursorSec || 0);
  addClipToLaneOrNewLane(source, startTime, state.musicClip.selectedLaneId).catch((err) => setStatus(`Add clip failed: ${err.message}`));
}

function updateSelectedMusicClip(patch) {
  const selected = selectedMusicClip();
  if (!selected) return;
  const lanes = musicArrangement().lanes.map((lane) => ({ ...lane, clips: lane.clips.map((clip) => clip.id === selected.id ? { ...clip, ...patch, start_time: clamp(patch.start_time ?? clip.start_time, 0, Math.max(0, state.timeline.durationSec || patch.start_time || 0)), offset_sec: clamp(patch.offset_sec ?? clip.offset_sec, 0, 999999), duration_sec: clamp(patch.duration_sec ?? clip.duration_sec ?? 0, 0, 999999), volume: clamp(patch.volume ?? clip.volume, 0, 2) } : clip) }));
  saveMusicLanes(lanes).catch((err) => setStatus(`Clip save failed: ${err.message}`));
}

function deleteSelectedMusicClip() {
  const selected = selectedMusicClip();
  if (!selected) return;
  const lanes = musicArrangement().lanes.map((lane) => ({ ...lane, clips: lane.clips.filter((clip) => clip.id !== selected.id) }));
  state.musicClip.selectedId = "";
  saveMusicLanes(lanes).catch((err) => setStatus(`Delete clip failed: ${err.message}`));
}

function updateMusicLane(laneId, patch) {
  const lanes = musicArrangement().lanes.map((lane) => {
    if (lane.id !== laneId) return lane;
    const nextVolume = clamp(patch.volume ?? lane.volume, 0, 2);
    const nextEnvelope = patch.volume_envelope ? normalizeLaneEnvelope(patch.volume_envelope) : normalizeLaneEnvelope(lane.volume_envelope);
    return { ...lane, ...patch, volume: nextVolume, volume_envelope: nextEnvelope };
  });
  saveMusicLanes(lanes).catch((err) => setStatus(`Lane save failed: ${err.message}`));
}

function resetMusicLaneCurve(laneId) {
  const lane = musicArrangement().lanes.find((item) => item.id === laneId);
  if (!lane) return;
  state.envelope.selectedIndex = -1;
  state.envelope.target = laneTarget(laneId);
  updateMusicLane(laneId, { volume_envelope: [{ time: 0, volume: 1 }] });
}

function deleteSelectedMusicLane() {
  const lane = selectedMusicLane();
  if (!lane) return;
  const lanes = musicArrangement().lanes.filter((item) => item.id !== lane.id).map((item, index) => ({ ...item, order: index }));
  state.musicClip.selectedLaneId = lanes[0]?.id || "";
  state.musicClip.selectedId = "";
  saveMusicLanes(lanes).catch((err) => setStatus(`Delete lane failed: ${err.message}`));
}

function deleteMusicSource(sourceId) {
  const music = musicArrangement();
  const source = music.sources.find((item) => item.id === sourceId);
  if (!source) return;
  const sources = music.sources.filter((item) => item.id !== sourceId);
  const lanes = music.lanes
    .filter((lane) => lane.source_id !== source.id && lane.path !== source.path)
    .map((lane, index) => ({ ...lane, order: index }));
  if (state.musicClip.selectedSourceId === sourceId) state.musicClip.selectedSourceId = sources[0]?.id || "";
  if (!lanes.some((lane) => lane.id === state.musicClip.selectedLaneId)) state.musicClip.selectedLaneId = lanes[0]?.id || "";
  if (!lanes.some((lane) => lane.clips.some((clip) => clip.id === state.musicClip.selectedId))) state.musicClip.selectedId = "";
  saveMusicArrangement({ sources, lanes, tracks: flattenMusicLanes(lanes) }).catch((err) => setStatus(`Delete source failed: ${err.message}`));
}

function beginMusicClipDrag(event, clipId, laneId = "") {
  if (event.button !== 0 || event.target.closest?.(".musicClipHandle")) return;
  event.preventDefault();
  event.stopPropagation();
  selectMusicClip(clipId, laneId);
  const startX = event.clientX;
  const lane = musicArrangement().lanes.find((item) => item.id === laneId) || selectedMusicLane();
  const track = lane?.clips.find((item) => item.id === clipId);
  const startTime = Number(track?.start_time || 0);
  const onMove = (moveEvent) => {
    const nextTime = clamp(startTime + ((moveEvent.clientX - startX) / Math.max(1, state.timeline.pixelsPerSecond || 96)), 0, Math.max(0, state.timeline.durationSec || startTime || 0));
    state.project.arrangement.music.lanes = musicArrangement().lanes.map((item) => item.id === lane?.id ? { ...item, clips: item.clips.map((clip) => clip.id === clipId ? { ...clip, start_time: nextTime } : clip) } : item);
    renderTransportLanes();
  };
  const onUp = () => {
    document.removeEventListener("pointermove", onMove);
    document.removeEventListener("pointerup", onUp);
    saveMusicLanes(musicArrangement().lanes).catch((err) => setStatus(`Clip drag save failed: ${err.message}`));
  };
  document.addEventListener("pointermove", onMove);
  document.addEventListener("pointerup", onUp, { once: true });
}

function beginMusicClipResize(event, clipId, edge, laneId = "") {
  if (event.button !== 0) return;
  event.preventDefault();
  event.stopPropagation();
  selectMusicClip(clipId, laneId);
  const lane = musicArrangement().lanes.find((item) => item.id === laneId) || selectedMusicLane();
  const track = lane?.clips.find((item) => item.id === clipId);
  if (!track) return;
  const startX = event.clientX;
  const startTime = Number(track.start_time || 0);
  const startOffset = Number(track.offset_sec || 0);
  const startDuration = lane ? clipDurationForClip(lane, track) || 8 : visualClipDuration(track);
  const sourceDuration = Number(musicArrangement().sources.find((item) => item.id === lane?.source_id || item.path === lane?.path)?.duration || 0);
  const minDuration = 0.05;
  const maxRightDuration = sourceDuration > 0 ? Math.max(minDuration, sourceDuration - startOffset) : 999999;
  const applyPatch = (patch) => {
    state.project.arrangement.music.lanes = musicArrangement().lanes.map((item) => item.id === lane?.id ? { ...item, clips: item.clips.map((clip) => clip.id === clipId ? { ...clip, ...patch } : clip) } : item);
    renderTransportLanes();
  };
  const onMove = (moveEvent) => {
    const deltaSec = (moveEvent.clientX - startX) / Math.max(1, state.timeline.pixelsPerSecond || 96);
    if (edge === "left") {
      const maxDelta = Math.min(startDuration - minDuration, sourceDuration > 0 ? Math.max(0, sourceDuration - startOffset - minDuration) : startDuration - minDuration);
      const delta = clamp(deltaSec, -startTime, maxDelta);
      applyPatch({
        start_time: roundTime(startTime + delta, 0.001),
        offset_sec: roundTime(Math.max(0, startOffset + delta), 0.001),
        duration_sec: roundTime(Math.max(minDuration, startDuration - delta), 0.001),
      });
    } else {
      const nextDuration = clamp(startDuration + deltaSec, minDuration, maxRightDuration);
      applyPatch({ duration_sec: roundTime(nextDuration, 0.001) });
    }
  };
  const onUp = () => {
    document.removeEventListener("pointermove", onMove);
    document.removeEventListener("pointerup", onUp);
    saveMusicLanes(musicArrangement().lanes).catch((err) => setStatus(`Clip trim save failed: ${err.message}`));
  };
  document.addEventListener("pointermove", onMove);
  document.addEventListener("pointerup", onUp, { once: true });
}

function renderMusicLibraryPanel() {
  const root = $("musicLibraryList");
  if (!root || !state.project) return;
  const music = musicArrangement();
  if (!state.musicClip.selectedSourceId && music.sources[0]) state.musicClip.selectedSourceId = music.sources[0].id;
  const loopBtn = $("musicLoopChainBtn");
  if (loopBtn) {
    loopBtn.classList.toggle("active", music.mode === "chain_loop");
    loopBtn.textContent = music.mode === "chain_loop" ? "Цепочка зациклена" : "Зациклить цепочку до конца";
  }
  const addButtonsDisabled = !music.sources.length;
  for (const id of ["musicLibraryAddAtCursorBtn", "musicLibraryAppendBtn"]) {
    const button = $(id);
    if (button) button.disabled = addButtonsDisabled;
  }
  if (!music.sources.length) {
    root.innerHTML = `<div class="chunkNavEmpty"><strong>Источников музыки нет</strong><small>Загрузите аудиофайлы или добавьте путь/URL.</small></div>`;
    return;
  }
  root.innerHTML = "";
  for (const source of music.sources) {
    const item = document.createElement("div");
    item.className = `musicLibraryItem ${source.id === state.musicClip.selectedSourceId ? "selected" : ""}`;
    item.draggable = true;
    item.dataset.sourceId = source.id;
    item.innerHTML = `
      <strong>${escapeHtml(source.label || shortPath(source.path))}</strong>
      <small>${escapeHtml(source.path)}</small>
      <small>${source.duration ? formatTime(source.duration) : "длительность загрузится после предпрослушивания"}</small>
      <button type="button" class="secondary deleteMusicSourceBtn">Удалить источник и дорожки</button>
    `;
    item.onclick = () => selectMusicSource(source.id);
    item.querySelector(".deleteMusicSourceBtn").onclick = (event) => { event.stopPropagation(); deleteMusicSource(source.id); };
    item.ondragstart = (event) => {
      selectMusicSource(source.id);
      event.dataTransfer.effectAllowed = "copy";
      event.dataTransfer.setData("text/plain", source.id);
      event.dataTransfer.setData("application/x-xtts-music-source", source.id);
    };
    root.appendChild(item);
  }
}

function addMusicSourceToTimeline(sourceId, startTime = state.timeline.cursorSec || 0) {
  const music = musicArrangement();
  const source = music.sources.find((item) => item.id === sourceId) || selectedMusicSource();
  if (!source?.path) { setStatus("Select or import a music source first"); return; }
  addClipToLaneOrNewLane(source, startTime, state.musicClip.selectedLaneId).catch((err) => setStatus(`Drop/add music clip failed: ${err.message}`));
}

function attachMusicLaneDrop(element, laneId = "") {
  element.addEventListener("dragover", (event) => {
    if (!event.dataTransfer.types.includes("application/x-xtts-music-source") && !event.dataTransfer.types.includes("text/plain")) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  });
  element.addEventListener("drop", (event) => {
    event.preventDefault();
    event.stopPropagation();
    const sourceId = event.dataTransfer.getData("application/x-xtts-music-source") || event.dataTransfer.getData("text/plain");
    const timelineLane = element.classList.contains("musicLaneRow") ? element : (element.querySelector?.(".musicLaneRow") || element.closest?.(".musicLaneRow") || element);
    const start = timeFromLaneClientX(event.clientX, timelineLane);
    const source = musicArrangement().sources.find((item) => item.id === sourceId) || selectedMusicSource();
    if (source) addClipToLaneOrNewLane(source, start, laneId).catch((err) => setStatus(`Drop/add music clip failed: ${err.message}`));
  });
}

function addSelectedMusicSourceAtCursor() {
  addMusicSourceToTimeline(state.musicClip.selectedSourceId, state.timeline.cursorSec || 0);
}

function appendSelectedMusicSource() {
  const music = musicArrangement();
  const lastEnd = music.tracks.reduce((maxEnd, track) => Math.max(maxEnd, Number(track.start_time || 0) + visualClipDuration(track)), 0);
  addMusicSourceToTimeline(state.musicClip.selectedSourceId, lastEnd);
}

function addMusicPathSourceFromValue(path, { addClip = false } = {}) {
  const cleanPath = (path || "").trim();
  if (!cleanPath) { setStatus("Enter a music/audio path or URL first"); return; }
  const music = musicArrangement();
  let source = music.sources.find((item) => item.path === cleanPath);
  const sources = music.sources.slice();
  if (!source) {
    source = { id: crypto.randomUUID?.() || `source_${Date.now()}`, path: cleanPath, label: shortPath(cleanPath) };
    sources.push(source);
  }
  const lanes = addClip ? music.lanes.concat([createMusicLaneFromSource(source, createMusicClipFromSource(source, state.timeline.cursorSec || 0))]) : music.lanes;
  state.musicClip.selectedSourceId = source.id;
  if (addClip && lanes.length) { state.musicClip.selectedLaneId = lanes.at(-1).id; state.musicClip.selectedId = lanes.at(-1).clips[0]?.id || ""; }
  saveMusicArrangement({ sources, lanes, tracks: flattenMusicLanes(lanes) }).catch((err) => setStatus(`Add audio source failed: ${err.message}`));
}

function beginEnvelopeDrag(event) {
  event.stopPropagation();
  event.preventDefault();
  const index = Number(event.currentTarget.dataset.index);
  const target = event.currentTarget.dataset.target || "music";
  if (event.altKey) {
    deleteEnvelopePoint(target, index);
    return;
  }
  state.envelope.selectedIndex = index;
  state.envelope.target = target;
  state.videoSpeed.selectedIndex = -1;
  updateAutomationCursorReadout(persistedEnvelope(target)[index]);
  let currentIndex = index;
  const onMove = (moveEvent) => {
    const points = persistedEnvelope(target);
    const dragged = envelopePointFromEvent(moveEvent, target);
    points[currentIndex] = dragged;
    points.sort((a, b) => a.time - b.time);
    currentIndex = points.findIndex((point) => point === dragged);
    state.envelope.selectedIndex = currentIndex;
    setLocalEnvelope(target, points);
    updateAutomationCursorReadout(dragged);
    renderTransportLanes();
  };
  const onUp = () => {
    document.removeEventListener("pointermove", onMove);
    document.removeEventListener("pointerup", onUp);
    saveEnvelope(target, persistedEnvelope(target)).catch((err) => setStatus(`Automation save failed: ${err.message}`));
  };
  document.addEventListener("pointermove", onMove);
  document.addEventListener("pointerup", onUp, { once: true });
}

function saveEnvelope(target, points) {
  if (target === "voice") return saveVoiceArrangement({ volume_envelope: points });
  if (isLaneEnvelopeTarget(target)) {
    const laneId = laneIdFromEnvelopeTarget(target);
    const lanes = musicArrangement().lanes.map((lane) => lane.id === laneId ? { ...lane, volume_envelope: normalizeLaneEnvelope(points) } : lane);
    return saveMusicLanes(lanes);
  }
  return saveMusicArrangement({ volume_envelope: points });
}

function setLocalEnvelope(target, points) {
  state.project.arrangement = state.project.arrangement || {};
  if (isLaneEnvelopeTarget(target)) {
    const laneId = laneIdFromEnvelopeTarget(target);
    state.project.arrangement.music = state.project.arrangement.music || {};
    state.project.arrangement.music.lanes = musicArrangement().lanes.map((lane) => lane.id === laneId ? { ...lane, volume_envelope: normalizeLaneEnvelope(points) } : lane);
    state.project.arrangement.music.tracks = flattenMusicLanes(state.project.arrangement.music.lanes);
    return;
  }
  state.project.arrangement[target] = state.project.arrangement[target] || {};
  state.project.arrangement[target].volume_envelope = points;
}

function setLocalVideoSpeedEnvelope(points) {
  state.project.arrangement = state.project.arrangement || {};
  state.project.arrangement.video = state.project.arrangement.video || {};
  state.project.arrangement.video.speed_envelope = points;
}

function saveVideoSpeedEnvelope(points) {
  return saveVideoArrangement({ speed_envelope: points });
}

function beginVideoSpeedDrag(event) {
  event.stopPropagation();
  event.preventDefault();
  const index = Number(event.currentTarget.dataset.index);
  if (event.altKey) {
    deleteVideoSpeedPoint(index);
    return;
  }
  state.envelope.selectedIndex = -1;
  state.videoSpeed.selectedIndex = index;
  updateAutomationCursorReadout();
  let currentIndex = index;
  const onMove = (moveEvent) => {
    const points = persistedVideoSpeedEnvelope();
    const dragged = videoSpeedPointFromEvent(moveEvent);
    points[currentIndex] = dragged;
    points.sort((a, b) => a.time - b.time);
    currentIndex = points.findIndex((point) => point === dragged);
    state.videoSpeed.selectedIndex = currentIndex;
    setLocalVideoSpeedEnvelope(points);
    applyPreviewVideoPlaybackRate();
    renderTransportLanes();
  };
  const onUp = () => {
    document.removeEventListener("pointermove", onMove);
    document.removeEventListener("pointerup", onUp);
    saveVideoSpeedEnvelope(persistedVideoSpeedEnvelope()).catch((err) => setStatus(`Video speed save failed: ${err.message}`));
  };
  document.addEventListener("pointermove", onMove);
  document.addEventListener("pointerup", onUp, { once: true });
}

function deleteVideoSpeedPoint(index = state.videoSpeed.selectedIndex) {
  const remaining = persistedVideoSpeedEnvelope().filter((_, i) => i !== index);
  const points = remaining.length ? remaining : [{ time: 0, speed: VIDEO_SPEED_DEFAULT }];
  state.videoSpeed.selectedIndex = -1;
  saveVideoSpeedEnvelope(points).catch((err) => setStatus(`Video speed delete failed: ${err.message}`));
}

function addVideoSpeedPoint(event) {
  const point = videoSpeedPointFromEvent(event);
  const points = persistedVideoSpeedEnvelope().concat([point]).sort((a, b) => a.time - b.time);
  state.envelope.selectedIndex = -1;
  state.videoSpeed.selectedIndex = points.findIndex((p) => p === point);
  updateAutomationCursorReadout();
  saveVideoSpeedEnvelope(points).catch((err) => setStatus(`Video speed save failed: ${err.message}`));
}

function deleteEnvelopePoint(target = state.envelope.target || "music", index = state.envelope.selectedIndex) {
  const remaining = persistedEnvelope(target).filter((_, i) => i !== index);
  const points = remaining.length ? remaining : [{ time: 0, volume: isLaneEnvelopeTarget(target) || target === "voice" ? 1 : Number(state.project?.settings?.music_volume ?? $("musicVolume")?.value ?? 0.18) }];
  state.envelope.selectedIndex = -1;
  saveEnvelope(target, points).catch((err) => setStatus(`Automation delete failed: ${err.message}`));
}

function addEnvelopePoint(event, target = "music") {
  const point = envelopePointFromEvent(event, target);
  const points = persistedEnvelope(target).concat([point]).sort((a, b) => a.time - b.time);
  state.envelope.selectedIndex = points.findIndex((p) => p === point);
  state.envelope.target = target;
  state.videoSpeed.selectedIndex = -1;
  updateAutomationCursorReadout(point);
  saveEnvelope(target, points).catch((err) => setStatus(`Automation save failed: ${err.message}`));
}

function shortPath(value) {
  return String(value || "").split(/[\\/]/).filter(Boolean).pop() || String(value || "");
}

function selectedVersionForChunk(chunk) {
  return (chunk.versions || []).find((v) => v.id === chunk.selected_version_id) || (chunk.versions || []).find((v) => v.audio_url) || null;
}

function selectedAudioUrlForChunk(chunk) {
  const selected = selectedVersionForChunk(chunk);
  return selected?.audio_url || chunk.audio_url || "";
}

function chunkSourceCandidates(project = state.project) {
  if (!project || typeof project !== "object") return [];
  const timeline = project.timeline;
  return [
    { label: "project.chunks", value: project.chunks },
    { label: "project.timeline[]", value: Array.isArray(timeline) ? timeline : null },
    { label: "project.timeline.chunks", value: timeline && !Array.isArray(timeline) ? timeline.chunks : null },
    { label: "project.project.chunks", value: project.project?.chunks },
    { label: "project.data.chunks", value: project.data?.chunks },
    { label: "project.payload.chunks", value: project.payload?.chunks },
    { label: "project.result.chunks", value: project.result?.chunks },
  ];
}

function projectShapeSummary(project = state.project) {
  if (!project || typeof project !== "object") return "project: none";
  const topKeys = Object.keys(project).slice(0, 12).join(", ") || "none";
  const parts = chunkSourceCandidates(project).map(({ label, value }) => `${label}=${Array.isArray(value) ? value.length : "not-array"}`);
  return `keys: ${topKeys}; ${parts.join("; ")}`;
}

function getChunks(project = state.project) {
  if (!project) return [];
  const candidates = chunkSourceCandidates(project).concat([
    { label: "project.arrangement.timeline.chunks", value: project.arrangement?.timeline?.chunks },
    { label: "project.arrangement.voice.chunks", value: project.arrangement?.voice?.chunks },
    { label: "project.timeline.items", value: project.timeline?.items },
  ]);
  const sourceEntry = candidates.find(({ value }) => Array.isArray(value) && value.length) || candidates.find(({ value }) => Array.isArray(value));
  const source = sourceEntry?.value || [];
  const seen = new Set();
  const chunks = source
    .filter((chunk) => chunk && typeof chunk === "object")
    .map((chunk, index) => ({ ...chunk, id: chunk.id || chunk.chunk_id || `chunk_${index}`, order: Number.isFinite(Number(chunk.order)) ? Number(chunk.order) : index }))
    .filter((chunk) => {
      if (seen.has(chunk.id)) return false;
      seen.add(chunk.id);
      return true;
    })
    .sort((a, b) => a.order - b.order);
  if (project === state.project && chunks.length) project.chunks = chunks;
  return chunks;
}

function selectedChunk() { return getChunks().find((chunk) => chunk.id === state.selectedChunkId) || null; }
function setScreenMode(mode) {
  state.screenMode = ["projects", "chunk", "project", "preview", "group"].includes(mode) ? mode : "project";
  renderCentralScreen();
}
function selectChunk(chunkId) {
  const chunk = getChunks().find((item) => item.id === chunkId);
  if (!chunk) return;
  state.selectedChunkId = chunk.id;
  state.chunkNav.activeId = chunk.id;
  state.screenMode = "chunk";
  renderCentralScreen();
  setActiveChunkNav(chunk.id);
}
function setSidePanelMode(mode) {
  state.sidePanelMode = mode === "groups" ? "groups" : "chunks";
  renderSidePanelMode();
}
function renderSidePanelMode() {
  const isGroups = state.sidePanelMode === "groups";
  $("chunkNavList")?.toggleAttribute("hidden", isGroups);
  $("groupNavList")?.toggleAttribute("hidden", !isGroups);
  $("chunksSideTab")?.classList.toggle("active", !isGroups);
  $("groupsSideTab")?.classList.toggle("active", isGroups);
  $("chunksSideTab")?.classList.toggle("secondary", isGroups);
  $("groupsSideTab")?.classList.toggle("secondary", !isGroups);
}
function selectGroup(groupId) {
  const group = groupTimelineSpans().find((item) => item.id === groupId);
  if (!group) return;
  state.selectedGroupId = group.id;
  state.sidePanelMode = "groups";
  state.screenMode = "group";
  renderCentralScreen();
  renderSidePanelMode();
  setActiveGroupNav(group.id);
  renderVideoGroupLanesHost();
}
function renderCentralScreen() {
  const isProjects = state.screenMode === "projects";
  const isChunk = state.screenMode === "chunk";
  const isPreview = state.screenMode === "preview";
  const isGroup = state.screenMode === "group";
  $("projectsScreen")?.classList.toggle("active", isProjects);
  $("projectScreen")?.classList.toggle("active", !isProjects && !isChunk && !isPreview && !isGroup);
  $("chunkScreen")?.classList.toggle("active", isChunk);
  $("previewScreen")?.classList.toggle("active", isPreview);
  $("groupScreen")?.classList.toggle("active", isGroup);
  $("projectsModeTab")?.classList.toggle("active", isProjects);
  $("projectModeTab")?.classList.toggle("active", !isProjects && !isChunk && !isPreview && !isGroup);
  $("chunkModeTab")?.classList.toggle("active", isChunk);
  $("previewModeTab")?.classList.toggle("active", isPreview);
  $("projectsModeTab")?.classList.toggle("secondary", !isProjects);
  $("projectModeTab")?.classList.toggle("secondary", isProjects || isChunk || isPreview || isGroup);
  $("chunkModeTab")?.classList.toggle("secondary", !isChunk);
  $("previewModeTab")?.classList.toggle("secondary", !isPreview);
  renderProjectsList();
  if (isChunk) renderChunkDetail(selectedChunk());
  if (isGroup) renderGroupDetail(selectedGroup());
  if (isPreview) renderPreviewScreen();
}

function renderPreviewScreen() {
  const frame = $("previewFrame");
  if (!frame) return;
  const group = selectedPreviewGroup();
  const image = group?.image || {};
  const video = group?.video || {};
  const hasVideo = Boolean(video.url);
  const hasImage = Boolean(image.url);
  const aspect = image.aspect_ratio || state.project?.settings?.image_aspect_ratio || "vertical";
  const isHorizontal = aspect === "horizontal";
  frame.classList.toggle("horizontal", isHorizontal);
  frame.classList.toggle("hasImage", hasImage && !hasVideo);
  frame.classList.toggle("hasVideo", hasVideo);
  const aspectLabel = $("previewAspectLabel");
  if (aspectLabel) aspectLabel.textContent = isHorizontal ? "16:9" : "9:16";
  const previewVideo = $("previewVideo");
  if (previewVideo) {
    previewVideo.loop = true;
    previewVideo.muted = true;
    previewVideo.playsInline = true;
    applyPreviewVideoPlaybackRate();
    if (hasVideo) {
      const currentSrc = previewVideo.getAttribute("src") || "";
      if (currentSrc !== video.url) {
        previewVideo.src = video.url;
        previewVideo.load();
      }
      previewVideo.hidden = false;
      const playPromise = previewVideo.play();
      if (playPromise?.catch) playPromise.catch(() => {});
    } else {
      if (!previewVideo.hidden || previewVideo.getAttribute("src")) {
        previewVideo.pause();
        previewVideo.removeAttribute("src");
        previewVideo.load();
      }
      previewVideo.hidden = true;
    }
  }
  if (hasVideo) {
    frame.style.removeProperty("background-image");
    $("previewTitle").textContent = group?.title || "Group video";
    $("previewDescription").textContent = `Preview: Loop video · speed ${videoSpeedAt(state.timeline.cursorSec).toFixed(2)}× · ${groupVideoMetaText(group)}`;
    $("previewImageHint").textContent = video.path ? `Video: ${video.path}` : "Selected group video preview.";
  } else if (hasImage) {
    frame.style.backgroundImage = `linear-gradient(180deg, rgba(8,11,17,.08), rgba(8,11,17,.38)), url("${image.url.replace(/"/g, "%22")}")`;
    $("previewTitle").textContent = group?.title || "Group image";
    $("previewDescription").textContent = `Preview: image · ${groupImageMetaText(group)}`;
    $("previewImageHint").textContent = image.path ? `Image: ${image.path}` : "Selected group image preview.";
  } else {
    frame.style.removeProperty("background-image");
    $("previewTitle").textContent = group ? `${group.title}: image ${groupImageStatus(group)}` : "Video preview placeholder";
    $("previewDescription").textContent = group ? (group.summary || "Картинка для группы ещё не сгенерирована.") : "Здесь появится вертикальный видеоряд, синхронизированный со смысловыми группами чанков.";
    $("previewImageHint").textContent = group ? "Для выбранной группы пока нет картинки — используйте генерацию в экране группы." : "Выберите группу с готовой картинкой, чтобы увидеть preview frame.";
  }
}

function renderChunkDetail(chunk) {
  const root = $("chunks");
  const placeholder = $("chunkDetailPlaceholder");
  if (!root) return;
  root.innerHTML = "";
  if (!chunk) {
    if (placeholder) placeholder.hidden = false;
    return;
  }
  if (placeholder) placeholder.hidden = true;
  root.appendChild(renderChunkCard(chunk));
}

function formatVersionDate(value) {
  if (!value) return "unknown time";
  const ms = Number(value) * 1000;
  if (!Number.isFinite(ms)) return "unknown time";
  return new Date(ms).toLocaleString();
}

function versionSettingsSummary(version) {
  const settings = version.settings || {};
  const parts = [];
  for (const key of ["temperature", "top_p", "top_k", "repetition_penalty", "length_penalty", "speed", "seed"]) {
    if (settings[key] !== undefined && settings[key] !== null) parts.push(`${key}: ${settings[key]}`);
  }
  return parts.length ? parts.join(" · ") : "No settings snapshot";
}

function chunkBoundaryType(chunk) {
  return ["sentence", "paragraph", "section"].includes(chunk?.boundary_type) ? chunk.boundary_type : "sentence";
}

function renderChunks() {
  renderChunkDetail(state.screenMode === "chunk" ? selectedChunk() : null);
  renderChunkNavigator();
  renderGroupNavigator();
}

function chunkNavSignature() {
  return getChunks().map((chunk) => `${chunk.id}:${chunk.order}:${Boolean(selectedAudioUrlForChunk(chunk))}:${chunk.selected_version_id || ""}:${chunkBoundaryType(chunk)}:${(chunk.text || "").slice(0, 48)}`).join("|");
}

function setActiveChunkNav(chunkId) {
  state.chunkNav.activeId = chunkId || state.chunkNav.activeId;
  document.querySelectorAll(".chunkNavItem").forEach((item) => item.classList.toggle("active", item.dataset.chunkId === state.chunkNav.activeId));
  document.querySelectorAll(".chunk").forEach((item) => item.classList.toggle("focused", item.dataset.chunkId === state.chunkNav.activeId));
}

function setActiveGroupNav(groupId) {
  state.selectedGroupId = groupId || state.selectedGroupId;
  document.querySelectorAll(".groupNavItem").forEach((item) => item.classList.toggle("active", item.dataset.groupId === state.selectedGroupId));
  document.querySelectorAll(".videoGroupLaneRow, .videoGroupBlock").forEach((item) => item.classList.toggle("selected", item.dataset.groupId === state.selectedGroupId));
}

function groupDetailSignature(group) {
  if (!group) return "";
  const image = group.image || {};
  const video = group.video || {};
  const imageTask = activeImageGroupTask(group.id);
  const videoTask = activeVideoGroupTask(group.id);
  const aiFields = ["visual_prompt", "negative_prompt", "animation_positive_prompt", "animation_negative_prompt", "grok_video_prompt", "mood", "scene_type", "video_motion_intensity", "video_loop_notes", "source", "media_layout", "default_media_duration_sec"]
    .map((key) => `${key}:${group[key] ?? ""}`)
    .join("|");
  return [
    group.id,
    group.title || "",
    group.summary || "",
    group.start,
    group.end,
    group.duration,
    (group.chunk_ids || []).join(","),
    aiFields,
    JSON.stringify(normalizeGroupMediaItems(group)),
    image.status || "",
    image.url || "",
    image.path || "",
    image.width || "",
    image.height || "",
    image.aspect_ratio || "",
    image.provider || "",
    image.model || "",
    image.seed ?? "",
    image.error || "",
    image.positive_prompt || "",
    image.negative_prompt || "",
    video.status || "",
    video.url || "",
    video.path || "",
    video.width || "",
    video.height || "",
    video.frames || "",
    video.fps || "",
    video.model_checkpoint || "",
    imageTask ? `${imageTask.id}:${imageTask.status}:${imageTask.progress_percent || 0}:${imageTask.stage || ""}` : "",
    videoTask ? `${videoTask.id}:${videoTask.status}:${videoTask.progress_percent || 0}:${videoTask.stage || ""}` : "",
    Boolean(state.project?.settings?.video_i2v_enabled),
    Boolean(state.project?.settings?.image_exclude_people),
  ].join("::");
}

function groupPromptInputId(groupId, key) {
  return `groupPrompt_${String(groupId || "").replace(/[^A-Za-z0-9_-]/g, "_")}_${key}`;
}

function renderChunkNavigator(force = false) {
  const root = $("chunkNavList");
  if (!root) return;
  const signature = chunkNavSignature();
  if (!force && signature === state.chunkNav.signature && root.dataset.rendered === "true") {
    setActiveChunkNav(state.chunkNav.activeId);
    return;
  }
  state.chunkNav.signature = signature;
  root.dataset.rendered = "true";
  root.innerHTML = "";
  const chunks = getChunks();
  if (!chunks.length) {
    root.innerHTML = `<div class="chunkNavEmpty"><strong>No chunks found in project</strong><small>Build ${escapeHtml(FRONTEND_BUILD)}</small><small>${escapeHtml(projectShapeSummary())}</small></div>`;
    return;
  }
  for (const chunk of chunks) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "chunkNavItem";
    item.dataset.chunkId = chunk.id;
    const ready = Boolean(selectedAudioUrlForChunk(chunk));
    const boundary = chunkBoundaryType(chunk);
    item.innerHTML = `<strong>#${chunk.order + 1}</strong><span>${escapeHtml((chunk.text || "").slice(0, 80))}</span><small class="${ready ? "ready" : "missing"}">${ready ? "generated" : "missing"} · ${escapeHtml(boundary)}</small>`;
    item.onclick = () => selectChunk(chunk.id);
    root.appendChild(item);
  }
  setActiveChunkNav(state.selectedChunkId || state.chunkNav.activeId || chunks[0]?.id || "");
}

function renderChunkMultiSelect(selectedIds = []) {
  const selected = new Set(selectedIds || []);
  return getChunks().map((chunk) => `
    <label class="chunkPick"><input type="checkbox" value="${escapeHtml(chunk.id)}" ${selected.has(chunk.id) ? "checked" : ""} /> #${chunk.order + 1} ${escapeHtml((chunk.text || "").slice(0, 80))}</label>
  `).join("");
}

function renderGroupNavigator() {
  const root = $("groupNavList");
  if (!root) return;
  const groups = groupTimelineSpans();
  root.innerHTML = "";
  if (!groups.length) {
    root.innerHTML = `<div class="chunkNavEmpty"><strong>Группы пока не найдены</strong><small>Сначала разделите текст на чанки.</small></div>`;
    return;
  }
  for (const group of groups) {
    const imageStatus = groupImageStatus(group);
    const item = document.createElement("button");
    item.type = "button";
    item.className = `groupNavItem image-${imageStatus}`;
    item.dataset.groupId = group.id;
    item.innerHTML = `
      <strong>${escapeHtml(group.title)}</strong>
      <span>${escapeHtml(group.summary)}</span>
      <small>${escapeHtml(formatTime(group.start))}–${escapeHtml(formatTime(group.end))} · ${group.chunk_ids.length} chunk(s)</small>
      <small class="imageStatusMini">image: ${escapeHtml(groupImageMetaText(group))}</small>
    `;
    item.onclick = () => selectGroup(group.id);
    root.appendChild(item);
  }
  setActiveGroupNav(state.selectedGroupId || groups[0]?.id || "");
}

function groupMediaUrl(item) {
  const raw = item?.url || item?.path || "";
  if (/^https?:\/\//i.test(raw) || String(raw).startsWith("/api/")) return raw;
  if (!raw) return "";
  return item.type === "video" ? `/api/video?path=${encodeURIComponent(raw)}` : `/api/image?path=${encodeURIComponent(raw)}`;
}

function addGroupMediaRow(card, sourceItem = {}, groupDuration = 1) {
  const list = card?.querySelector(".groupMediaList");
  if (!list) return null;
  list.querySelector(".groupMediaEmpty")?.remove();
  const rawPath = sourceItem.path || sourceItem.url || "";
  const row = document.createElement("div");
  row.className = "groupMediaItem";
  row.dataset.mediaId = sourceItem.id || `media_${Date.now()}_${Math.random().toString(16).slice(2)}`;
  const duration = clamp(sourceItem.duration_sec || sourceItem.visual_duration_sec || sourceItem.default_duration_sec || Math.min(5, Math.max(0.5, groupDuration || 5)), 0.1, 36000);
  row.innerHTML = `
    <label>Type <select data-media-field="type"><option value="image" ${sourceItem.type !== "video" ? "selected" : ""}>image</option><option value="video" ${sourceItem.type === "video" ? "selected" : ""}>video</option></select></label>
    <label>Path/URL <input type="text" data-media-field="path" value="${escapeHtml(rawPath)}" /></label>
    <label>Label <input type="text" data-media-field="label" value="${escapeHtml(sourceItem.label || shortPath(rawPath) || "Media")}" /></label>
    <label>Role <input type="text" data-media-field="role" value="${escapeHtml(sourceItem.role || "main")}" /></label>
    <label>Start offset <input type="number" min="0" step="0.05" data-media-field="start_offset_sec" value="${Number(sourceItem.start_offset_sec || 0).toFixed(2)}" /></label>
    <label>Duration <input type="number" min="0" step="0.05" data-media-field="duration_sec" value="${Number(duration).toFixed(2)}" /></label>
    <label>Fit <select data-media-field="fit"><option value="cover" ${sourceItem.fit !== "contain" && sourceItem.fit !== "fill" ? "selected" : ""}>cover</option><option value="contain" ${sourceItem.fit === "contain" ? "selected" : ""}>contain</option><option value="fill" ${sourceItem.fit === "fill" ? "selected" : ""}>fill</option></select></label>
    <button type="button" class="secondary deleteGroupMediaBtn">Delete media</button>
  `;
  row.querySelector(".deleteGroupMediaBtn").onclick = () => row.remove();
  list.appendChild(row);
  return row;
}

function selectGroupMediaPreview(card, item) {
  if (!card || !item) return;
  state.groupMedia.selectedId = item.id || "";
  card.querySelectorAll(".groupMediaThumb,.groupMediaTimelineBlock").forEach((el) => el.classList.toggle("selected", el.dataset.mediaId === state.groupMedia.selectedId));
  const preview = card.querySelector(".groupMediaPreview");
  const url = groupMediaUrl(item);
  if (!preview || !url) return;
  preview.innerHTML = item.type === "video"
    ? `<video src="${escapeHtml(url)}" controls muted loop playsinline></video><small>${escapeHtml(item.label || item.path || item.url || "Video")}</small>`
    : `<img src="${escapeHtml(url)}" alt="${escapeHtml(item.label || "Image preview")}" /><small>${escapeHtml(item.label || item.path || item.url || "Image")}</small>`;
}

function renderGroupMediaThumbs(card, group) {
  const root = card?.querySelector?.(".groupMediaThumbSections");
  if (!root) return;
  const items = normalizeGroupMediaItems(group);
  const sectionHtml = (type, title) => {
    const subset = items.filter((item) => item.type === type);
    return `<section class="groupMediaThumbSection"><h5>${title}</h5><div class="groupMediaThumbGrid">${subset.map((item) => {
      const url = groupMediaUrl(item);
      const media = type === "video" ? `<video src="${escapeHtml(url)}" muted loop playsinline></video>` : `<img src="${escapeHtml(url)}" alt="" />`;
      return `<button type="button" class="groupMediaThumb" draggable="true" data-media-id="${escapeHtml(item.id)}">${media}<span>${escapeHtml(item.label || shortPath(item.path || item.url))}</span></button>`;
    }).join("") || `<p class="groupMediaEmpty">No ${title.toLowerCase()} yet.</p>`}</div></section>`;
  };
  root.innerHTML = sectionHtml("image", "Images") + sectionHtml("video", "Videos");
  root.querySelectorAll(".groupMediaThumb").forEach((thumb) => {
    const item = items.find((media) => media.id === thumb.dataset.mediaId);
    thumb.onclick = () => selectGroupMediaPreview(card, item);
    thumb.ondragstart = (event) => {
      event.dataTransfer.effectAllowed = "copy";
      event.dataTransfer.setData("application/x-xtts-group-media", JSON.stringify(item));
    };
  });
  const selected = items.find((item) => item.id === state.groupMedia.selectedId) || items[0];
  if (selected) selectGroupMediaPreview(card, selected);
}

function renderGroupDetail(group, { force = false } = {}) {
  const root = $("groupDetail");
  const placeholder = $("groupDetailPlaceholder");
  if (!root) return;
  if (!group) {
    state.groupDetail.signature = "";
    root.innerHTML = "";
    if (placeholder) placeholder.hidden = false;
    return;
  }
  const signature = groupDetailSignature(group);
  if (!force && root.dataset.groupId === group.id && state.groupDetail.signature === signature && root.dataset.rendered === "true") return;
  state.groupDetail.signature = signature;
  root.dataset.groupId = group.id;
  root.dataset.rendered = "true";
  root.innerHTML = "";
  if (placeholder) placeholder.hidden = true;
  const editableFields = [
    ["title", "Title", "input"],
    ["summary", "Summary", "textarea"],
    ["visual_prompt", "Visual prompt", "textarea"],
    ["negative_prompt", "Negative prompt", "textarea"],
    ["animation_positive_prompt", "Animation positive prompt", "textarea"],
    ["animation_negative_prompt", "Animation negative prompt", "textarea"],
    ["grok_video_prompt", "Grok video prompt", "textarea"],
    ["mood", "Mood", "input"],
    ["scene_type", "Scene type", "input"],
    ["video_motion_intensity", "Video motion intensity", "input"],
    ["video_loop_notes", "Video loop notes", "textarea"],
  ];
  const mediaItems = normalizeGroupMediaItems(group);
  const mediaItemsHtml = mediaItems.map((item, index) => `
    <div class="groupMediaItem" data-media-index="${index}" data-media-id="${escapeHtml(item.id || `media_${index}`)}">
      <label>Type <select data-media-field="type"><option value="image" ${item.type === "image" ? "selected" : ""}>image</option><option value="video" ${item.type === "video" ? "selected" : ""}>video</option></select></label>
      <label>Path/URL <input type="text" data-media-field="path" value="${escapeHtml(item.path || item.url || "")}" /></label>
      <label>Label <input type="text" data-media-field="label" value="${escapeHtml(item.label || "")}" /></label>
      <label>Role <input type="text" data-media-field="role" value="${escapeHtml(item.role || "main")}" /></label>
      <label>Start offset <input type="number" min="0" step="0.05" data-media-field="start_offset_sec" value="${Number(item.start_offset_sec || 0).toFixed(2)}" /></label>
      <label>Duration <input type="number" min="0" step="0.05" data-media-field="duration_sec" value="${Number(item.duration_sec || 0).toFixed(2)}" /></label>
      <label>Fit <select data-media-field="fit"><option value="cover" ${item.fit === "cover" ? "selected" : ""}>cover</option><option value="contain" ${item.fit === "contain" ? "selected" : ""}>contain</option><option value="fill" ${item.fit === "fill" ? "selected" : ""}>fill</option></select></label>
      <button type="button" class="secondary deleteGroupMediaBtn">Delete media</button>
    </div>
  `).join("");
  const aiFieldsHtml = `
    <details class="groupPromptEditor" open>
      <summary class="groupPromptSummary"><h4>Editable group prompts</h4><span>click to collapse</span></summary>
      <div class="row between wrap">
        <span></span>
        <div class="row wrap">
          <button type="button" class="moveGroupUpBtn secondary">Group ↑</button>
          <button type="button" class="moveGroupDownBtn secondary">Group ↓</button>
          <button type="button" class="deleteGroupBtn secondary">Delete group</button>
          <button type="button" class="generateGroupPromptBtn secondary">Generate prompt for selected group</button>
          <button type="button" class="saveGroupPromptsBtn secondary">Save group</button>
        </div>
      </div>
      <details class="groupChunkMembership">
        <summary>Chunks in this group (editable)</summary>
        <div class="chunkPickGrid">${renderChunkMultiSelect(group.chunk_ids || [])}</div>
      </details>
      <div class="groupPromptGrid">
        ${editableFields.map(([key, label, type]) => {
          const id = groupPromptInputId(group.id, key);
          const value = group[key] ?? "";
          return type === "textarea"
            ? `<label>${escapeHtml(label)}<textarea id="${escapeHtml(id)}" data-group-field="${escapeHtml(key)}">${escapeHtml(value)}</textarea></label>`
            : `<label>${escapeHtml(label)}<input id="${escapeHtml(id)}" type="text" data-group-field="${escapeHtml(key)}" value="${escapeHtml(value)}" /></label>`;
        }).join("")}
      </div>
      <section class="groupMediaEditor">
        <div class="row between wrap">
          <h4>Group media schedule</h4>
          <button type="button" class="addGroupMediaBtn secondary">Add photo/video</button>
        </div>
        <div class="grid two imageSettingsGrid">
          <label>Layout <select data-group-setting="media_layout"><option value="sequence" ${(group.media_layout || "sequence") === "sequence" ? "selected" : ""}>sequence</option><option value="overlay" ${group.media_layout === "overlay" ? "selected" : ""}>overlay</option><option value="background" ${group.media_layout === "background" ? "selected" : ""}>background</option><option value="manual" ${group.media_layout === "manual" ? "selected" : ""}>manual</option></select></label>
          <label>Default duration, sec <input type="number" min="0" step="0.1" data-group-setting="default_media_duration_sec" value="${Number(group.default_media_duration_sec || 0).toFixed(1)}" /></label>
        </div>
        <div class="groupMediaTimelineHost"></div>
        <div class="groupMediaThumbSections"></div>
        <div class="groupMediaPreview" aria-live="polite"><div class="groupMediaPreviewEmpty">Select an image/video thumbnail or timeline block.</div></div>
        <div class="groupMediaList legacyHidden">${mediaItemsHtml || `<p class="groupMediaEmpty">No extra media yet. Generated image/video is still used automatically.</p>`}</div>
      </section>
      ${group.source ? `<p class="groupPromptSource">Source: ${escapeHtml(group.source)}</p>` : ""}
    </details>
  `;
  const image = group.image || {};
  const video = group.video || {};
  const imageStatus = groupImageStatus(group);
  const imageExists = Boolean(image.url || image.path || image.status === "done" || image.status === "fallback");
  const imageTask = activeImageGroupTask(group.id);
  const imageBusy = Boolean(imageTask);
  const videoStatus = groupVideoStatus(group);
  const videoExists = Boolean(video.url || video.path || video.status === "ready" || video.status === "done");
  const videoBusy = Boolean(activeVideoGroupTask(group.id));
  const i2vEnabled = Boolean(state.project?.settings?.video_i2v_enabled);
  const imagePreviewHtml = image.url
    ? `<img class="groupImageThumb" src="${escapeHtml(image.url)}" alt="${escapeHtml(group.title)} image preview" />`
    : `<div class="groupImageThumb missing">No image preview</div>`;
  const backendLabel = videoBackendLabel();
  const videoPreviewHtml = video.url
    ? `<video class="groupImageThumb" src="${escapeHtml(video.url)}" controls muted loop playsinline></video>`
    : `<div class="groupImageThumb missing">${video.error ? `${escapeHtml(backendLabel)} failed: ${escapeHtml(video.error)}` : `No ${escapeHtml(backendLabel)} video yet`}</div>`;
  const promptHtml = (image.positive_prompt || image.negative_prompt) ? `
    <details class="groupImagePrompts">
      <summary>Prompt used</summary>
      <h4>Positive prompt</h4>
      <pre>${escapeHtml(image.positive_prompt || "")}</pre>
      <h4>Negative prompt used</h4>
      <pre>${escapeHtml(image.negative_prompt || "")}</pre>
    </details>
  ` : "";
  const card = document.createElement("article");
  card.className = "groupDetailCard";
  card.innerHTML = `
    <div class="groupDetailHead">
      <div>
        <h3>${escapeHtml(group.title)}</h3>
        <p>${escapeHtml(group.summary)}</p>
      </div>
      <span class="groupDurationBadge">${escapeHtml(formatTime(group.duration))}</span>
    </div>
    <dl class="groupMetaGrid">
      <div><dt>Start</dt><dd>${escapeHtml(formatTime(group.start))}</dd></div>
      <div><dt>End</dt><dd>${escapeHtml(formatTime(group.end))}</dd></div>
      <div><dt>Duration</dt><dd>${escapeHtml(formatTime(group.duration))}</dd></div>
      <div><dt>Chunk ids</dt><dd>${escapeHtml(group.chunk_ids.join(", "))}</dd></div>
    </dl>
    ${aiFieldsHtml}
    <section class="groupImagePanel image-${escapeHtml(imageStatus)}">
      <div class="groupImageHead">
        <div>
          <h4>Картинка группы</h4>
          <p>${imageBusy ? "Картинка в очереди/генерируется" : escapeHtml(groupImageMetaText(group))}</p>
          ${image.error ? `<p class="groupImageError">${escapeHtml(image.error)}</p>` : ""}
        </div>
        <div class="row wrap">
          <button type="button" class="generateGroupImageBtn" ${imageBusy ? "disabled" : ""}>${imageExists ? "Перегенерировать" : "Сгенерировать картинку"}</button>
          <button type="button" class="generateGroupVideoBtn" ${videoBusy || !imageExists || !i2vEnabled ? "disabled" : ""}>${videoExists ? `Перегенерировать ${escapeHtml(backendLabel)}-видео` : `Сгенерировать ${escapeHtml(backendLabel)}-видео`}</button>
        </div>
      </div>
      <div class="groupImageBody">
        ${imagePreviewHtml}
        ${videoPreviewHtml}
        <dl class="groupImageMeta">
          <div><dt>Status</dt><dd>${escapeHtml(imageStatus)}</dd></div>
          <div><dt>Provider</dt><dd>${escapeHtml(image.provider || "—")}</dd></div>
          <div><dt>Model</dt><dd>${escapeHtml(image.model || "—")}</dd></div>
          <div><dt>Aspect</dt><dd>${escapeHtml(image.aspect_ratio || "—")}</dd></div>
          <div><dt>Size</dt><dd>${escapeHtml(image.width && image.height ? `${image.width}×${image.height}` : "—")}</dd></div>
          <div><dt>Seed</dt><dd>${escapeHtml(image.seed ?? "—")}</dd></div>
          <div><dt>Video</dt><dd>${escapeHtml(groupVideoMetaText(group))}</dd></div>
        </dl>
        ${video.error ? `<p class="groupImageError">${escapeHtml(video.error)}</p>` : ""}
      </div>
      ${promptHtml}
    </section>
  `;
  const savePromptsButton = card.querySelector(".saveGroupPromptsBtn");
  const generateImageButton = card.querySelector(".generateGroupImageBtn");
  const generateVideoButton = card.querySelector(".generateGroupVideoBtn");
  card.querySelector(".moveGroupUpBtn")?.addEventListener("click", () => moveGroup(group.id, "up"));
  card.querySelector(".moveGroupDownBtn")?.addEventListener("click", () => moveGroup(group.id, "down"));
  card.querySelector(".deleteGroupBtn")?.addEventListener("click", () => deleteGroup(group.id));
  card.querySelector(".generateGroupPromptBtn")?.addEventListener("click", () => generateSelectedGroupPrompt(group.id));
  card.querySelector(".addGroupMediaBtn")?.addEventListener("click", () => addGroupMediaItem(group.id));
  card.querySelectorAll(".deleteGroupMediaBtn").forEach((button) => button.onclick = (event) => {
    event.preventDefault();
    button.closest(".groupMediaItem")?.remove();
  });
  if (savePromptsButton) savePromptsButton.onclick = () => saveGroupPrompts(group.id, card);
  else console.warn("Group prompt save button missing", { groupId: group.id });
  if (generateImageButton) generateImageButton.onclick = () => enqueueGroupImage(group.id, imageExists);
  else console.warn("Group image button missing", { groupId: group.id });
  if (generateVideoButton) generateVideoButton.onclick = () => enqueueGroupVideo(group.id, videoExists);
  else console.warn("Group video button missing", { groupId: group.id });
  root.appendChild(card);
  renderGroupMediaThumbs(card, group);
  renderGroupMediaTimeline(card, group);
}

function renderGroupMediaTimeline(card, group) {
  const host = card?.querySelector?.(".groupMediaTimelineHost");
  const timeline = window.XTTSStudio?.GroupMediaTimeline;
  if (!host || !timeline) return;
  const renderFromRows = () => timeline.render(host, group, timeline.normalizedItemsFromRows(card, group.duration), { selectedId: state.groupMedia.selectedId });
  renderFromRows();
  timeline.bind(host, card, group, renderFromRows, {
    onSelect: (item) => selectGroupMediaPreview(card, item),
    onAdd: (item) => addGroupMediaRow(card, item, group.duration),
    onChange: () => saveGroupPrompts(group.id, card),
  });
}

async function saveGroupPrompts(groupId, card) {
  if (!groupId || !card) return;
  const payload = {};
  card.querySelectorAll("[data-group-field]").forEach((field) => {
    payload[field.dataset.groupField] = field.value || "";
  });
  payload.chunk_ids = [...card.querySelectorAll(".chunkPick input[type='checkbox']:checked")].map((input) => input.value);
  payload.media_layout = card.querySelector("[data-group-setting='media_layout']")?.value || "sequence";
  payload.default_media_duration_sec = Number(card.querySelector("[data-group-setting='default_media_duration_sec']")?.value || 0);
  payload.media_items = [...card.querySelectorAll(".groupMediaItem")].map((row) => {
    const value = (field) => row.querySelector(`[data-media-field='${field}']`)?.value || "";
    const pathOrUrl = value("path");
    const item = {
      id: row.dataset.mediaId || undefined,
      type: value("type") || "image",
      path: /^https?:\/\//i.test(pathOrUrl) ? "" : pathOrUrl,
      url: /^https?:\/\//i.test(pathOrUrl) ? pathOrUrl : "",
      label: value("label"),
      role: value("role") || "main",
      start_offset_sec: Number(value("start_offset_sec") || 0),
      duration_sec: Number(value("duration_sec") || 0),
      fit: value("fit") || "cover",
    };
    return item;
  });
  try {
    setStatus("Saving group prompts…", true);
    const data = await api(`/api/project/groups/${encodeURIComponent(groupId)}${activeProjectQuery()}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    if (data.project) state.project = data.project;
    buildTimelineArrangement();
    render();
    setStatus("Group prompts saved");
  } catch (err) {
    setStatus(`Group prompt save failed: ${err.message}`);
  }
}

function addGroupMediaItem(groupId) {
  const card = document.querySelector(`.groupDetailCard`);
  addGroupMediaRow(card, { type: "image", label: "Manual media" }, selectedGroup()?.duration || 1);
  renderGroupMediaTimeline(card, selectedGroup() || { duration: 1 });
  setStatus(`Added media row for ${groupId}; save group to persist`);
}

async function generateSelectedGroupPrompt(groupId) {
  if (!groupId) return;
  try {
    setStatus("Generating prompt for selected group…", true);
    const data = await api(`/api/project/groups/${encodeURIComponent(groupId)}/prompt${activeProjectQuery()}`, { method: "POST", body: "{}" });
    if (data.project) state.project = data.project;
    render();
    setStatus("Selected group prompt generated");
  } catch (err) { setStatus(`Group prompt generation failed: ${err.message}`); }
}

async function moveGroup(groupId, direction) {
  try {
    state.project = await api(`/api/project/groups/${encodeURIComponent(groupId)}/move${activeProjectQuery()}`, { method: "POST", body: JSON.stringify({ direction }) });
    render();
    setStatus("Group moved");
  } catch (err) { setStatus(`Group move failed: ${err.message}`); }
}

async function deleteGroup(groupId) {
  if (!confirm(`Delete group ${groupId}? Chunks are kept and can be assigned to another/new group.`)) return;
  try {
    state.project = await api(`/api/project/groups/${encodeURIComponent(groupId)}${activeProjectQuery()}`, { method: "DELETE" });
    state.selectedGroupId = videoGroups()[0]?.id || "";
    render();
    setStatus("Group deleted");
  } catch (err) { setStatus(`Group delete failed: ${err.message}`); }
}

async function addManualGroup() {
  try {
    const chunks = getChunks();
    const cursorChunk = state.timeline.arrangement.find((part) => state.timeline.cursorSec >= part.start && state.timeline.cursorSec <= part.nextStart)?.chunk;
    const chunk_ids = cursorChunk ? [cursorChunk.id] : (chunks[0] ? [chunks[0].id] : []);
    state.project = await api(`/api/project/groups${activeProjectQuery()}`, { method: "POST", body: JSON.stringify({ title: "Manual group", summary: "", chunk_ids, insert_after_group_id: state.selectedGroupId || "" }) });
    state.sidePanelMode = "groups";
    state.screenMode = "group";
    render();
    setStatus("Manual group added");
  } catch (err) { setStatus(`Add group failed: ${err.message}`); }
}

function setGroupAiStatus(message, tone = "") {
  const el = $("groupAiStatus");
  if (!el) return;
  el.textContent = message || "Ключ можно задать в настройках проекта или через XAI_API_KEY.";
  el.className = `groupAiStatus ${tone}`.trim();
}

function activeGrokGroupsTask() {
  const projectId = state.project?.id || state.activeProjectId || "";
  const queues = [state.queue || [], state.project?.queue || []];
  for (const tasks of queues) {
    const task = (tasks || []).find((item) => item?.kind === "grok_groups"
      && (!projectId || item.project_id === projectId)
      && ["queued", "running"].includes(item.status));
    if (task) return task;
  }
  return null;
}

function isGrokGroupingActive() {
  return Boolean(activeGrokGroupsTask());
}

function syncGroupAiTaskUi() {
  const task = activeGrokGroupsTask();
  const button = $("generateAiGroupsBtn");
  if (button) button.disabled = Boolean(task);
  if (!task) return false;
  const message = task.status === "queued"
    ? "Grok в очереди..."
    : `Grok группирует...${task.stage ? ` ${task.stage}` : ""}`;
  setGroupAiStatus(message, "busy");
  return true;
}

function syncImageTaskUi() {
  const allButton = $("queueAllImagesBtn");
  const allVideosButton = $("queueAllVideosBtn");
  const activeAny = Boolean(activeImageGroupTask() || activeVideoGroupTask());
  syncBulkVideoButtonLabel();
  if (allButton) allButton.disabled = activeAny;
  if (allVideosButton) allVideosButton.disabled = activeAny || !state.project?.settings?.video_i2v_enabled;
  if (state.screenMode === "group") renderGroupDetail(selectedGroup());
  return activeAny;
}

async function enqueueGroupVideo(groupId, force = false) {
  if (!groupId) return;
  try {
    await saveSettings();
    const backend = videoBackendLabel();
    setStatus(force ? `Queueing ${backend} video regeneration…` : `Queueing ${backend} video generation…`, true);
    const data = await api(`/api/project/groups/${encodeURIComponent(groupId)}/video${activeProjectQuery()}`, {
      method: "POST",
      body: JSON.stringify({ force: Boolean(force) }),
    });
    if (data.project) state.project = data.project;
    state.queue = data.queue || state.queue;
    state.progress = data.progress || state.progress;
    rememberTaskStatuses(state.queue);
    render();
    setStatus(`${backend} group video queued`, true);
  } catch (err) {
    setStatus(`${videoBackendLabel()} video queue failed: ${err.message}`);
  }
}

async function enqueueGroupImage(groupId, force = false) {
  if (!groupId) return;
  try {
    await saveSettings();
    setStatus(force ? "Queueing group image regeneration…" : "Queueing group image generation…", true);
    const data = await api(`/api/project/groups/${encodeURIComponent(groupId)}/image${activeProjectQuery()}`, {
      method: "POST",
      body: JSON.stringify({ force: Boolean(force) }),
    });
    if (data.project) state.project = data.project;
    state.queue = data.queue || state.queue;
    state.progress = data.progress || state.progress;
    rememberTaskStatuses(state.queue);
    render();
    setStatus("Group image queued", true);
  } catch (err) {
    setStatus(`Group image queue failed: ${err.message}`);
  }
}

async function enqueueAllGroupImages() {
  try {
    await saveSettings();
    const missingOnly = $("imageMissingOnly")?.checked !== false;
    setStatus("Queueing group images…", true);
    const data = await api(`/api/project/groups/images${activeProjectQuery()}`, {
      method: "POST",
      body: JSON.stringify({ missing_only: missingOnly, force: false }),
    });
    if (data.project) state.project = data.project;
    state.queue = data.queue || state.queue;
    state.progress = data.progress || state.progress;
    rememberTaskStatuses(state.queue);
    render();
    setStatus("Group images queued", true);
  } catch (err) {
    setStatus(`Group images queue failed: ${err.message}`);
  }
}

async function enqueueAllGroupVideos() {
  try {
    await saveSettings();
    const missingOnly = $("imageMissingOnly")?.checked !== false;
    const backend = videoBackendLabel();
    setStatus(`Queueing ${backend} group videos…`, true);
    const data = await api(`/api/project/groups/videos${activeProjectQuery()}`, {
      method: "POST",
      body: JSON.stringify({ missing_only: missingOnly, force: false }),
    });
    if (data.project) state.project = data.project;
    state.queue = data.queue || state.queue;
    state.progress = data.progress || state.progress;
    rememberTaskStatuses(state.queue);
    render();
    setStatus(`${backend} group videos queued: ${(data.queued_tasks || []).length}, skipped: ${data.skipped_count || 0}`, true);
  } catch (err) {
    setStatus(`${videoBackendLabel()} videos queue failed: ${err.message}`);
  }
}

async function generateAiGroups() {
  const button = $("generateAiGroupsBtn");
  const chunks = getChunks();
  if (isGrokGroupingActive()) {
    syncGroupAiTaskUi();
    setStatus("Grok AI grouping is already queued/running", true);
    return;
  }
  if (!state.project) {
    setGroupAiStatus("Откройте проект перед AI-группировкой.", "error");
    setStatus("Open a project first");
    return;
  }
  if (!chunks.length) {
    setGroupAiStatus("Сначала разделите текст на чанки.", "error");
    setStatus("Split text into chunks first");
    return;
  }
  if (!state.project?.settings?.xai_api_key_configured) {
    const message = "Grok/xAI API key is not configured. Задайте ключ в настройках проекта или через XAI_API_KEY и перезапустите XTTS Studio.";
    setGroupAiStatus(message, "error");
    setStatus(message);
    return;
  }
  const previousGroupId = state.selectedGroupId;
  try {
    if (button) button.disabled = true;
    setGroupAiStatus("Grok ставится в очередь…", "busy");
    setStatus("Queueing Grok AI grouping…", true);
    const data = await api(`/api/project/groups/ai${activeProjectQuery()}`, {
      method: "POST",
      body: JSON.stringify({ fallback_on_error: true, strategy: "auto", max_section_chunks: 40, max_request_chars: 22000, exclude_people_from_images: Boolean($("imageExcludePeople")?.checked) }),
    });
    state.project = data.project || state.project;
    state.queue = data.queue || state.queue;
    state.progress = data.progress || state.progress;
    rememberTaskStatuses(state.queue);
    patchProjectChunksFromProject(state.project);
    buildTimelineArrangement();
    const groups = videoGroups();
    state.selectedGroupId = groups.some((group) => group.id === previousGroupId) ? previousGroupId : state.selectedGroupId;
    state.sidePanelMode = "groups";
    state.screenMode = "group";
    render();
    syncGroupAiTaskUi();
    setStatus("Grok AI grouping queued", true);
  } catch (err) {
    const rawMessage = err?.message || String(err);
    const message = rawMessage === "Not Found"
      ? "AI grouping endpoint /api/project/groups/ai is not available. Restart XTTS Studio backend so the latest studio_server.py is loaded."
      : rawMessage;
    setGroupAiStatus(`Ошибка AI-группировки: ${message}`, "error");
    setStatus(`AI grouping failed: ${message}`);
  } finally {
    if (button && !isGrokGroupingActive()) button.disabled = false;
  }
}

function renderChunkCard(chunk) {
  const selectedVersion = selectedVersionForChunk(chunk);
  const selectedLabel = selectedVersion ? (selectedVersion.label || selectedVersion.id) : "none";
  const selectedAudioUrl = selectedAudioUrlForChunk(chunk);
  const boundary = chunkBoundaryType(chunk);
  const ttsText = chunk.tts_text || chunk.stressed_text || chunk.text || "";
  const hasStressedText = Boolean((chunk.stressed_text || chunk.tts_text || "").includes("\u0301"));
  const stressLabel = hasStressedText ? ` · stress: ${escapeHtml(chunk.stress_source || "grok")}` : "";
  const card = document.createElement("article");
  card.className = "chunk";
  card.id = `chunk-card-${chunk.id}`;
  card.tabIndex = -1;
  card.dataset.chunkId = chunk.id;
  card.innerHTML = `
    <div class="chunkHead">
      <strong>Chunk ${chunk.order + 1}</strong>
      <span><small class="boundaryBadge">${escapeHtml(boundary)}</small> start ${chunk.start_time || 0}s · selected ${escapeHtml(selectedLabel)} · duration ${chunk.duration_sec || 0}s · pause after ${(chunk.pause_after ?? 0)}s${stressLabel}</span>
    </div>
    <label class="chunkTtsLabel">TTS text ${hasStressedText ? "<small class=\"stressBadge\">stress marks visible/editable</small>" : "<small>TTS uses this text</small>"}<textarea class="chunkTtsText">${escapeHtml(ttsText)}</textarea></label>
    <details class="originalTextDetails">
      <summary>Original text (kept for reference)</summary>
      <textarea class="chunkText">${escapeHtml(chunk.text || "")}</textarea>
    </details>
    <div class="row wrap">
      <label>Pause after, sec <input class="pauseAfter" type="number" min="0" max="10" step="0.01" value="${clampPauseAfter(chunk.pause_after ?? 0)}" /></label>
      <button type="button" class="saveChunk secondary">Save</button>
      <button type="button" class="addChunkAfter secondary">Add after</button>
      <button type="button" class="deleteChunk secondary">Delete</button>
      <button type="button" class="generateChunk">Generate another version</button>
      <button type="button" class="moveUp secondary">↑</button>
      <button type="button" class="moveDown secondary">↓</button>
    </div>
    <div class="audioSlot selectedAudio"><strong>Selected for export:</strong> ${selectedAudioUrl ? `<audio controls src="${selectedAudioUrl}"></audio>` : "No selected audio yet."}</div>
    <div class="versions"></div>
  `;
  card.querySelector(".saveChunk").onclick = () => updateChunk(chunk.id, {
    text: card.querySelector(".chunkText").value,
    tts_text: card.querySelector(".chunkTtsText").value,
    pause_after: clampPauseAfter(card.querySelector(".pauseAfter").value),
  });
  card.querySelector(".addChunkAfter").onclick = () => addChunkAfter(chunk.id);
  card.querySelector(".deleteChunk").onclick = () => deleteChunk(chunk.id);
  card.querySelector(".generateChunk").onclick = () => generateChunk(chunk.id, card);
  card.querySelector(".moveUp").onclick = () => moveChunk(chunk.id, "up");
  card.querySelector(".moveDown").onclick = () => moveChunk(chunk.id, "down");
  const versionsRoot = card.querySelector(".versions");
  const versions = chunk.versions || [];
  if (versions.length) {
    versionsRoot.innerHTML = `<div class="versionsTitle">Versions for this chunk</div>` + versions.map((v, i) => {
      const isSelected = v.id === chunk.selected_version_id;
      const label = v.label || `Version ${v.index || i + 1}`;
      return `
      <div class="versionRow ${isSelected ? "selected" : ""}">
        <label class="versionPick"><input type="radio" name="ver_${chunk.id}" ${isSelected ? "checked" : ""} /> Use in final export</label>
        <div class="versionMeta">
          <strong>${escapeHtml(label)} ${isSelected ? "✓ selected" : ""}</strong>
          <small>${Number(v.duration_sec || 0).toFixed(3)}s · ${escapeHtml(formatVersionDate(v.created_at))}</small>
          <small>${escapeHtml(versionSettingsSummary(v))}</small>
        </div>
        ${v.audio_url ? `<audio controls src="${v.audio_url}"></audio>` : `<span class="missingVersion">Missing audio file</span>`}
        <button type="button" class="secondary useVersion" ${isSelected ? "disabled" : ""}>Select</button>
      </div>
    `;
    }).join("");
    [...versionsRoot.querySelectorAll(".versionRow")].forEach((row, i) => {
      row.querySelector("input").onchange = () => selectVersion(chunk.id, versions[i].id);
      row.querySelector(".useVersion").onclick = () => selectVersion(chunk.id, versions[i].id);
    });
  } else {
    versionsRoot.textContent = "No versions yet.";
  }
  return card;
}

function replaceChunkCard(chunk) {
  const root = $("chunks");
  const existing = root.querySelector(`[data-chunk-id="${CSS.escape(chunk.id)}"]`);
  const card = renderChunkCard(chunk);
  if (existing) {
    existing.replaceWith(card);
  } else {
    root.appendChild(card);
  }
}

function renderExport() {
  const exp = state.project.export;
  const root = $("exportResult");
  if (!root) return;
  if (!exp || !exp.url) {
    root.innerHTML = "No export yet.";
    return;
  }
  const isVideo = exp.media_type === "video" || /\.(mp4|webm|mov)$/i.test(exp.path || "");
  const details = [
    exp.duration_sec ? `${escapeHtml(exp.duration_sec)}s` : "",
    exp.sample_rate ? `${escapeHtml(exp.sample_rate)} Hz` : "",
    exp.format ? String(exp.format).toUpperCase() : "",
    exp.width && exp.height ? `${escapeHtml(exp.width)}×${escapeHtml(exp.height)}` : "",
    exp.fps ? `${escapeHtml(exp.fps)} fps` : "",
  ].filter(Boolean).join(" · ");
  root.innerHTML = `
    <a href="${exp.url}" download>Download ${escapeHtml(exp.path || "export")}</a>
    <p>${details}</p>
    ${isVideo ? `<video controls src="${exp.url}" class="exportPreviewVideo"></video>` : `<audio controls src="${exp.url}"></audio>`}
    ${exp.timeline_fidelity ? `<p class="imageResolvedSettings">${escapeHtml(exp.timeline_fidelity)}</p>` : ""}
  `;
}

function exportPayloadFromUi() {
  const sampleRateValue = $("exportSampleRate")?.value || "";
  return {
    export_type: $("exportType")?.value || "audio",
    audio_format: $("exportAudioFormat")?.value || "wav",
    audio_bitrate: $("exportAudioBitrate")?.value || "192k",
    sample_rate: sampleRateValue ? Number(sampleRateValue) : null,
    channels: Number($("exportChannels")?.value || 1),
    video_format: $("exportVideoFormat")?.value || "mp4",
    orientation: $("exportOrientation")?.value || "auto",
    resolution: $("exportResolution")?.value || "720p",
    fps: Number($("exportFps")?.value || 30),
    video_quality: $("exportVideoQuality")?.value || "medium",
    video_fit: $("exportVideoFit")?.value || "cover",
  };
}

function syncExportSettingsUi() {
  const isVideo = ($("exportType")?.value || "audio") === "video";
  for (const id of ["exportVideoFormat", "exportOrientation", "exportResolution", "exportFps", "exportVideoFit", "exportVideoQuality"]) {
    const el = $(id);
    if (!el) continue;
    el.closest("label")?.classList.toggle("disabledSetting", !isVideo);
    el.disabled = !isVideo;
  }
  const audioFormat = $("exportAudioFormat")?.value || "wav";
  const bitrate = $("exportAudioBitrate");
  if (bitrate) {
    bitrate.disabled = audioFormat === "wav" || audioFormat === "flac";
    bitrate.closest("label")?.classList.toggle("disabledSetting", bitrate.disabled);
  }
}

function renderCurrentProjectInfo() {
  const el = $("currentProjectInfo");
  if (!el) return;
  const p = state.project;
  el.textContent = p ? `Project: ${p.name || p.id || "unnamed"} · ${p.id || "no-id"}` : "Project: none selected";
}

function renderProjectsList() {
  const root = $("projectsList");
  if (!root) return;
  if (!state.projects.length) {
    root.innerHTML = "No projects yet.";
    return;
  }
  root.innerHTML = "";
  for (const project of state.projects) {
    const active = project.id === state.activeProjectId;
    const card = document.createElement("article");
    card.className = `projectCard ${active ? "active" : ""}`;
    card.innerHTML = `
      <strong>${escapeHtml(project.name || project.id)} ${active ? "· active" : ""}</strong>
      <small>${escapeHtml(project.id)} · updated ${escapeHtml(formatVersionDate(project.updated_at))}</small>
      <div class="projectCardActions">
        <button type="button" class="openProjectBtn">Open</button>
        <input class="renameProjectInput" type="text" value="${escapeHtml(project.name || project.id)}" />
        <button type="button" class="secondary renameProjectBtn">Rename</button>
        <button type="button" class="secondary deleteProjectBtn" ${state.projects.length <= 1 ? "disabled" : ""}>Delete</button>
      </div>
    `;
    card.querySelector(".openProjectBtn").onclick = () => openProject(project.id);
    card.querySelector(".renameProjectBtn").onclick = () => renameProject(project.id, card.querySelector(".renameProjectInput").value);
    card.querySelector(".deleteProjectBtn").onclick = () => deleteProject(project.id);
    root.appendChild(card);
  }
}

async function loadProjects() {
  const data = await api("/api/projects");
  state.projects = data.projects || [];
  state.activeProjectId = data.last_active_project_id || "";
  if (!state.projects.some((project) => project.id === state.activeProjectId)) state.activeProjectId = state.projects[0]?.id || "";
  renderProjectsList();
  renderCurrentProjectInfo();
  return data;
}

function resetTransientProjectUi() {
  stopSequence();
  state.selectedChunkId = "";
  state.selectedGroupId = "";
  state.sidePanelMode = "chunks";
  state.chunkNav = { activeId: "", signature: "" };
  state.musicClip = { selectedId: "", draggingId: "", selectedSourceId: "", selectedLaneId: "" };
  state.groupMedia = { selectedId: "", libraryTab: state.groupMedia.libraryTab || "image" };
  state.envelope.selectedIndex = -1;
  state.videoSpeed.selectedIndex = -1;
  state.timeline.cursorSec = 0;
}

async function openProject(projectId) {
  resetTransientProjectUi();
  state.project = await api(`/api/projects/${encodeURIComponent(projectId)}`);
  state.activeProjectId = state.project.id || projectId;
  await loadProjects().catch(() => {});
  patchProjectChunksFromProject(state.project);
  state.screenMode = "project";
  render();
  await refreshQueue().catch(() => {});
}

async function createProject() {
  const name = $("newProjectName")?.value?.trim() || "New project";
  const initial_text = $("newProjectText")?.value || "";
  const data = await api("/api/projects", { method: "POST", body: JSON.stringify({ name, initial_text }) });
  state.project = data.project;
  state.projects = data.projects || [];
  state.activeProjectId = data.last_active_project_id || state.project?.id || "";
  if ($("newProjectName")) $("newProjectName").value = "";
  if ($("newProjectText")) $("newProjectText").value = "";
  state.screenMode = "project";
  render();
}

async function renameProject(projectId, name) {
  const data = await api(`/api/projects/${encodeURIComponent(projectId)}`, { method: "PATCH", body: JSON.stringify({ name }) });
  state.projects = data.projects || state.projects;
  if (data.project && state.project?.id === projectId) state.project = data.project;
  render();
}

async function deleteProject(projectId) {
  if (!confirm(`Delete project ${projectId}? This removes its project directory and per-project outputs/uploads.`)) return;
  const data = await api(`/api/projects/${encodeURIComponent(projectId)}?confirm=${encodeURIComponent(projectId)}`, { method: "DELETE" });
  state.projects = data.projects || [];
  state.activeProjectId = data.last_active_project_id || "";
  if (state.project?.id === projectId) {
    state.project = null;
    if (state.activeProjectId) await openProject(state.activeProjectId);
    else setScreenMode("projects");
  } else {
    renderProjectsList();
  }
}

async function importTextToProject() {
  if (!state.project?.id) throw new Error("Open a project first");
  let text = $("importTextPaste")?.value || "";
  const file = $("importTextFile")?.files?.[0];
  if (file) text = await file.text();
  const mode = $("importTextMode")?.value || "replace";
  state.project = await api(`/api/projects/${encodeURIComponent(state.project.id)}/import-text`, { method: "POST", body: JSON.stringify({ text, mode }) });
  if ($("importTextFile")) $("importTextFile").value = "";
  render();
  setScreenMode("project");
}

function render() {
  if (!state.project) return;
  const status = state.project.status || {};
  state.queue = (state.project.queue && state.project.queue.length ? state.project.queue : state.queue) || [];
  state.progress = state.project.progress || state.progress;
  state.activeProjectId = state.project.id || state.activeProjectId;
  if (!state.sequence.active) setStatus(status.message || "Ready", status.busy);
  setSequenceStatus(state.sequence.status);
  const chunks = getChunks();
  if (state.selectedChunkId && !chunks.some((chunk) => chunk.id === state.selectedChunkId)) state.selectedChunkId = "";
  const groups = videoGroups();
  if (state.selectedGroupId && !groups.some((group) => group.id === state.selectedGroupId)) state.selectedGroupId = "";
  if (!state.selectedChunkId && chunks.length && state.screenMode === "chunk") state.selectedChunkId = chunks[0].id;
  state.chunkNav.activeId = state.selectedChunkId || state.chunkNav.activeId || chunks[0]?.id || "";
  safeRenderStep("chunk navigator", () => renderChunkNavigator(true));
  safeRenderStep("settings", renderSettings);
  safeRenderStep("health", renderHealth);
  safeRenderStep("timeline", renderTimeline);
  safeRenderStep("central screen", renderCentralScreen);
  safeRenderStep("chunk navigator refresh", () => renderChunkNavigator(true));
  safeRenderStep("group navigator", renderGroupNavigator);
  safeRenderStep("side panel mode", renderSidePanelMode);
  safeRenderStep("progress", renderProgress);
  safeRenderStep("queue", renderQueue);
  safeRenderStep("Grok AI task UI", syncGroupAiTaskUi);
  safeRenderStep("image task UI", syncImageTaskUi);
  safeRenderStep("music library", renderMusicLibraryPanel);
  safeRenderStep("media library", renderMediaLibraryPanel);
  safeRenderStep("export settings", syncExportSettingsUi);
  safeRenderStep("export", renderExport);
  safeRenderStep("current project", renderCurrentProjectInfo);
  safeRenderStep("projects list", renderProjectsList);
}

function isDomAudioPlaying() {
  return [...document.querySelectorAll("audio")].some((audio) => !audio.paused && !audio.ended);
}

function canFullRefreshProjectUi() {
  return !state.sequence.active && !state.sequence.audio && !isDomAudioPlaying();
}

function renderQueueOnly() {
  renderProgress();
  renderQueue();
  syncGroupAiTaskUi();
  syncImageTaskUi();
  renderHealth();
}

function patchProjectChunk(chunk) {
  if (!state.project) return;
  const chunks = getChunks();
  const idx = chunks.findIndex((item) => item.id === chunk.id);
  if (idx >= 0) {
    chunks[idx] = chunk;
  } else {
    chunks.push(chunk);
  }
  state.project.chunks = chunks.sort((a, b) => a.order - b.order);
}

function patchProjectChunksFromProject(project) {
  const chunks = getChunks(project);
  if (state.project && Array.isArray(chunks)) state.project.chunks = chunks;
  if (state.selectedChunkId && !chunks.some((chunk) => chunk.id === state.selectedChunkId)) state.selectedChunkId = chunks[0]?.id || "";
  state.chunkNav.activeId = state.selectedChunkId || state.chunkNav.activeId || chunks[0]?.id || "";
}

async function refreshChunkBlock(chunkId) {
  if (!chunkId || state.refreshingChunks.has(chunkId)) return;
  state.refreshingChunks.add(chunkId);
  try {
    const data = await api(`/api/chunks/${chunkId}${activeProjectQuery()}`);
    if (data.settings && state.project) state.project.settings = data.settings;
    if (data.timeline_duration_sec !== undefined && state.project) state.project.timeline_duration_sec = data.timeline_duration_sec;
    if (data.status && state.project) state.project.status = data.status;
    if (data.export !== undefined && state.project) state.project.export = data.export;
    patchProjectChunk(data.chunk);
    if (state.screenMode === "chunk" && state.selectedChunkId === data.chunk.id) replaceChunkCard(data.chunk);
    renderTimeline();
    renderCentralScreen();
    renderChunkNavigator();
    renderExport();
    if (!state.sequence.active) setStatus(data.status?.message || "Chunk updated", data.status?.busy);
  } finally {
    state.refreshingChunks.delete(chunkId);
  }
}

async function refreshExportOnly() {
  const project = await api(`/api/project${activeProjectQuery()}`);
  if (!state.project) {
    state.project = project;
    return;
  }
  state.project.export = project.export;
  state.project.status = project.status;
  state.project.timeline_duration_sec = project.timeline_duration_sec;
  renderExport();
  if (!state.sequence.active) setStatus(project.status?.message || "Export updated", project.status?.busy);
}

async function refreshVideoGroupsOnly() {
  const project = await api(`/api/project${activeProjectQuery()}`);
  if (!state.project) {
    state.project = project;
  } else {
    state.project.arrangement = project.arrangement;
    state.project.status = project.status;
    state.project.timeline_duration_sec = project.timeline_duration_sec;
    state.project.queue = project.queue || state.project.queue;
    state.project.progress = project.progress || state.project.progress;
  }
  patchProjectChunksFromProject(project);
  buildTimelineArrangement();
  const groups = videoGroups();
  state.selectedGroupId = groups[0]?.id || state.selectedGroupId || "";
  state.sidePanelMode = "groups";
  state.screenMode = "group";
  render();
  setGroupAiStatus("AI-группировка готова", "success");
  if (!state.sequence.active) setStatus("AI-группировка готова");
}

async function refreshProjectImagesOnly() {
  const project = await api(`/api/project${activeProjectQuery()}`);
  if (!state.project) {
    state.project = project;
  } else {
    state.project.arrangement = project.arrangement;
    state.project.status = project.status;
    state.project.timeline_duration_sec = project.timeline_duration_sec;
    state.project.queue = project.queue || state.project.queue;
    state.project.progress = project.progress || state.project.progress;
  }
  patchProjectChunksFromProject(project);
  buildTimelineArrangement();
  render();
  if (!state.sequence.active) setStatus("Group image updated");
}

function taskChunkId(task) {
  return task?.result_chunk_id || task?.chunk_id || null;
}

async function refreshCompletedTaskChunks(previousStatuses, tasks) {
  const chunkIds = new Set();
  let exportCompleted = false;
  let grokGroupsCompleted = false;
  let imageGroupCompleted = false;
  for (const task of tasks) {
    const previous = previousStatuses.get(task.id);
    if (previous && previous !== "done" && task.status === "done") {
      if (task.kind === "generate_chunk") {
        const chunkId = taskChunkId(task);
        if (chunkId) chunkIds.add(chunkId);
      } else if (task.kind === "export") {
        exportCompleted = true;
      } else if (task.kind === "grok_groups") {
        grokGroupsCompleted = true;
      } else if (task.kind === "image_group") {
        imageGroupCompleted = true;
      } else if (task.kind === "video_group") {
        imageGroupCompleted = true;
      }
    } else if (previous && previous !== "failed" && task.status === "failed" && task.kind === "grok_groups") {
      const message = task.message || "Grok AI grouping failed";
      setGroupAiStatus(`Ошибка AI-группировки: ${message}`, "error");
      setStatus(`AI grouping failed: ${message}`);
    }
  }
  for (const chunkId of chunkIds) {
    await refreshChunkBlock(chunkId).catch((err) => setStatus(`Chunk refresh failed: ${err.message}`));
  }
  if (exportCompleted) await refreshExportOnly().catch((err) => setStatus(`Export refresh failed: ${err.message}`));
  if (grokGroupsCompleted) await refreshVideoGroupsOnly().catch((err) => setStatus(`AI groups refresh failed: ${err.message}`));
  if (imageGroupCompleted) await refreshProjectImagesOnly().catch((err) => setStatus(`Image refresh failed: ${err.message}`));
}

function rememberTaskStatuses(tasks) {
  const next = new Map();
  for (const task of tasks) next.set(task.id, task.status);
  state.taskStatuses = next;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"]/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m]));
}

async function updateChunk(id, payload) {
  await saveSettings();
  state.project = await api(`/api/chunks/${id}${activeProjectQuery()}`, { method: "PATCH", body: JSON.stringify(payload) });
  render();
}

async function addChunkAfter(chunkId = "") {
  const text = prompt("Text for the new chunk:", "");
  if (text === null) return;
  try {
    state.project = await api(`/api/chunks${activeProjectQuery()}`, { method: "POST", body: JSON.stringify({ text, pause_after: 0.25, insert_after_chunk_id: chunkId }) });
    const chunks = getChunks();
    const inserted = chunks.find((chunk) => chunk.text === text) || chunks.at(-1);
    state.selectedChunkId = inserted?.id || state.selectedChunkId;
    state.screenMode = "chunk";
    render();
    setStatus("Chunk added");
  } catch (err) { setStatus(`Add chunk failed: ${err.message}`); }
}

async function deleteChunk(chunkId) {
  if (!confirm(`Delete chunk ${chunkNumber(chunkId)}? This also removes it from video groups.`)) return;
  try {
    state.project = await api(`/api/chunks/${encodeURIComponent(chunkId)}${activeProjectQuery()}`, { method: "DELETE" });
    state.selectedChunkId = getChunks()[0]?.id || "";
    render();
    setStatus("Chunk deleted");
  } catch (err) { setStatus(`Delete chunk failed: ${err.message}`); }
}

async function loadHealth() {
  state.health = await api("/api/health");
  renderHealth();
}

async function loadProject({ renderUi = true } = {}) {
  state.project = await api(`/api/project${activeProjectQuery()}`);
  state.activeProjectId = state.project.id || state.activeProjectId;
  patchProjectChunksFromProject(state.project);
  renderChunkNavigator(true);
  if (renderUi && !state.sequence.active) render();
  renderChunkNavigator(true);
}

async function generateChunk(id, card) {
  try {
    setStatus("Saving chunk and queueing generation…", true);
      const payload = {
        text: card.querySelector(".chunkText")?.value || card.querySelector(".chunkTtsText")?.value || "",
        tts_text: card.querySelector(".chunkTtsText")?.value || "",
        pause_after: clampPauseAfter(card.querySelector(".pauseAfter").value),
      };
    await updateChunk(id, payload);
    const data = await api(`/api/queue/generate${activeProjectQuery()}`, { method: "POST", body: JSON.stringify({ chunk_ids: [id] }) });
    if (data.project) state.project = data.project;
    state.queue = data.queue || state.queue;
    rememberTaskStatuses(state.queue);
    await refreshQueue();
    renderQueueOnly();
  } catch (err) { setStatus(`Error: ${err.message}`); }
}

async function selectVersion(chunkId, versionId) {
  state.project = await api(`/api/chunks/${chunkId}/select-version${activeProjectQuery()}`, { method: "POST", body: JSON.stringify({ version_id: versionId }) });
  render();
}

async function refreshQueue() {
  const data = await api(`/api/queue${activeProjectQuery()}`);
  const previousStatuses = new Map(state.taskStatuses);
  state.queue = data.queue || [];
  state.progress = data.progress || null;
  if (state.project) state.project.queue = state.queue;
  if (state.project) state.project.progress = state.progress;
  await refreshCompletedTaskChunks(previousStatuses, state.queue);
  rememberTaskStatuses(state.queue);
  if (!state.project) return;
  renderQueueOnly();
}

async function moveQueueTask(taskId, direction) {
  await api(`/api/queue/${taskId}/move/${direction}${activeProjectQuery()}`, { method: "POST", body: "{}" });
  await refreshQueue();
}

async function removeQueueTask(taskId) {
  await api(`/api/queue/${taskId}${activeProjectQuery()}`, { method: "DELETE" });
  await refreshQueue();
}

async function clearCompletedQueueTasks() {
  const data = await api(`/api/queue/clear-completed${activeProjectQuery()}`, { method: "POST", body: "{}" });
  state.queue = data.queue || [];
  state.progress = data.progress || state.progress;
  rememberTaskStatuses(state.queue);
  renderQueueOnly();
  setStatus(`Cleared ${data.removed || 0} completed task(s)`);
}

async function moveChunk(id, direction) {
  state.project = await api(`/api/chunks/${id}/move/${direction}${activeProjectQuery()}`, { method: "POST", body: "{}" });
  render();
}

$("splitBtn").onclick = async () => {
  try {
    const fullTextInput = $("fullText");
    const maxCharsInput = $("maxChars");
    const splitMinInput = $("splitPauseAfterMin");
    const splitMaxInput = $("splitPauseAfterMax");
    if (!fullTextInput || !maxCharsInput || !splitMinInput || !splitMaxInput) throw new Error("Split controls are missing from DOM");
    const text = fullTextInput.value;
    const maxChars = Number(maxCharsInput.value);
    const split_pause_after_min = Number.isFinite(Number(splitMinInput.value)) ? Number(splitMinInput.value) : SPLIT_SENTENCE_PAUSE_MIN_SEC;
    const split_pause_after_max = Number.isFinite(Number(splitMaxInput.value)) ? Number(splitMaxInput.value) : SPLIT_SENTENCE_PAUSE_MAX_SEC;
    await api(`/api/project/settings${activeProjectQuery()}`, { method: "POST", body: JSON.stringify(settingsPayload()) });
    setStatus("Splitting…", true);
    state.project = await api(`/api/chunks/split${activeProjectQuery()}`, {
      method: "POST",
      body: JSON.stringify({ text, max_chars: maxChars, split_pause_after_min, split_pause_after_max, generate_group_prompts: Boolean($("aiGenerateGroupPromptsOnSplit")?.checked ?? true) }),
    });
    const chunks = getChunks();
    state.selectedChunkId = chunks[0]?.id || "";
    state.chunkNav.activeId = state.selectedChunkId;
    state.screenMode = chunks.length ? "chunk" : "project";
    render();
    renderChunkNavigator(true);
  } catch (err) { setStatus(`Error: ${err.message}`); }
};

$("saveTextBtn").onclick = async () => {
  state.project = await api(`/api/project/text${activeProjectQuery()}`, { method: "POST", body: JSON.stringify({ text: $("fullText").value }) });
  render();
};

$("saveSettingsBtn").onclick = saveSettings;
$("voiceVolume").oninput = () => $("voiceVolumeValue").textContent = Number($("voiceVolume").value).toFixed(2);
$("musicVolume").oninput = () => {
  $("musicVolumeValue").textContent = Number($("musicVolume").value).toFixed(2);
  const transportMusic = $("transportMusicVolume");
  if (transportMusic) {
    transportMusic.value = $("musicVolume").value;
    $("transportMusicVolumeValue").textContent = Number(transportMusic.value).toFixed(2);
  }
};

$("transportMusicVolume").oninput = () => {
  $("transportMusicVolumeValue").textContent = Number($("transportMusicVolume").value).toFixed(2);
  $("musicVolume").value = $("transportMusicVolume").value;
  $("musicVolumeValue").textContent = Number($("musicVolume").value).toFixed(2);
};

$("transportMusicVolume").onchange = () => saveSettings().catch((err) => setStatus(`Music volume save failed: ${err.message}`));

const musicModeSelect = $("musicMode");
if (musicModeSelect) {
  musicModeSelect.onchange = () => {
    const mode = ["loop", "once", "chain_loop"].includes(musicModeSelect.value) ? musicModeSelect.value : "loop";
    ensureProjectArrangement().music.mode = mode;
    renderTransportLanes();
    saveMusicArrangement({ mode }).catch((err) => setStatus(`Music mode save failed: ${err.message}`));
  };
}

const imageAspectRatioSelect = $("imageAspectRatio");
if (imageAspectRatioSelect) {
  imageAspectRatioSelect.onchange = () => {
    updateResolvedImageSettingsHint();
  };
}

const imageQualitySlider = $("imageQualityPreset");
if (imageQualitySlider) {
  imageQualitySlider.oninput = () => setImageQualityPreset(IMAGE_QUALITY_ORDER[clamp(imageQualitySlider.value, 0, 2)] || "balanced");
}

const videoI2vQualitySlider = $("videoI2vQualityPreset");
if (videoI2vQualitySlider) {
  videoI2vQualitySlider.oninput = () => setVideoI2vQualityPreset(VIDEO_I2V_QUALITY_ORDER[clamp(videoI2vQualitySlider.value, 0, 2)] || "balanced");
}

document.querySelectorAll(".imageQualityButton").forEach((button) => {
  button.onclick = () => setImageQualityPreset(button.dataset.quality || "balanced");
});

document.querySelectorAll(".videoI2vQualityButton").forEach((button) => {
  button.onclick = () => setVideoI2vQualityPreset(button.dataset.quality || "balanced");
});
$("videoI2vMotionStyle")?.addEventListener("change", updateResolvedVideoI2vSettingsHint);
$("videoI2vWorkflowMode")?.addEventListener("change", updateResolvedVideoI2vSettingsHint);
$("videoI2vEnabled")?.addEventListener("change", () => {
  syncBulkVideoButtonLabel();
  syncImageTaskUi();
});
$("videoI2vTargetDurationSec")?.addEventListener("input", updateResolvedVideoI2vSettingsHint);
$("videoI2vPreviewPlaybackRate")?.addEventListener("input", updateResolvedVideoI2vSettingsHint);
$("videoI2vPingpong")?.addEventListener("change", updateResolvedVideoI2vSettingsHint);
for (const id of ["videoI2vGrokModel", "videoI2vGrokDurationSec", "videoI2vGrokResolution", "videoI2vGrokAspectRatioMode", "videoI2vGrokLoopPostprocess", "videoI2vGrokCrossfadeSec"]) {
  $(id)?.addEventListener("input", updateResolvedVideoI2vSettingsHint);
  $(id)?.addEventListener("change", updateResolvedVideoI2vSettingsHint);
}

const checkComfyuiBtn = $("checkComfyuiBtn");
if (checkComfyuiBtn) checkComfyuiBtn.onclick = checkComfyuiStatus;

for (const id of ["imageModel", "imageProvider", "imageWorkflowMode", "imageGrokModel"]) {
  const el = $(id);
  if (el) el.addEventListener("change", () => { renderFluxWorkflowNote(); syncGrokImageSettingsUi(); });
}

$("timelineScrubber").oninput = () => {
  state.timeline.userScrubbing = true;
  setTimelineCursor(Number($("timelineScrubber").value));
};

$("timelineScrubber").onchange = () => {
  state.timeline.userScrubbing = false;
  setTimelineCursor(Number($("timelineScrubber").value));
  if (state.sequence.active) playFromTimelineCursor(state.timeline.cursorSec).catch((err) => setStatus(`Seek failed: ${err.message}`));
};

function updatePlayheadPosition() {
  const wrap = $("timelineWorkspace");
  const playhead = $("transportPlayhead");
  const lane = $("voiceTimelineLane");
  if (!wrap || !playhead || !lane) return;
  const wrapRect = wrap.getBoundingClientRect();
  const laneRect = lane.getBoundingClientRect();
  playhead.style.left = `${(laneRect.left - wrapRect.left) + timelinePx(state.timeline.cursorSec)}px`;
}

function timeFromTimelineClientX(clientX) {
  const lane = $("voiceTimelineLane");
  return timeFromLaneClientX(clientX, lane);
}

function beginPlayheadDrag(event) {
  if (!state.timeline.durationSec) return;
  event.preventDefault();
  state.timeline.draggingPlayhead = true;
  const wasPlaying = state.sequence.active;
  setTimelineCursor(timeFromTimelineClientX(event.clientX));
  const onMove = (moveEvent) => setTimelineCursor(timeFromTimelineClientX(moveEvent.clientX));
  const onUp = () => {
    document.removeEventListener("pointermove", onMove);
    document.removeEventListener("pointerup", onUp);
    state.timeline.draggingPlayhead = false;
    setSequenceStatus(`Cursor ${formatTime(state.timeline.cursorSec)}${wasPlaying ? " · seeking…" : ""}`);
    if (wasPlaying) playFromTimelineCursor(state.timeline.cursorSec).catch((err) => setStatus(`Seek failed: ${err.message}`));
  };
  document.addEventListener("pointermove", onMove);
  document.addEventListener("pointerup", onUp, { once: true });
}

function shouldStartPlayheadDrag(event) {
  if (event.button !== 0) return false;
  if (event.target.closest?.("button,input,select,textarea,label,.musicLaneHead,#musicTimelineLane,#voiceAutomationLane,.musicEnvelope,.envelopePoint,.pauseRegion")) return false;
  return Boolean(event.target.closest?.("#voiceTimelineLane,.voiceLane,.laneBlock,.laneLabel"));
}

$("timelineLaneWrap").addEventListener("pointerdown", (event) => {
  if (!shouldStartPlayheadDrag(event)) return;
  beginPlayheadDrag(event);
});

$("musicTimelineLane").addEventListener("pointerdown", (event) => {
  if (event.target.closest?.(".envelopePoint,.musicClip")) return;
  event.stopPropagation();
});

$("musicTimelineLane").addEventListener("click", (event) => {
  if (event.target.closest?.(".envelopePoint,.musicClip")) return;
  event.preventDefault();
  event.stopPropagation();
  addEnvelopePoint(event, "music");
});

$("musicTimelineLane").addEventListener("dragover", (event) => {
  if (!event.dataTransfer.types.includes("application/x-xtts-music-source") && !event.dataTransfer.types.includes("text/plain")) return;
  event.preventDefault();
  event.dataTransfer.dropEffect = "copy";
});

$("musicTimelineLane").addEventListener("drop", (event) => {
  event.preventDefault();
  event.stopPropagation();
  const sourceId = event.dataTransfer.getData("application/x-xtts-music-source") || event.dataTransfer.getData("text/plain");
  addMusicSourceToTimeline(sourceId, timeFromLaneClientX(event.clientX, $("musicTimelineLane")));
});

$("musicTimelineLane").addEventListener("dblclick", (event) => {
  event.preventDefault();
  event.stopPropagation();
});

$("musicTimelineLane").addEventListener("contextmenu", (event) => {
  event.preventDefault();
  event.stopPropagation();
  if (state.envelope.selectedIndex >= 0) deleteEnvelopePoint("music");
});

$("voiceAutomationLane").addEventListener("click", (event) => {
  if (event.target.closest?.(".envelopePoint")) return;
  event.preventDefault();
  event.stopPropagation();
  addEnvelopePoint(event, "voice");
});

$("voiceAutomationLane").addEventListener("contextmenu", (event) => {
  event.preventDefault();
  event.stopPropagation();
  if (state.envelope.selectedIndex >= 0) deleteEnvelopePoint("voice");
});

const videoSpeedAutomationLane = $("videoSpeedAutomationLane");
if (videoSpeedAutomationLane) {
  videoSpeedAutomationLane.addEventListener("click", (event) => {
    if (event.target.closest?.(".envelopePoint")) return;
    event.preventDefault();
    event.stopPropagation();
    addVideoSpeedPoint(event);
  });
  videoSpeedAutomationLane.addEventListener("contextmenu", (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (state.videoSpeed.selectedIndex >= 0) deleteVideoSpeedPoint();
  });
}

function clampTimelineZoom(value) {
  return clamp(value, TIMELINE_ZOOM_MIN, TIMELINE_ZOOM_MAX);
}

function laneViewportAnchorPx(scroller, anchorTime) {
  const lane = $("voiceTimelineLane");
  const scrollerRect = scroller?.getBoundingClientRect?.();
  const laneRect = lane?.getBoundingClientRect?.();
  if (!scrollerRect || !laneRect) return 195 + timelinePx(anchorTime);
  return (laneRect.left - scrollerRect.left) + timelinePx(anchorTime);
}

function setZoom(nextPps, { anchorTime = state.timeline.cursorSec } = {}) {
  const scroller = $("timelineScroller");
  const safeAnchorTime = clamp(anchorTime, 0, state.timeline.durationSec || TIMELINE_DEFAULT_VISIBLE_SECONDS);
  const beforeAnchorPx = scroller ? laneViewportAnchorPx(scroller, safeAnchorTime) : null;
  const beforeScrollLeft = scroller?.scrollLeft || 0;
  state.timeline.pixelsPerSecond = clampTimelineZoom(nextPps);
  localStorage.setItem("xttsStudioPixelsPerSecond", String(state.timeline.pixelsPerSecond));
  renderTimeline();
  if (scroller && beforeAnchorPx !== null) {
    const afterAnchorPx = laneViewportAnchorPx(scroller, safeAnchorTime);
    scroller.scrollLeft = Math.max(0, beforeScrollLeft + afterAnchorPx - beforeAnchorPx);
  }
  updatePlayheadPosition();
}

$("zoomOutBtn").onclick = () => setZoom(state.timeline.pixelsPerSecond / 1.25, { anchorTime: state.timeline.cursorSec });
$("zoomInBtn").onclick = () => setZoom(state.timeline.pixelsPerSecond * 1.25, { anchorTime: state.timeline.cursorSec });
$("zoomFitBtn").onclick = () => {
  const scroller = $("timelineScroller");
  const available = Math.max(320, (scroller?.clientWidth || 1200) - 195);
  const visibleDuration = Math.max(state.timeline.durationSec || 1, TIMELINE_DEFAULT_VISIBLE_SECONDS);
  setZoom(available / visibleDuration, { anchorTime: state.timeline.cursorSec });
};

window.addEventListener("resize", () => {
  const currentHeight = $("timelineTransport")?.getBoundingClientRect?.().height || Number(localStorage.getItem(TIMELINE_PANEL_HEIGHT_KEY)) || 660;
  setTimelinePanelHeight(currentHeight, { persist: true });
  updatePlayheadPosition();
});

window.addEventListener("scroll", () => {
  if (state.screenMode !== "chunk") return;
  const cards = [...document.querySelectorAll(".chunk")];
  if (!cards.length) return;
  const mid = window.innerHeight * 0.45;
  let best = cards[0];
  let bestDistance = Infinity;
  for (const card of cards) {
    const rect = card.getBoundingClientRect();
    const distance = Math.abs((rect.top + rect.bottom) / 2 - mid);
    if (distance < bestDistance) {
      best = card;
      bestDistance = distance;
    }
  }
  if (best?.dataset.chunkId && best.dataset.chunkId !== state.chunkNav.activeId) setActiveChunkNav(best.dataset.chunkId);
}, { passive: true });

document.addEventListener("keydown", (event) => {
  const target = event.target;
  const editingText = target?.closest?.("input,textarea,select,[contenteditable='true']");
  if (editingText) return;
  if ((event.key === "Delete" || event.key === "Backspace") && state.musicClip.selectedId) {
    event.preventDefault();
    deleteSelectedMusicClip();
    return;
  }
  if ((event.key === "Delete" || event.key === "Backspace") && state.musicClip.selectedLaneId) {
    event.preventDefault();
    deleteSelectedMusicLane();
    return;
  }
  if ((event.key === "Delete" || event.key === "Backspace") && state.envelope.selectedIndex >= 0) {
    event.preventDefault();
    deleteEnvelopePoint();
    return;
  }
  if ((event.key === "Delete" || event.key === "Backspace") && state.videoSpeed.selectedIndex >= 0) {
    event.preventDefault();
    deleteVideoSpeedPoint();
  }
});

$("musicUpload").onchange = async () => {
  const files = [...($("musicUpload").files || [])];
  if (!files.length) return;
  try {
    setStatus(`Uploading ${files.length} audio source(s)…`, true);
    for (const file of files) {
      const form = new FormData();
      form.append("file", file);
      const data = await api(`/api/upload/music${activeProjectQuery()}`, { method: "POST", body: form });
      state.project = data.project;
    }
    state.musicClip.selectedId = musicArrangement().tracks.at(-1)?.id || state.musicClip.selectedId;
    render();
    setStatus(`Uploaded ${files.length} audio source(s)`);
  } catch (err) {
    setStatus(`Music upload failed: ${err.message}`);
  } finally {
    $("musicUpload").value = "";
  }
};

async function uploadMusicFiles(files, uploadInput = null) {
  const items = [...(files || [])];
  if (!items.length) return;
  try {
    setStatus(`Uploading ${items.length} audio source(s)…`, true);
    for (const file of items) {
      const form = new FormData();
      form.append("file", file);
      const data = await api(`/api/upload/music${activeProjectQuery()}`, { method: "POST", body: form });
      state.project = data.project;
    }
    const music = musicArrangement();
    state.musicClip.selectedId = music.tracks.at(-1)?.id || state.musicClip.selectedId;
    state.musicClip.selectedSourceId = music.sources.at(-1)?.id || state.musicClip.selectedSourceId;
    render();
    setStatus(`Uploaded ${items.length} audio source(s)`);
  } catch (err) {
    setStatus(`Music upload failed: ${err.message}`);
  } finally {
    if (uploadInput) uploadInput.value = "";
  }
}

const musicLibraryUpload = $("musicLibraryUpload");
if (musicLibraryUpload) musicLibraryUpload.onchange = () => uploadMusicFiles(musicLibraryUpload.files, musicLibraryUpload);

function addMusicPathSource() {
  const input = $("musicPath");
  addMusicPathSourceFromValue(input?.value || "", { addClip: true });
}

const addMusicSourceBtn = $("addMusicSourceBtn");
if (addMusicSourceBtn) addMusicSourceBtn.onclick = addMusicPathSource;
const musicLibraryAddPathBtn = $("musicLibraryAddPathBtn");
if (musicLibraryAddPathBtn) musicLibraryAddPathBtn.onclick = () => {
  addMusicPathSourceFromValue($("musicLibraryPath")?.value || "", { addClip: false });
  if ($("musicLibraryPath")) $("musicLibraryPath").value = "";
};
const musicLibraryAddAtCursorBtn = $("musicLibraryAddAtCursorBtn");
if (musicLibraryAddAtCursorBtn) musicLibraryAddAtCursorBtn.onclick = addSelectedMusicSourceAtCursor;
const musicLibraryAppendBtn = $("musicLibraryAppendBtn");
if (musicLibraryAppendBtn) musicLibraryAppendBtn.onclick = appendSelectedMusicSource;
const musicLoopChainBtn = $("musicLoopChainBtn");
if (musicLoopChainBtn) musicLoopChainBtn.onclick = () => {
  const mode = musicArrangement().mode === "chain_loop" ? "once" : "chain_loop";
  if ($("musicMode")) $("musicMode").value = mode;
  ensureProjectArrangement().music.mode = mode;
  renderTransportLanes();
  saveMusicArrangement({ mode }).catch((err) => setStatus(`Music loop-chain save failed: ${err.message}`));
};

function allProjectMediaItems(type = state.groupMedia.libraryTab || "image") {
  return groupTimelineSpans().flatMap((group) => normalizeGroupMediaItems(group).filter((item) => item.type === type).map((item) => ({ ...item, group_id: group.id, group_title: group.title })));
}

function renderMediaLibraryPanel() {
  const root = $("mediaLibraryList");
  if (!root || !state.project) return;
  document.querySelectorAll(".mediaLibraryTab").forEach((button) => {
    button.classList.toggle("active", button.dataset.type === state.groupMedia.libraryTab);
    button.classList.toggle("secondary", button.dataset.type !== state.groupMedia.libraryTab);
  });
  const items = allProjectMediaItems(state.groupMedia.libraryTab);
  if (!items.length) {
    root.innerHTML = `<div class="chunkNavEmpty"><strong>No ${escapeHtml(state.groupMedia.libraryTab)} media yet</strong><small>Generated group media appears here and can be dragged into another group.</small></div>`;
    return;
  }
  root.innerHTML = "";
  for (const item of items) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "mediaLibraryItem";
    button.draggable = true;
    const url = groupMediaUrl(item);
    button.innerHTML = `${item.type === "video" ? `<video src="${escapeHtml(url)}" muted loop playsinline></video>` : `<img src="${escapeHtml(url)}" alt="" />`}<strong>${escapeHtml(item.label || shortPath(item.path || item.url))}</strong><small>${escapeHtml(item.group_title || item.group_id || "group")}</small>`;
    button.ondragstart = (event) => {
      event.dataTransfer.effectAllowed = "copy";
      event.dataTransfer.setData("application/x-xtts-group-media", JSON.stringify({ ...item, id: `media_${Date.now()}_${Math.random().toString(16).slice(2)}` }));
    };
    root.appendChild(button);
  }
}

document.querySelectorAll(".mediaLibraryTab").forEach((button) => {
  button.onclick = () => { state.groupMedia.libraryTab = button.dataset.type || "image"; renderMediaLibraryPanel(); };
});

const resetMusicAutomationBtn = $("resetMusicAutomationBtn");
if (resetMusicAutomationBtn) resetMusicAutomationBtn.onclick = resetMusicEnvelope;
const resetVoiceAutomationBtn = $("resetVoiceAutomationBtn");
if (resetVoiceAutomationBtn) resetVoiceAutomationBtn.onclick = resetVoiceEnvelope;

$("generateAllBtn").onclick = async () => {
  try {
    await saveSettings();
    setStatus("Queueing missing chunks…", true);
    const chunk_ids = getChunks()
      .filter((chunk) => !chunk.audio_path && (chunk.text || "").trim())
      .sort((a, b) => a.order - b.order)
      .map((chunk) => chunk.id);
    const data = await api(`/api/queue/generate${activeProjectQuery()}`, { method: "POST", body: JSON.stringify({ chunk_ids }) });
    if (data.project) state.project = data.project;
    state.queue = data.queue || state.queue;
    rememberTaskStatuses(state.queue);
    await refreshQueue();
    renderQueueOnly();
  } catch (err) { setStatus(`Error: ${err.message}`); }
};

$("exportBtn").onclick = async () => {
  try {
    await saveSettings();
    const payload = exportPayloadFromUi();
    setStatus(`Queueing ${payload.export_type === "video" ? "video" : payload.audio_format.toUpperCase()} export…`, true);
    const data = await api(`/api/queue/export${activeProjectQuery()}`, { method: "POST", body: JSON.stringify(payload) });
    state.project = data.project;
    state.queue = data.queue || state.queue;
    rememberTaskStatuses(state.queue);
    await refreshQueue();
    renderQueueOnly();
  } catch (err) { setStatus(`Error: ${err.message}`); }
};

for (const id of ["exportType", "exportAudioFormat", "exportAudioBitrate", "exportSampleRate", "exportChannels", "exportVideoFormat", "exportOrientation", "exportResolution", "exportFps", "exportVideoFit", "exportVideoQuality"]) {
  $(id)?.addEventListener("change", syncExportSettingsUi);
  $(id)?.addEventListener("input", syncExportSettingsUi);
}

$("projectModeTab").onclick = () => setScreenMode("project");
$("projectsModeTab").onclick = () => { loadProjects().catch((err) => setStatus(`Projects load failed: ${err.message}`)); setScreenMode("projects"); };
$("chunkModeTab").onclick = () => setScreenMode("chunk");
$("previewModeTab").onclick = () => setScreenMode("preview");
$("backToProjectBtn").onclick = () => setScreenMode("project");
$("backToProjectFromGroupBtn").onclick = () => setScreenMode("project");
const generateAiGroupsBtn = $("generateAiGroupsBtn");
if (generateAiGroupsBtn) generateAiGroupsBtn.onclick = () => generateAiGroups();
const addManualGroupBtn = $("addManualGroupBtn");
if (addManualGroupBtn) addManualGroupBtn.onclick = addManualGroup;
const queueAllImagesBtn = $("queueAllImagesBtn");
if (queueAllImagesBtn) queueAllImagesBtn.onclick = () => enqueueAllGroupImages();
const queueAllVideosBtn = $("queueAllVideosBtn");
if (queueAllVideosBtn) queueAllVideosBtn.onclick = () => enqueueAllGroupVideos();
$("chunksSideTab").onclick = () => setSidePanelMode("chunks");
$("groupsSideTab").onclick = () => setSidePanelMode("groups");
$("refreshQueueBtn").onclick = refreshQueue;
const clearCompletedQueueBtn = $("clearCompletedQueueBtn");
if (clearCompletedQueueBtn) clearCompletedQueueBtn.onclick = () => clearCompletedQueueTasks().catch((err) => setStatus(`Clear completed failed: ${err.message}`));
$("manualReloadBtn").onclick = () => {
  const url = new URL(window.location.href);
  url.searchParams.set("studioReload", `${FRONTEND_BUILD}-${Date.now()}`);
  window.location.replace(url.toString());
};
$("createProjectBtn").onclick = () => createProject().catch((err) => setStatus(`Create project failed: ${err.message}`));
$("importTextBtn").onclick = () => importTextToProject().catch((err) => setStatus(`Import text failed: ${err.message}`));

document.addEventListener("submit", (event) => {
  event.preventDefault();
});

function stopSequence() {
  stopTimelinePreview(false);
  const previousAudio = state.sequence.audio;
  const stopAudio = state.sequence.stopAudio;
  state.sequence.active = false;
  state.sequence.runId += 1;
  if (state.sequence.timer) clearTimeout(state.sequence.timer);
  state.sequence.timer = null;
  state.sequence.stopAudio = null;
  if (stopAudio) stopAudio();
  if (previousAudio) {
    previousAudio.onended = null;
    previousAudio.onerror = null;
    previousAudio.onpause = null;
    previousAudio.pause();
    previousAudio.removeAttribute("src");
    previousAudio.load();
  }
  state.sequence.audio = null;
  if (state.sequence.status !== "Stopped") {
    setSequenceStatus("Stopped");
    setStatus("Sequence stopped");
  }
}

function stopTimelinePreview(updateStatus = true) {
  state.preview.runId += 1;
  if (state.preview.raf) cancelAnimationFrame(state.preview.raf);
  state.preview.raf = null;
  for (const source of state.preview.sources) {
    try { source.stop(); } catch (_) {}
    source.onended = null;
  }
  state.preview.sources = [];
  state.preview.gains = [];
  state.sequence.active = false;
  state.sequence.audio = null;
  state.sequence.stopAudio = null;
  if (updateStatus) {
    setSequenceStatus("Stopped");
    setStatus("Timeline preview stopped");
  }
}

async function getAudioContext() {
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) throw new Error("Web Audio is not supported by this browser");
  if (!state.preview.ctx) state.preview.ctx = new AudioContextClass();
  if (state.preview.ctx.state === "suspended") await state.preview.ctx.resume();
  return state.preview.ctx;
}

function audioUrlForPath(path) {
  const value = String(path || "").trim();
  if (/^https?:\/\//i.test(value)) return value;
  return value ? `/api/audio?path=${encodeURIComponent(value)}` : "";
}

async function decodeAudioUrl(ctx, url) {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`Audio fetch failed (${res.status})`);
  const data = await res.arrayBuffer();
  return ctx.decodeAudioData(data);
}

async function cachedDecodeAudioUrl(ctx, url, cacheKey = url) {
  if (!ctx) throw new Error("Audio context is not ready");
  if (!url) throw new Error("Audio URL is empty");
  const key = String(cacheKey || url);
  if (!state.audioDecodeCache.has(key)) {
    state.audioDecodeCache.set(key, decodeAudioUrl(ctx, url).catch((err) => {
      state.audioDecodeCache.delete(key);
      throw err;
    }));
  }
  return state.audioDecodeCache.get(key);
}

window.XTTSStudio = window.XTTSStudio || {};
window.XTTSStudio.FRONTEND_BUILD = FRONTEND_BUILD;
window.XTTSStudio.cachedDecodeAudioUrl = cachedDecodeAudioUrl;
window.cachedDecodeAudioUrl = cachedDecodeAudioUrl;

async function bufferForTrack(ctx, track, bufferCache) {
  if (!track.path) return null;
  const url = audioUrlForPath(track.path);
  const buffer = bufferCache.get(track.path) || await decodeAudioUrl(ctx, url);
  bufferCache.set(track.path, buffer);
  const music = state.project.arrangement?.music;
  const source = music?.sources?.find?.((item) => item.id === track.source_id || item.path === track.path);
  if (source && !source.duration) source.duration = buffer.duration;
  return buffer;
}

function musicAudioUrl() {
  const path = musicArrangement().tracks[0]?.path || state.project?.settings?.music_path || "";
  return audioUrlForPath(path);
}

function startSource(ctx, buffer, when, offset, gainValue, { loop = false, automation = null, automationStartTime = state.timeline.cursorSec } = {}) {
  const source = ctx.createBufferSource();
  const gain = ctx.createGain();
  gain.gain.value = Math.max(0, Number(gainValue) || 0);
  if (automation && automation.length) {
    const startAt = Math.max(ctx.currentTime, when);
    gain.gain.cancelScheduledValues(startAt);
    gain.gain.setValueAtTime(Math.max(0, Number(gainValue) || 0), startAt);
    for (const point of automation) {
      const value = clamp((point.volumeMultiplier ?? 1) * point.volume, 0, 4);
      gain.gain.linearRampToValueAtTime(value, startAt + Math.max(0, point.time - automationStartTime));
    }
  }
  source.buffer = buffer;
  source.loop = loop;
  source.connect(gain).connect(ctx.destination);
  source.start(Math.max(ctx.currentTime, when), Math.max(0, offset || 0));
  state.preview.sources.push(source);
  state.preview.gains.push(gain);
  return source;
}

function sourceStartWithDuration(ctx, buffer, when, offset, gainValue, duration, opts = {}) {
  const source = startSource(ctx, buffer, when, offset, gainValue, opts);
  if (duration !== undefined && duration !== null && duration > 0 && !opts.loop) {
    try { source.stop(Math.max(ctx.currentTime, when) + duration); } catch (_) {}
  }
  return source;
}

function startPreviewClock(runId) {
  if (state.preview.raf) cancelAnimationFrame(state.preview.raf);
  const tick = () => {
    if (!state.sequence.active || state.preview.runId !== runId || !state.preview.ctx) return;
    const elapsed = state.preview.ctx.currentTime - state.preview.startedAtContextTime;
    const next = Math.min(state.timeline.durationSec, state.preview.startedAtTimelineTime + Math.max(0, elapsed));
    setTimelineCursor(next, { fromPlayback: true });
    setSequenceStatus(`Playing from cursor · ${formatTime(next)} / ${formatTime(state.timeline.durationSec)}`);
    if (next >= state.timeline.durationSec - 0.01) {
      setTimelineCursor(state.timeline.durationSec, { fromPlayback: true });
      stopTimelinePreview(false);
      setSequenceStatus("Complete");
      setStatus("Timeline preview complete");
      return;
    }
    state.preview.raf = requestAnimationFrame(tick);
  };
  state.preview.raf = requestAnimationFrame(tick);
}

async function playFromTimelineCursor(cursorSec = state.timeline.cursorSec) {
  stopSequence();
  buildTimelineArrangement();
  setTimelineCursor(cursorSec);
  const arrangement = state.timeline.arrangement.filter((part) => part.audioUrl && part.end > state.timeline.cursorSec);
  if (!arrangement.length && !musicAudioUrl()) {
    setSequenceStatus("Stopped · no selected audio after cursor");
    setStatus("No selected chunk audio after the cursor");
    return;
  }
  const ctx = await getAudioContext();
  stopTimelinePreview(false);
  state.sequence.active = true;
  state.preview.runId += 1;
  const runId = state.preview.runId;
  const baseTime = ctx.currentTime + 0.08;
  state.preview.startedAtContextTime = baseTime;
  state.preview.startedAtTimelineTime = state.timeline.cursorSec;
  startPreviewClock(runId);
  const firstPart = arrangement[0];
  const startsInGap = firstPart && state.timeline.cursorSec < firstPart.start;
  if (startsInGap) {
    setStatus(`Cursor is in a pause gap; next chunk starts in ${(firstPart.start - state.timeline.cursorSec).toFixed(2)}s…`, true);
    setSequenceStatus(`Gap before chunk ${firstPart.chunk.order + 1} · waiting ${(firstPart.start - state.timeline.cursorSec).toFixed(2)}s`);
  } else {
    setStatus(`Playing timeline preview from ${formatTime(state.timeline.cursorSec)}…`, true);
    setSequenceStatus(firstPart ? `Starting at chunk ${firstPart.chunk.order + 1}` : "Starting music-only preview");
  }

  const voiceVolume = Number(state.project?.settings?.voice_volume ?? $("voiceVolume").value ?? 1);
  const playbackTimeNow = () => state.preview.startedAtTimelineTime + Math.max(0, ctx.currentTime - state.preview.startedAtContextTime);
  const scheduleVoice = async () => {
    for (const part of arrangement) {
      if (!state.sequence.active || state.preview.runId !== runId) return;
      try {
        console.debug("[XTTS Studio] voice chunk decode queued", { chunk: part.chunk.order + 1, start: part.start, cursor: state.preview.startedAtTimelineTime });
        const decodeFn = window.XTTSStudio?.cachedDecodeAudioUrl || window.cachedDecodeAudioUrl;
        if (typeof decodeFn !== "function") throw new Error(`decode cache unavailable in build ${FRONTEND_BUILD}`);
        const buffer = await decodeFn(ctx, part.audioUrl, `voice:${part.audioUrl}`);
        if (!state.sequence.active || state.preview.runId !== runId) return;
        const nowTimeline = Math.max(state.timeline.cursorSec, playbackTimeNow());
        if (part.end <= nowTimeline) continue;
        const offset = Math.max(0, nowTimeline - part.start);
        const startTimeForVol = Math.max(nowTimeline, part.start);
        const when = Math.max(ctx.currentTime, baseTime + Math.max(0, part.start - state.preview.startedAtTimelineTime));
        const automation = effectiveEnvelope("voice")
          .filter((point) => point.time >= startTimeForVol && point.time <= part.end)
          .map((point) => ({ ...point, volume: voiceVolume * point.volume }));
        console.debug("[XTTS Studio] voice chunk scheduled", { chunk: part.chunk.order + 1, start: part.start, offset, when });
        sourceStartWithDuration(ctx, buffer, when, offset, voiceVolume * voiceAutomationAt(startTimeForVol), Math.max(0, part.duration - offset), { automation, automationStartTime: startTimeForVol });
      } catch (err) {
        setStatus(`Skipping chunk ${part.chunk.order + 1}: ${err.message}`);
      }
    }
  };

  const envelopeHasAudibleMusic = effectiveMusicEnvelope().some((point) => Number(point.volume || 0) > 0);
  const music = musicArrangement();
  const scheduleMusic = async () => {
    if (!(music.lanes.some((lane) => lane.enabled && lane.clips.length) && envelopeHasAudibleMusic)) return;
    try {
      const bufferCache = new Map();
      for (const lane of music.lanes) await bufferForTrack(ctx, lane, bufferCache);
      if (bufferCache.size) renderTransportLanes();
      for (const lane of music.lanes.filter((item) => item.enabled && item.clips.length)) {
        const musicBuffer = await bufferForTrack(ctx, lane, bufferCache);
        if (!musicBuffer) continue;
        if (!state.sequence.active || state.preview.runId !== runId || musicBuffer.duration <= 0) return;
        state.preview.musicBufferDuration = Math.max(state.preview.musicBufferDuration, musicBuffer.duration);
        renderTransportLanes();
        for (const item of renderLaneClipInstances(lane)) {
          const clip = item.clip;
          const clipStart = Number(item.start_time || 0);
          const clipDuration = Math.min(clipDurationForClip(lane, clip) || musicBuffer.duration, Math.max(0, musicBuffer.duration - Number(clip.offset_sec || 0)));
          const clipEnd = clipStart + clipDuration;
          const nowTimeline = Math.max(state.timeline.cursorSec, playbackTimeNow());
          if (clipEnd <= nowTimeline || clipStart >= state.timeline.durationSec) continue;
          const offset = Math.max(0, Number(clip.offset_sec || 0) + nowTimeline - clipStart);
          if (offset >= musicBuffer.duration) continue;
          const when = Math.max(ctx.currentTime, baseTime + Math.max(0, clipStart - state.preview.startedAtTimelineTime));
          const clipVol = Number(clip.volume ?? 1);
          const startTimeForVol = Math.max(nowTimeline, clipStart);
          const duration = Math.min(clipDuration, musicBuffer.duration - offset, state.timeline.durationSec - startTimeForVol);
          const clipEndForAutomation = startTimeForVol + duration;
          const breakpoints = envelopeBreakpointsInSpan(startTimeForVol, clipEndForAutomation, effectiveMusicEnvelope(), effectiveEnvelope(laneTarget(lane.id)));
          const laneBaseVol = Number(lane.volume ?? 1);
          const combinedVolAt = (time) => musicVolumeAt(time) * laneEnvelopeValueAt(lane, time) * laneBaseVol * clipVol;
          const startVol = combinedVolAt(startTimeForVol);
          const automation = breakpoints.map((time) => ({ time, volume: combinedVolAt(time) }));
          sourceStartWithDuration(ctx, musicBuffer, when, offset, startVol, duration, { automation, automationStartTime: startTimeForVol });
        }
      }
    } catch (err) {
      setStatus(`Timeline preview continuing without music: ${err.message}`, true);
    }
  };
  scheduleVoice();
  scheduleMusic();
}

function wait(ms, runId) {
  return new Promise((resolve) => {
    state.sequence.timer = setTimeout(() => {
      if (state.sequence.runId === runId) state.sequence.timer = null;
      resolve(state.sequence.active && state.sequence.runId === runId);
    }, ms);
  });
}

function playChunkAudio(chunk, index, total, runId) {
  return new Promise((resolve) => {
    const audioUrl = selectedAudioUrlForChunk(chunk);
    if (!audioUrl || !state.sequence.active || state.sequence.runId !== runId) {
      resolve(false);
      return;
    }
    const audio = new Audio();
    audio.preload = "auto";
    let settled = false;
    const cleanup = () => {
      audio.onended = null;
      audio.onerror = null;
      audio.onabort = null;
      if (state.sequence.audio === audio) state.sequence.audio = null;
      if (state.sequence.stopAudio === stopAudio) state.sequence.stopAudio = null;
    };
    const finish = (played) => {
      if (settled) return;
      settled = true;
      cleanup();
      resolve(played && state.sequence.active && state.sequence.runId === runId);
    };
    const stopAudio = () => finish(false);
    state.sequence.audio = audio;
    state.sequence.stopAudio = stopAudio;
    setStatus(`Playing chunk ${index + 1}/${total} (chunk ${chunk.order + 1})…`, true);
    setSequenceStatus(`Playing chunk ${index + 1}/${total} · chunk ${chunk.order + 1}`);
    audio.onended = () => finish(true);
    audio.onabort = () => finish(false);
    audio.onerror = () => {
      if (state.sequence.runId !== runId) return;
      setStatus(`Skipping chunk ${chunk.order + 1}: could not play selected audio`);
      setSequenceStatus(`Skipped chunk ${chunk.order + 1}: audio error`);
      finish(true);
    };
    audio.src = audioUrl;
    audio.load();
    audio.play().catch(() => {
      if (state.sequence.runId !== runId) return;
      setStatus(`Skipping chunk ${chunk.order + 1}: browser refused playback`);
      setSequenceStatus(`Skipped chunk ${chunk.order + 1}: playback refused`);
      finish(true);
    });
  });
}

async function playGeneratedSequence() {
  return playFromTimelineCursor(0);
}

$("playSequenceBtn").onclick = () => playGeneratedSequence().catch((err) => setStatus(`Error: ${err.message}`));
$("stopSequenceBtn").onclick = stopSequence;
$("playFromCursorBtn").onclick = () => playFromTimelineCursor().catch((err) => setStatus(`Error: ${err.message}`));
$("stopPreviewBtn").onclick = stopSequence;

function startPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = setInterval(() => {
    refreshQueue().catch(() => {});
    loadHealth().catch(() => {});
  }, 1500);
}

async function initStudio() {
  console.info("[XTTS Studio] startup", {
    frontendBuild: FRONTEND_BUILD,
    decodeCacheLoaded: typeof window.XTTSStudio?.cachedDecodeAudioUrl === "function",
  });
  initTimelinePanelResize();
  await loadHealth().catch(() => {});
  const projects = await loadProjects();
  if (projects.last_active_project_id) {
    await loadProject({ renderUi: false });
    state.screenMode = "projects";
    render();
  } else {
    setScreenMode("projects");
  }
  await refreshQueue().catch(() => {});
  startPolling();
}

initStudio().catch((err) => setStatus(`Error: ${err.message}`));


