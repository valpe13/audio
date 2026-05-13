window.XTTSStudio = window.XTTSStudio || {};

(function registerGroupMediaTimeline(namespace) {
  const clamp = (value, min, max) => Math.max(min, Math.min(max, Number(value) || 0));
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"]/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m]));
  const formatSeconds = (seconds) => {
    const safe = Math.max(0, Number(seconds) || 0);
    const minutes = Math.floor(safe / 60);
    const secs = Math.floor(safe % 60);
    return `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  };

  function timelineScale(duration) {
    return Math.max(1, Number(duration) || 1);
  }

  function mediaPath(item) {
    return String(item?.source_path || item?.path || item?.url || item?.source_url || "");
  }

  function chunkStart(chunk) {
    return Number(chunk?.local_start_sec ?? chunk?.start_offset_sec ?? chunk?.start ?? 0) || 0;
  }

  function chunkDuration(chunk) {
    return Math.max(0, Number(chunk?.duration_sec ?? chunk?.duration ?? 0) || 0);
  }

  function itemDuration(item, groupDuration) {
    const explicit = Number(item?.duration_sec || 0);
    if (explicit > 0) return explicit;
    return Math.max(0.25, Number(groupDuration || 0) - Number(item?.start_offset_sec || 0));
  }

  function activeSubtitleBlocksAt(blocks, timeSec, groupDuration) {
    const time = clamp(timeSec, 0, Math.max(0.25, Number(groupDuration || 0)));
    const subtitle = namespace.GroupSubtitleTimeline;
    if (subtitle?.progressiveBlocks) return subtitle.progressiveBlocks(blocks, time, groupDuration, {});
    return (Array.isArray(blocks) ? blocks : [])
      .map((block, index) => subtitle?.normalizeBlock?.(block, index, groupDuration, {}) || block)
      .filter((block) => {
        if (!block || block.enabled === false) return false;
        const start = clamp(block.start_offset_sec ?? block.start ?? 0, 0, groupDuration);
        const end = start + Math.max(0.05, Number(block.duration_sec ?? block.duration ?? 0.05) || 0.05);
        return time >= start && time < end;
      });
  }

  function normalizedItemsFromRows(card, groupDuration) {
    return [...card.querySelectorAll(".groupMediaItem")].map((row, index) => {
      const value = (field) => row.querySelector(`[data-media-field='${field}']`)?.value || "";
      const checked = (field) => row.querySelector(`[data-media-field='${field}']`)?.checked;
      const start = clamp(value("start_offset_sec"), 0, Math.max(0, groupDuration || 0));
      const duration = clamp(value("duration_sec"), 0, Math.max(0, groupDuration || 0));
      return {
        id: row.dataset.mediaId || `media_${index}`,
        source_id: value("source_id") || row.dataset.sourceId || "",
        type: value("type") || "image",
        path: value("path"),
        label: value("label") || value("path") || `Media ${index + 1}`,
        role: value("role") || "main",
        start_offset_sec: start,
        duration_sec: duration,
        visual_duration_sec: duration > 0 ? duration : itemDuration({ start_offset_sec: start }, groupDuration),
        fit: value("fit") || "cover",
        scheduled: (() => { const box = row.querySelector(`[data-media-field='scheduled']`); return Boolean(box && !box.disabled && box.checked); })(),
        timeline_source: value("timeline_source") || row.dataset.timelineSource || "",
        auto_sequence_id: value("auto_sequence_id") || row.dataset.autoSequenceId || "",
        chunk_id: value("chunk_id") || row.dataset.chunkId || "",
        prompt_scope: value("prompt_scope") || row.dataset.promptScope || "",
      };
    });
  }

  function setRowValue(row, field, value) {
    const input = row?.querySelector?.(`[data-media-field='${field}']`);
    if (!input) return;
    input.value = String(value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function render(host, group, mediaItems, options = {}) {
    if (!host) return;
    const duration = Math.max(0.25, Number(group?.duration || 0));
    const scale = timelineScale(duration);
    const items = namespace.GroupMediaUtils?.scheduledItems?.(mediaItems) || (Array.isArray(mediaItems) ? mediaItems.filter((item) => item?.scheduled !== false) : []);
    const chunks = Array.isArray(options.chunks) ? options.chunks : [];
    const subtitleLane = namespace.GroupSubtitleTimeline?.laneHtml?.(group, Array.isArray(options.subtitleBlocks) ? options.subtitleBlocks : []);
    const rulerTicks = [];
    const tickCount = Math.min(12, Math.max(2, Math.ceil(duration / 5)));
    for (let i = 0; i <= tickCount; i += 1) {
      const time = (duration / tickCount) * i;
      rulerTicks.push(`<span style="left:${(time / scale) * 100}%">${escapeHtml(formatSeconds(time))}</span>`);
    }
    const blocks = items.map((item, index) => {
      const start = clamp(item.start_offset_sec, 0, duration);
      const visualDuration = Math.max(0.25, itemDuration(item, duration));
      const width = Math.max(3, Math.min(100 - (start / scale) * 100, (visualDuration / scale) * 100));
      const left = (start / scale) * 100;
      const type = item.type === "video" ? "video" : "image";
      return `<button type="button" class="groupMediaTimelineBlock ${type} ${item.id === options.selectedId ? "selected" : ""}" data-media-index="${index}" data-media-id="${escapeHtml(item.id || `media_${index}`)}" style="left:${left}%;width:${width}%" title="${escapeHtml(item.label || mediaPath(item))}\nstart ${start.toFixed(2)}s · duration ${Number(item.duration_sec || 0).toFixed(2)}s">
        <span>${escapeHtml(item.label || mediaPath(item) || `Media ${index + 1}`)}</span>
        <small>${escapeHtml(type)} · ${start.toFixed(2)}s → ${(start + visualDuration).toFixed(2)}s</small>
        <b class="groupMediaHandle left" title="Resize left"></b><b class="groupMediaHandle right" title="Resize right"></b>
      </button>`;
    }).join("");
    host.innerHTML = `
      <div class="groupMediaTimelineHead">
        <div>
          <strong>Таймлайн медиа группы</strong>
          <small>0 → ${escapeHtml(formatSeconds(duration))}. Выберите блок, сдвиньте/измените длительность, затем сохраните группу.</small>
        </div>
        <div class="groupMediaTimelineButtons">
          <button type="button" class="secondary groupMediaPreviewPlay">▶ Играть</button>
          <button type="button" class="secondary groupMediaPreviewStop">■ Стоп</button>
          <button type="button" class="secondary groupMediaNudgeLeft">← 0.5s</button>
          <button type="button" class="secondary groupMediaNudgeRight">0.5s →</button>
          <button type="button" class="secondary groupMediaShorten">− длит.</button>
          <button type="button" class="secondary groupMediaLengthen">+ длит.</button>
        </div>
      </div>
      <div class="groupMediaTimelineRuler">${rulerTicks.join("")}</div>
      <input type="range" class="groupMediaPlayheadSlider" min="0" max="${duration.toFixed(3)}" step="0.05" value="0" aria-label="Позиция предпросмотра медиа группы" />
      <div class="groupMediaTimelineLane" tabindex="0"><i class="groupMediaPlayhead" style="left:0%"></i><i class="groupMediaSnapMarker" hidden><span>идеальный стык</span></i>${blocks || `<div class="groupMediaTimelineEmpty">На таймлайне пока нет медиа-блоков. Перетащите миниатюру сюда; исходник не будет дублироваться.</div>`}</div>
      <div class="groupChunkTimelineLane" aria-label="Дорожка чанков группы">
        ${chunks.map((chunk) => {
          const start = clamp(chunkStart(chunk), 0, duration);
          const len = Math.max(0.05, chunkDuration(chunk));
          const left = (start / scale) * 100;
          const width = Math.max(2, Math.min(100 - left, (len / scale) * 100));
          return `<button type="button" class="groupChunkTimelineBlock ${chunk.audio_url ? "ready" : "missing"}" data-chunk-id="${escapeHtml(chunk.id || "")}" style="left:${left}%;width:${width}%" title="${escapeHtml(chunk.label || "Чанк")} · ${start.toFixed(2)}s → ${(start + len).toFixed(2)}s${chunk.audio_url ? "" : " · аудио нет"}"><span>${escapeHtml(chunk.label || "Чанк")}</span></button>`;
        }).join("") || `<div class="groupMediaTimelineEmpty compact">В группе нет чанков с таймингом.</div>`}
      </div>
      <div class="groupMediaSubtitleLaneWrap">
        <div class="groupSubtitleTimelineHead"><strong>Дорожка субтитров</strong><small>Интегрирована в таймлайн группы.</small></div>
        ${subtitleLane || `<div class="groupMediaTimelineEmpty compact">Модуль субтитров не загрузился.</div>`}
      </div>
      <div class="groupMediaTimelineInspector">
        <span class="groupMediaTimelineSelection">Выберите клип таймлайна или отредактируйте строки ниже.</span>
      </div>
    `;
  }

  function bind(host, card, group, rerender, callbacks = {}) {
    if (!host || !card) return;
    const duration = Math.max(0.25, Number(group?.duration || 0));
    let selectedIndex = -1;
    let activeAudio = null;
    let isPlaying = false;
    const rows = () => [...card.querySelectorAll(".groupMediaItem")];
    const timelineItems = () => namespace.GroupMediaUtils?.scheduledItems?.(normalizedItemsFromRows(card, duration)) || normalizedItemsFromRows(card, duration).filter((item) => item.scheduled !== false);
    const isRowScheduled = (row) => {
      const checkbox = row?.querySelector?.(`[data-media-field='scheduled']`);
      return Boolean(checkbox && !checkbox.disabled && checkbox.checked);
    };
    const scheduledRows = () => rows().filter(isRowScheduled);
    const rowSpan = (row) => {
      const start = clamp(row?.querySelector(`[data-media-field='start_offset_sec']`)?.value || 0, 0, duration);
      const len = Math.max(0.05, Number(row?.querySelector(`[data-media-field='duration_sec']`)?.value || 0.05) || 0.05);
      return { start, end: Math.min(duration, start + len), duration: Math.min(duration, start + len) - start };
    };
    const safeSpanForRow = (row, desiredStart, desiredDuration) => {
      const others = scheduledRows()
        .filter((item) => item !== row)
        .map(rowSpan)
        .filter((span) => span.end > span.start)
        .sort((a, b) => a.start - b.start || a.end - b.end);
      const len = Math.max(0.05, Math.min(Number(desiredDuration || 0.05) || 0.05, duration));
      const target = clamp(desiredStart, 0, Math.max(0, duration - len));
      const gaps = [];
      let cursor = 0;
      for (const span of others) {
        if (span.start > cursor + 0.001) gaps.push({ start: cursor, end: span.start });
        cursor = Math.max(cursor, span.end);
      }
      if (cursor < duration - 0.001) gaps.push({ start: cursor, end: duration });
      const containing = gaps.find((gap) => target >= gap.start - 0.001 && target + len <= gap.end + 0.001);
      if (containing) return { start: target, duration: len };
      const adjusted = gaps
        .map((gap) => ({ gap, duration: Math.min(len, gap.end - gap.start), start: clamp(target, gap.start, Math.max(gap.start, gap.end - Math.min(len, gap.end - gap.start))) }))
        .filter((item) => item.duration >= 0.05)
        .sort((a, b) => Math.abs(a.start - target) - Math.abs(b.start - target) || b.duration - a.duration)[0];
      return adjusted ? { start: adjusted.start, duration: adjusted.duration } : null;
    };
    const markManualEdit = (row) => {
      if (!row) return;
      row.dataset.timelineSource = "manual";
      setRowValue(row, "timeline_source", "manual");
      setRowValue(row, "auto_sequence_id", "");
    };
    const activeItemAt = (timeSec) => {
      const time = clamp(timeSec, 0, duration);
      return timelineItems().find((item) => {
        const start = clamp(item.start_offset_sec, 0, duration);
        const end = Math.min(duration, start + itemDuration(item, duration));
        return time >= start && time < end;
      }) || null;
    };
    const activeChunkAt = (timeSec) => {
      const chunks = Array.isArray(callbacks.chunks) ? callbacks.chunks : [];
      const time = clamp(timeSec, 0, duration);
      return chunks.find((chunk) => {
        const start = chunkStart(chunk);
        const end = start + chunkDuration(chunk);
        return time >= start && time < end;
      }) || null;
    };
    const activeSubtitlesAt = (timeSec) => activeSubtitleBlocksAt(callbacks.subtitleBlocks, timeSec, duration);
    const setPlayhead = (timeSec) => {
      const time = clamp(timeSec, 0, duration);
      const slider = host.querySelector(".groupMediaPlayheadSlider");
      const playhead = host.querySelector(".groupMediaPlayhead");
      if (slider) slider.value = String(time);
      if (playhead) playhead.style.left = `${(time / Math.max(0.25, duration)) * 100}%`;
      const item = activeItemAt(time);
      const chunk = activeChunkAt(time);
      const subtitles = activeSubtitlesAt(time);
      callbacks.onPreviewState?.({ item, subtitles, chunk, time, isPlaying });
      callbacks.onPreviewTime?.(item, time, { isPlaying });
      callbacks.onPreviewChunkTime?.(chunk, time, { isPlaying });
      return time;
    };
    const stopPlayback = (options = {}) => {
      isPlaying = false;
      if (namespace.GroupMediaTimeline?.previewTimer) window.clearInterval(namespace.GroupMediaTimeline.previewTimer);
      namespace.GroupMediaTimeline.previewTimer = null;
      if (activeAudio) {
        activeAudio.pause?.();
        activeAudio = null;
      }
      callbacks.onPreviewStop?.(options);
    };
    const startPlayback = () => {
      stopPlayback();
      isPlaying = true;
      let startWall = Date.now();
      let startTime = Number(host.querySelector(".groupMediaPlayheadSlider")?.value || 0);
      if (startTime >= duration - 0.01) startTime = 0;
      setPlayhead(startTime);
      namespace.GroupMediaTimeline.previewTimer = window.setInterval(() => {
        const next = startTime + (Date.now() - startWall) / 1000;
        setPlayhead(next);
        if (next >= duration) stopPlayback();
      }, 120);
    };
    const select = (index) => {
      selectedIndex = index;
      host.querySelectorAll(".groupMediaTimelineBlock").forEach((block) => block.classList.toggle("selected", Number(block.dataset.mediaIndex) === index));
      rows().forEach((row) => row.classList.remove("selected"));
      scheduledRows()[index]?.classList.add("selected");
      const item = timelineItems()[index];
      if (item) callbacks.onSelect?.(item);
      const selection = host.querySelector(".groupMediaTimelineSelection");
      if (selection) selection.textContent = item ? `${item.label} · старт ${item.start_offset_sec.toFixed(2)}s · длительность ${Number(item.duration_sec || 0).toFixed(2)}s` : "Выберите клип таймлайна или отредактируйте строки ниже.";
    };
    const mutateSelected = (patch) => {
      const row = scheduledRows()[selectedIndex];
      if (!row) return;
      const item = timelineItems()[selectedIndex];
      const start = clamp(patch.start_offset_sec ?? item.start_offset_sec, 0, duration);
      const maxDuration = Math.max(0, duration - start);
      const nextDuration = clamp(patch.duration_sec ?? item.duration_sec, 0, maxDuration);
      const safe = safeSpanForRow(row, start, nextDuration);
      if (!safe) {
        callbacks.onReject?.("No free group media timeline space for this edit; change rejected.");
        return;
      }
      setRowValue(row, "start_offset_sec", safe.start.toFixed(2));
      setRowValue(row, "duration_sec", safe.duration.toFixed(2));
      markManualEdit(row);
      rerender?.();
      select(selectedIndex);
    };
    const deleteSelected = () => {
      const row = scheduledRows()[selectedIndex];
      if (!row) return;
      row.dataset.timelineSource = "";
      setRowValue(row, "timeline_source", "");
      setRowValue(row, "auto_sequence_id", "");
      setRowValue(row, "start_offset_sec", "0.00");
      setRowValue(row, "duration_sec", "0.00");
      const scheduledBox = row.querySelector(`[data-media-field='scheduled']`);
      if (scheduledBox) {
        scheduledBox.checked = false;
        scheduledBox.disabled = true;
      }
      selectedIndex = Math.min(selectedIndex, scheduledRows().length - 1);
      rerender?.();
      callbacks.onChange?.();
    };
    const addDropped = (event) => {
      const text = event.dataTransfer.getData("application/x-xtts-group-media");
      if (!text) return;
      const item = JSON.parse(text);
      const rect = host.querySelector(".groupMediaTimelineLane")?.getBoundingClientRect?.();
      const ratio = rect ? clamp((event.clientX - rect.left) / Math.max(1, rect.width), 0, 1) : 0;
      const gap = namespace.GroupMediaUtils?.bestFreeInterval?.(normalizedItemsFromRows(card, duration), duration, ratio * duration);
      if (!gap) {
        callbacks.onReject?.("Group media timeline is fully occupied; drop rejected.");
        return;
      }
      const block = { ...item, id: `block_${Date.now()}_${Math.random().toString(16).slice(2)}`, source_id: item.source_id || item.id || "", start_offset_sec: gap.start, duration_sec: gap.duration, scheduled: true, kind: "timeline_block", timeline_source: "manual", auto_sequence_id: "" };
      callbacks.onAdd?.(block);
      rerender?.();
      callbacks.onChange?.();
    };
    host.addEventListener("click", (event) => {
      const block = event.target.closest?.(".groupMediaTimelineBlock");
      if (block) {
        select(Number(block.dataset.mediaIndex));
        return;
      }
      if (event.target.closest?.(".groupMediaPreviewPlay")) {
        startPlayback();
      } else if (event.target.closest?.(".groupMediaPreviewStop")) {
        stopPlayback();
      } else if (event.target.closest?.(".groupMediaNudgeLeft")) {
        const item = timelineItems()[selectedIndex];
        if (item) mutateSelected({ start_offset_sec: item.start_offset_sec - 0.5 });
      } else if (event.target.closest?.(".groupMediaNudgeRight")) {
        const item = timelineItems()[selectedIndex];
        if (item) mutateSelected({ start_offset_sec: item.start_offset_sec + 0.5 });
      } else if (event.target.closest?.(".groupMediaShorten")) {
        const item = timelineItems()[selectedIndex];
        if (item) mutateSelected({ duration_sec: Math.max(0, Number(item.duration_sec || item.visual_duration_sec) - 0.5) });
      } else if (event.target.closest?.(".groupMediaLengthen")) {
        const item = timelineItems()[selectedIndex];
        if (item) mutateSelected({ duration_sec: Number(item.duration_sec || item.visual_duration_sec) + 0.5 });
      } else if (event.target.closest?.(".deleteGroupMediaSelectedBtn")) {
        deleteSelected();
      }
    });
    const lane = host.querySelector(".groupMediaTimelineLane");
    if (lane) {
      lane.addEventListener("dragover", (event) => {
        if (!event.dataTransfer.types.includes("application/x-xtts-group-media")) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
      });
      lane.addEventListener("drop", (event) => { event.preventDefault(); addDropped(event); });
    }
    host.querySelector(".groupMediaPlayheadSlider")?.addEventListener("input", (event) => { stopPlayback({ keepFrame: true }); setPlayhead(event.target.value); });
    host.querySelector(".groupMediaTimelineButtons")?.insertAdjacentHTML("beforeend", `<button type="button" class="secondary deleteGroupMediaSelectedBtn">Удалить выбранное</button>`);
    card.querySelectorAll(".groupMediaItem input, .groupMediaItem select").forEach((input) => {
      input.addEventListener("input", () => { rerender?.(); select(Math.min(selectedIndex, scheduledRows().length - 1)); });
      input.addEventListener("change", () => { rerender?.(); select(Math.min(selectedIndex, scheduledRows().length - 1)); });
    });
    const onKeyDown = (event) => {
      const editingText = event.target?.closest?.("input,textarea,select,[contenteditable='true'],[contenteditable='']");
      if (editingText || selectedIndex < 0 || !host.isConnected) return;
      if (event.key === "Delete" || event.key === "Backspace") {
        event.preventDefault();
        deleteSelected();
      }
    };
    if (namespace.GroupMediaTimeline?.activeKeydown) document.removeEventListener("keydown", namespace.GroupMediaTimeline.activeKeydown);
    namespace.GroupMediaTimeline.activeKeydown = onKeyDown;
    document.addEventListener("keydown", onKeyDown);
    host.querySelectorAll(".groupMediaTimelineBlock").forEach((block) => {
      block.addEventListener("pointerdown", (event) => {
        if (event.button !== 0) return;
        event.preventDefault();
        const index = Number(block.dataset.mediaIndex);
        select(index);
        const item = timelineItems()[index];
        const startX = event.clientX;
        const edge = event.target.classList.contains("left") ? "left" : event.target.classList.contains("right") ? "right" : "move";
        const start = Number(item.start_offset_sec || 0);
        const len = Number(item.duration_sec || item.visual_duration_sec || 1);
        const rect = host.querySelector(".groupMediaTimelineLane")?.getBoundingClientRect?.();
        const pxPerSec = (rect?.width || 1) / Math.max(0.25, duration);
        const onMove = (moveEvent) => {
          const delta = (moveEvent.clientX - startX) / Math.max(1, pxPerSec);
          if (edge === "left") mutateSelected({ start_offset_sec: start + delta, duration_sec: len - delta });
          else if (edge === "right") mutateSelected({ duration_sec: len + delta });
          else mutateSelected({ start_offset_sec: start + delta, duration_sec: len });
        };
        const onUp = () => { document.removeEventListener("pointermove", onMove); document.removeEventListener("pointerup", onUp); callbacks.onChange?.(); };
        document.addEventListener("pointermove", onMove);
        document.addEventListener("pointerup", onUp, { once: true });
      });
    });
  }

  namespace.GroupMediaTimeline = { render, bind, normalizedItemsFromRows };
})(window.XTTSStudio);
