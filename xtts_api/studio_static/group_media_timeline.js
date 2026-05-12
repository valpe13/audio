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
    return String(item?.path || item?.url || "");
  }

  function itemDuration(item, groupDuration) {
    const explicit = Number(item?.duration_sec || 0);
    if (explicit > 0) return explicit;
    return Math.max(0.25, Number(groupDuration || 0) - Number(item?.start_offset_sec || 0));
  }

  function normalizedItemsFromRows(card, groupDuration) {
    return [...card.querySelectorAll(".groupMediaItem")].map((row, index) => {
      const value = (field) => row.querySelector(`[data-media-field='${field}']`)?.value || "";
      const checked = (field) => row.querySelector(`[data-media-field='${field}']`)?.checked;
      const start = clamp(value("start_offset_sec"), 0, Math.max(0, groupDuration || 0));
      const duration = clamp(value("duration_sec"), 0, Math.max(0, groupDuration || 0));
      return {
        id: row.dataset.mediaId || `media_${index}`,
        type: value("type") || "image",
        path: value("path"),
        label: value("label") || value("path") || `Media ${index + 1}`,
        role: value("role") || "main",
        start_offset_sec: start,
        duration_sec: duration,
        visual_duration_sec: duration > 0 ? duration : itemDuration({ start_offset_sec: start }, groupDuration),
        fit: value("fit") || "cover",
        scheduled: checked("scheduled") !== false,
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
          <strong>Group media timeline</strong>
          <small>0 → ${escapeHtml(formatSeconds(duration))}. Select a clip, nudge/resize, then Save group.</small>
        </div>
        <div class="groupMediaTimelineButtons">
          <button type="button" class="secondary groupMediaNudgeLeft">← 0.5s</button>
          <button type="button" class="secondary groupMediaNudgeRight">0.5s →</button>
          <button type="button" class="secondary groupMediaShorten">− duration</button>
          <button type="button" class="secondary groupMediaLengthen">+ duration</button>
        </div>
      </div>
      <div class="groupMediaTimelineRuler">${rulerTicks.join("")}</div>
      <div class="groupMediaTimelineLane" tabindex="0">${blocks || `<div class="groupMediaTimelineEmpty">No scheduled clips yet. Drag media here to fill a free gap; library-only media stays below.</div>`}</div>
      <div class="groupMediaTimelineInspector">
        <span class="groupMediaTimelineSelection">Select a timeline clip or edit rows below.</span>
      </div>
    `;
  }

  function bind(host, card, group, rerender, callbacks = {}) {
    if (!host || !card) return;
    const duration = Math.max(0.25, Number(group?.duration || 0));
    let selectedIndex = -1;
    const rows = () => [...card.querySelectorAll(".groupMediaItem")];
    const timelineItems = () => namespace.GroupMediaUtils?.scheduledItems?.(normalizedItemsFromRows(card, duration)) || normalizedItemsFromRows(card, duration).filter((item) => item.scheduled !== false);
    const scheduledRows = () => rows().filter((row) => row.querySelector(`[data-media-field='scheduled']`)?.checked !== false);
    const select = (index) => {
      selectedIndex = index;
      host.querySelectorAll(".groupMediaTimelineBlock").forEach((block) => block.classList.toggle("selected", Number(block.dataset.mediaIndex) === index));
      rows().forEach((row) => row.classList.remove("selected"));
      scheduledRows()[index]?.classList.add("selected");
      const item = timelineItems()[index];
      if (item) callbacks.onSelect?.(item);
      const selection = host.querySelector(".groupMediaTimelineSelection");
      if (selection) selection.textContent = item ? `${item.label} · start ${item.start_offset_sec.toFixed(2)}s · duration ${Number(item.duration_sec || 0).toFixed(2)}s` : "Select a timeline clip or edit rows below.";
    };
    const mutateSelected = (patch) => {
      const row = scheduledRows()[selectedIndex];
      if (!row) return;
      const item = timelineItems()[selectedIndex];
      const start = clamp(patch.start_offset_sec ?? item.start_offset_sec, 0, duration);
      const maxDuration = Math.max(0, duration - start);
      const nextDuration = clamp(patch.duration_sec ?? item.duration_sec, 0, maxDuration);
      setRowValue(row, "start_offset_sec", start.toFixed(2));
      setRowValue(row, "duration_sec", nextDuration.toFixed(2));
      rerender?.();
      select(selectedIndex);
    };
    const deleteSelected = () => {
      const row = scheduledRows()[selectedIndex];
      if (!row) return;
      row.remove();
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
      item.start_offset_sec = gap.start;
      item.duration_sec = gap.duration;
      item.scheduled = true;
      callbacks.onAdd?.(item);
      rerender?.();
      callbacks.onChange?.();
    };
    host.addEventListener("click", (event) => {
      const block = event.target.closest?.(".groupMediaTimelineBlock");
      if (block) {
        select(Number(block.dataset.mediaIndex));
        return;
      }
      if (event.target.closest?.(".groupMediaNudgeLeft")) {
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
    host.querySelector(".groupMediaTimelineButtons")?.insertAdjacentHTML("beforeend", `<button type="button" class="secondary deleteGroupMediaSelectedBtn">Delete selected</button>`);
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
