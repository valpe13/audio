window.XTTSStudio = window.XTTSStudio || {};

(function registerGroupMediaUtils(namespace) {
  const clamp = (value, min, max) => Math.max(min, Math.min(max, Number(value) || 0));

  function mediaKey(item) {
    const raw = String(item?.source_path || item?.path || item?.url || item?.source_url || item?.id || "").trim();
    return `${item?.type === "video" ? "video" : "image"}:${raw.toLowerCase()}`;
  }

  function isScheduledBlock(item) {
    if (!item || typeof item !== "object") return false;
    return item.scheduled !== false && (item.start_offset_sec !== undefined || item.duration_sec !== undefined || item.kind === "timeline_block");
  }

  function scheduledItems(items) {
    return (Array.isArray(items) ? items : []).filter(isScheduledBlock);
  }

  function assetItems(items) {
    const out = [];
    const seen = new Set();
    for (const item of Array.isArray(items) ? items : []) {
      if (!item || item.type === "audio") continue;
      const key = mediaKey(item);
      if (!key.split(":").slice(1).join(":") || seen.has(key)) continue;
      seen.add(key);
      out.push({ ...item, scheduled: false, asset_key: key });
    }
    return out;
  }

  function itemEnd(item) {
    return Number(item?.start_offset_sec || 0) + Math.max(0, Number(item?.duration_sec || item?.visual_duration_sec || 0));
  }

  function itemDuration(item, groupDuration) {
    const explicit = Number(item?.duration_sec || 0);
    if (explicit > 0) return explicit;
    return Math.max(0.25, Number(groupDuration || 0) - Number(item?.start_offset_sec || 0));
  }

  function activeItemAt(items, timeSec, groupDuration) {
    const duration = Math.max(0.25, Number(groupDuration || 0));
    const time = clamp(timeSec, 0, duration);
    return scheduledItems(items).find((item) => {
      const start = clamp(item.start_offset_sec, 0, duration);
      const end = Math.min(duration, start + itemDuration(item, duration));
      return time >= start && time < end;
    }) || null;
  }

  function freeIntervals(items, duration) {
    const end = Math.max(0, Number(duration) || 0);
    const spans = scheduledItems(items)
      .map((item) => ({ start: clamp(item.start_offset_sec, 0, end), end: clamp(itemEnd(item), 0, end) }))
      .filter((span) => span.end > span.start)
      .sort((a, b) => a.start - b.start || a.end - b.end);
    const gaps = [];
    let cursor = 0;
    for (const span of spans) {
      if (span.start > cursor + 0.001) gaps.push({ start: cursor, end: span.start, duration: span.start - cursor });
      cursor = Math.max(cursor, span.end);
    }
    if (cursor < end - 0.001) gaps.push({ start: cursor, end, duration: end - cursor });
    return gaps;
  }

  function bestFreeInterval(items, duration, pointerTime = 0) {
    const gaps = freeIntervals(items, duration);
    if (!gaps.length) return null;
    const time = clamp(pointerTime, 0, duration);
    return gaps.find((gap) => time >= gap.start - 0.001 && time <= gap.end + 0.001)
      || gaps.slice().sort((a, b) => b.duration - a.duration || a.start - b.start)[0];
  }

  function groupChunkTimelineItems(group, arrangement = []) {
    const chunkIds = Array.isArray(group?.chunk_ids) ? group.chunk_ids.map(String) : [];
    const selected = new Set(chunkIds);
    const parts = Array.isArray(group?.parts) && group.parts.length ? group.parts : arrangement;
    const groupStart = Number(group?.start || 0) || 0;
    return (Array.isArray(parts) ? parts : [])
      .filter((part) => {
        const chunkId = String(part?.chunk?.id || part?.id || "");
        return chunkId && (!selected.size || selected.has(chunkId));
      })
      .map((part, index) => {
        const chunk = part.chunk || part;
        const absoluteStart = Number(part.start ?? chunk.start_time ?? groupStart) || groupStart;
        const duration = Math.max(0, Number(part.duration ?? part.duration_sec ?? chunk.duration_sec ?? 0) || 0);
        const order = Number.isFinite(Number(chunk.order)) ? Number(chunk.order) : index;
        const audioUrl = part.audioUrl || chunk.audio_url || (Array.isArray(chunk.versions) ? chunk.versions.find((version) => version?.id === chunk.selected_version_id)?.audio_url || chunk.versions.find((version) => version?.audio_url)?.audio_url : "") || "";
        return {
          id: chunk.id || `chunk_${index}`,
          order,
          label: `Чанк ${order + 1}`,
          text: chunk.tts_text || chunk.text || "",
          audio_url: audioUrl,
          local_start_sec: clamp(absoluteStart - groupStart, 0, Math.max(0, Number(group?.duration || 0) || 0)),
          start_offset_sec: clamp(absoluteStart - groupStart, 0, Math.max(0, Number(group?.duration || 0) || 0)),
          duration_sec: duration,
        };
      })
      .sort((a, b) => a.local_start_sec - b.local_start_sec || a.order - b.order);
  }

  namespace.GroupMediaUtils = { mediaKey, isScheduledBlock, scheduledItems, assetItems, itemDuration, itemEnd, activeItemAt, freeIntervals, bestFreeInterval, groupChunkTimelineItems };
})(window.XTTSStudio);
