const FRONTEND_BUILD = "2026-05-08-cachedecode-scope-header-fix-v1";
const TIMELINE_ZOOM_MIN = 0.2;
const TIMELINE_ZOOM_MAX = 640;
const TIMELINE_PAUSE_PRECISION_SEC = 0.01;
const TIMELINE_PAUSE_MIN_SEC = 0;
const TIMELINE_PAUSE_MAX_SEC = 10;
const TIMELINE_DEFAULT_VISIBLE_SECONDS = 3600;
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
  preview: { ctx: null, sources: [], gains: [], raf: null, runId: 0, startedAtContextTime: 0, startedAtTimelineTime: 0, musicBufferDuration: 0 },
  envelope: { selectedIndex: -1, draggingIndex: -1, target: "music" },
  musicClip: { selectedId: "", draggingId: "", selectedSourceId: "", selectedLaneId: "" },
  chunkNav: { activeId: "", signature: "" },
  screenMode: "projects",
  selectedChunkId: "",
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
  const runningLabel = activeTask ? `${activeTask.kind}${activeTask.chunk_id ? ` · chunk ${chunkNumber(activeTask.chunk_id)}` : ""}` : "";
  $("progressText").textContent = p.active || activeTask
    ? `${p.message || "Working…"}${runningLabel ? ` (${runningLabel})` : ""}${queuedCount ? ` · ${queuedCount} queued` : ""}`
    : (p.message || "Idle");
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
      ? "Frontend/backend build mismatch detected. Queue polling continues without automatic page reload; use the manual reload button when playback is stopped."
      : "";
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
    const label = chunk ? `Chunk ${chunk.order + 1}` : "project";
    const taskPercent = task.progress_percent ?? (task.status === "done" ? 100 : task.status === "running" ? (state.progress?.percent || 15) : 0);
    const item = document.createElement("div");
    item.className = "queueItem";
    item.innerHTML = `
      <span class="statusTag status-${task.status}">${task.status}</span>
      <div>
        <strong>${task.kind}</strong>
        <small>${label} · ${task.message || ""}</small>
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

function settingsPayload() {
  return {
    reference_path: $("referencePath").value.trim(),
    music_path: $("musicPath").value.trim(),
    voice_volume: Number($("voiceVolume").value),
    music_volume: Number($("musicVolume").value),
  };
}

function activeProjectQuery() {
  return state.activeProjectId ? `?project_id=${encodeURIComponent(state.activeProjectId)}` : "";
}

async function saveSettings() {
  state.project = await api(`/api/project/settings${activeProjectQuery()}`, { method: "POST", body: JSON.stringify(settingsPayload()) });
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
  const payload = { ...musicArrangement(), ...patch };
  state.project = await api(`/api/project/arrangement/music${activeProjectQuery()}`, { method: "POST", body: JSON.stringify(payload) });
  if (patch.mode) setStatus(`Music mode saved: ${payload.mode}`);
  if (patch.volume_envelope) setStatus("Music automation saved");
  render();
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
}

function formatTime(seconds) {
  const safe = Math.max(0, Number(seconds) || 0);
  const minutes = Math.floor(safe / 60);
  const secs = Math.floor(safe % 60);
  const ms = Math.floor((safe - Math.floor(safe)) * 1000);
  return `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}.${String(ms).padStart(3, "0")}`;
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
  updatePlayheadPosition();
  updateAutomationCursorReadout();
}

function setTimelineCursor(seconds, { fromPlayback = false } = {}) {
  state.timeline.cursorSec = Math.max(0, Math.min(Number(seconds) || 0, state.timeline.durationSec || 0));
  updateTransportReadout();
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
  const label = $("musicLaneLabel");
  if (label) label.textContent = music.sources.length ? `Music: ${music.sources.length} source(s) · ${music.lanes.length} lane(s) · ${music.tracks.length} clip(s)` : "Music: none loaded";
  renderMusicClipEditor();
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
  const value = point || { time: state.timeline.cursorSec, volume: envelopeValueAt(target, state.timeline.cursorSec) };
  const label = envelopeTargetLabel(target);
  const selected = state.envelope.selectedIndex >= 0 ? `${label} point selected` : "Volume automation";
  el.textContent = `${selected} · ${formatTime(value.time)} · vol ${value.volume.toFixed(2)} · music gain = master curve × lane curve × lane base × clip`;
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
    loopBtn.textContent = music.mode === "chain_loop" ? "Loop chain: ON" : "Loop chain to end";
  }
  const addButtonsDisabled = !music.sources.length;
  for (const id of ["musicLibraryAddAtCursorBtn", "musicLibraryAppendBtn"]) {
    const button = $(id);
    if (button) button.disabled = addButtonsDisabled;
  }
  if (!music.sources.length) {
    root.innerHTML = `<div class="chunkNavEmpty"><strong>No music sources</strong><small>Upload audio files or add a path/URL.</small></div>`;
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
      <small>${source.duration ? formatTime(source.duration) : "duration loads after preview"}</small>
      <button type="button" class="secondary deleteMusicSourceBtn">Delete source + lanes</button>
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
  const sourceEntry = chunkSourceCandidates(project).find(({ value }) => Array.isArray(value) && value.length) || chunkSourceCandidates(project).find(({ value }) => Array.isArray(value));
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
  state.screenMode = ["projects", "chunk", "project"].includes(mode) ? mode : "project";
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
function renderCentralScreen() {
  const isProjects = state.screenMode === "projects";
  const isChunk = state.screenMode === "chunk";
  $("projectsScreen")?.classList.toggle("active", isProjects);
  $("projectScreen")?.classList.toggle("active", !isProjects && !isChunk);
  $("chunkScreen")?.classList.toggle("active", isChunk);
  $("projectsModeTab")?.classList.toggle("active", isProjects);
  $("projectModeTab")?.classList.toggle("active", !isProjects && !isChunk);
  $("chunkModeTab")?.classList.toggle("active", isChunk);
  $("projectsModeTab")?.classList.toggle("secondary", !isProjects);
  $("projectModeTab")?.classList.toggle("secondary", isProjects || isChunk);
  $("chunkModeTab")?.classList.toggle("secondary", !isChunk);
  renderProjectsList();
  if (isChunk) renderChunkDetail(selectedChunk());
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

function renderChunks() {
  renderChunkDetail(state.screenMode === "chunk" ? selectedChunk() : null);
  renderChunkNavigator();
}

function chunkNavSignature() {
  return getChunks().map((chunk) => `${chunk.id}:${chunk.order}:${Boolean(selectedAudioUrlForChunk(chunk))}:${chunk.selected_version_id || ""}:${(chunk.text || "").slice(0, 48)}`).join("|");
}

function setActiveChunkNav(chunkId) {
  state.chunkNav.activeId = chunkId || state.chunkNav.activeId;
  document.querySelectorAll(".chunkNavItem").forEach((item) => item.classList.toggle("active", item.dataset.chunkId === state.chunkNav.activeId));
  document.querySelectorAll(".chunk").forEach((item) => item.classList.toggle("focused", item.dataset.chunkId === state.chunkNav.activeId));
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
    item.innerHTML = `<strong>#${chunk.order + 1}</strong><span>${escapeHtml((chunk.text || "").slice(0, 80))}</span><small class="${ready ? "ready" : "missing"}">${ready ? "generated" : "missing"}</small>`;
    item.onclick = () => selectChunk(chunk.id);
    root.appendChild(item);
  }
  setActiveChunkNav(state.selectedChunkId || state.chunkNav.activeId || chunks[0]?.id || "");
}

function renderChunkCard(chunk) {
  const selectedVersion = selectedVersionForChunk(chunk);
  const selectedLabel = selectedVersion ? (selectedVersion.label || selectedVersion.id) : "none";
  const selectedAudioUrl = selectedAudioUrlForChunk(chunk);
  const card = document.createElement("article");
  card.className = "chunk";
  card.id = `chunk-card-${chunk.id}`;
  card.tabIndex = -1;
  card.dataset.chunkId = chunk.id;
  card.innerHTML = `
    <div class="chunkHead">
      <strong>Chunk ${chunk.order + 1}</strong>
      <span>start ${chunk.start_time || 0}s · selected ${escapeHtml(selectedLabel)} · duration ${chunk.duration_sec || 0}s · pause after ${(chunk.pause_after ?? 0)}s</span>
    </div>
    <textarea class="chunkText">${escapeHtml(chunk.text || "")}</textarea>
    <div class="row wrap">
      <label>Pause after, sec <input class="pauseAfter" type="number" min="0" max="10" step="0.01" value="${clampPauseAfter(chunk.pause_after ?? 0)}" /></label>
      <button type="button" class="saveChunk secondary">Save</button>
      <button type="button" class="generateChunk">Generate another version</button>
      <button type="button" class="moveUp secondary">↑</button>
      <button type="button" class="moveDown secondary">↓</button>
    </div>
    <div class="audioSlot selectedAudio"><strong>Selected for export:</strong> ${selectedAudioUrl ? `<audio controls src="${selectedAudioUrl}"></audio>` : "No selected audio yet."}</div>
    <div class="versions"></div>
  `;
  card.querySelector(".saveChunk").onclick = () => updateChunk(chunk.id, {
    text: card.querySelector(".chunkText").value,
    pause_after: clampPauseAfter(card.querySelector(".pauseAfter").value),
  });
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
  $("exportResult").innerHTML = exp && exp.url
    ? `<a href="${exp.url}" download>Download ${exp.path}</a><p>${exp.duration_sec}s · ${exp.sample_rate} Hz</p><audio controls src="${exp.url}"></audio>`
    : "No export yet.";
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
  state.chunkNav = { activeId: "", signature: "" };
  state.musicClip = { selectedId: "", draggingId: "", selectedSourceId: "", selectedLaneId: "" };
  state.envelope.selectedIndex = -1;
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
  if (!state.selectedChunkId && chunks.length && state.screenMode === "chunk") state.selectedChunkId = chunks[0].id;
  state.chunkNav.activeId = state.selectedChunkId || state.chunkNav.activeId || chunks[0]?.id || "";
  safeRenderStep("chunk navigator", () => renderChunkNavigator(true));
  safeRenderStep("settings", renderSettings);
  safeRenderStep("health", renderHealth);
  safeRenderStep("timeline", renderTimeline);
  safeRenderStep("central screen", renderCentralScreen);
  safeRenderStep("chunk navigator refresh", () => renderChunkNavigator(true));
  safeRenderStep("progress", renderProgress);
  safeRenderStep("queue", renderQueue);
  safeRenderStep("music library", renderMusicLibraryPanel);
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

function taskChunkId(task) {
  return task?.result_chunk_id || task?.chunk_id || null;
}

async function refreshCompletedTaskChunks(previousStatuses, tasks) {
  const chunkIds = new Set();
  let exportCompleted = false;
  for (const task of tasks) {
    const previous = previousStatuses.get(task.id);
    if (previous && previous !== "done" && task.status === "done") {
      if (task.kind === "generate_chunk") {
        const chunkId = taskChunkId(task);
        if (chunkId) chunkIds.add(chunkId);
      } else if (task.kind === "export") {
        exportCompleted = true;
      }
    }
  }
  for (const chunkId of chunkIds) {
    await refreshChunkBlock(chunkId).catch((err) => setStatus(`Chunk refresh failed: ${err.message}`));
  }
  if (exportCompleted) await refreshExportOnly().catch((err) => setStatus(`Export refresh failed: ${err.message}`));
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
        text: card.querySelector(".chunkText").value,
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
    const split_pause_after_min = Number(splitMinInput.value);
    const split_pause_after_max = Number(splitMaxInput.value);
    await api(`/api/project/settings${activeProjectQuery()}`, { method: "POST", body: JSON.stringify(settingsPayload()) });
    setStatus("Splitting…", true);
    state.project = await api(`/api/chunks/split${activeProjectQuery()}`, {
      method: "POST",
      body: JSON.stringify({ text, max_chars: maxChars, split_pause_after_min, split_pause_after_max }),
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

window.addEventListener("resize", updatePlayheadPosition);

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
    setStatus("Queueing export…", true);
    const data = await api(`/api/queue/export${activeProjectQuery()}`, { method: "POST", body: "{}" });
    state.project = data.project;
    state.queue = data.queue || state.queue;
    rememberTaskStatuses(state.queue);
    await refreshQueue();
    renderQueueOnly();
  } catch (err) { setStatus(`Error: ${err.message}`); }
};

$("projectModeTab").onclick = () => setScreenMode("project");
$("projectsModeTab").onclick = () => { loadProjects().catch((err) => setStatus(`Projects load failed: ${err.message}`)); setScreenMode("projects"); };
$("chunkModeTab").onclick = () => setScreenMode("chunk");
$("backToProjectBtn").onclick = () => setScreenMode("project");
$("refreshQueueBtn").onclick = refreshQueue;
const clearCompletedQueueBtn = $("clearCompletedQueueBtn");
if (clearCompletedQueueBtn) clearCompletedQueueBtn.onclick = () => clearCompletedQueueTasks().catch((err) => setStatus(`Clear completed failed: ${err.message}`));
$("manualReloadBtn").onclick = () => window.location.reload();
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


