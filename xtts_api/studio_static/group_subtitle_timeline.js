window.XTTSStudio = window.XTTSStudio || {};

(function registerGroupSubtitleTimeline(namespace) {
  const clamp = (value, min, max) => Math.max(min, Math.min(max, Number(value) || 0));
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"]/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m]));
  const uuid = () => crypto.randomUUID?.() || `subtitle_${Date.now()}_${Math.random().toString(16).slice(2)}`;
  const DEFAULTS = { position: "bottom", font_family: "Arial", font_size: 20, color: "#ffffff", background: "#000000", background_opacity: 0.45, outline: 2, max_words: 5, word_offset_sec: 0 };

  function defaults(raw = {}) { return normalizeStyle({ ...DEFAULTS, ...(raw && typeof raw === "object" ? raw : {}) }); }

  function normalizeStyle(raw = {}) {
    const opacityRaw = raw.background_opacity;
    const opacity = opacityRaw === "" || opacityRaw === null || opacityRaw === undefined ? DEFAULTS.background_opacity : clamp(opacityRaw, 0, 1);
    const maxWordsRaw = raw.max_words;
    const maxWords = maxWordsRaw === "" || maxWordsRaw === null || maxWordsRaw === undefined ? DEFAULTS.max_words : Math.round(clamp(maxWordsRaw, 1, 40));
    const offsetRaw = raw.word_offset_sec;
    const offset = offsetRaw === "" || offsetRaw === null || offsetRaw === undefined ? DEFAULTS.word_offset_sec : clamp(offsetRaw, -5, 5);
    return { ...raw, background_opacity: opacity, max_words: maxWords, word_offset_sec: offset };
  }

  function normalizeBlock(raw = {}, index = 0, groupDuration = 1, fallbackDefaults = {}) {
    const d = defaults(fallbackDefaults);
    const start = clamp(raw.start_offset_sec ?? raw.start ?? 0, 0, Math.max(0, groupDuration));
    const duration = clamp(raw.duration_sec ?? raw.duration ?? Math.max(0.25, groupDuration - start), 0.05, Math.max(0.05, groupDuration - start || groupDuration || 1));
    return { id: raw.id || uuid(), enabled: raw.enabled !== false, text: String(raw.text ?? ""), start_offset_sec: start, duration_sec: duration, position: ["top", "center", "bottom"].includes(raw.position) ? raw.position : d.position, font_family: String(raw.font_family || d.font_family), font_size: clamp(raw.font_size ?? d.font_size, 8, 160), color: String(raw.color || d.color), background: String(raw.background || d.background), background_opacity: raw.background_opacity === "" || raw.background_opacity === null || raw.background_opacity === undefined ? d.background_opacity : clamp(raw.background_opacity, 0, 1), outline: clamp(raw.outline ?? d.outline, 0, 12), max_words: Math.round(clamp(raw.max_words ?? d.max_words, 1, 40)), word_offset_sec: clamp(raw.word_offset_sec ?? d.word_offset_sec, -5, 5), order: Number.isFinite(Number(raw.order)) ? Number(raw.order) : index };
  }

  function groupTextFromChunks(chunks = []) { return chunks.map((chunk) => String(chunk.text || chunk.tts_text || chunk.label || "").trim()).filter(Boolean).join(" "); }
  function blockFromGroup(group, chunks = []) { return normalizeBlock({ text: groupTextFromChunks(chunks) || group.summary || group.title || "Субтитры", start_offset_sec: 0, duration_sec: Math.max(0.25, Number(group?.duration || 1)) }, 0, Number(group?.duration || 1), group?.subtitle_defaults); }
  function blocksFromChunks(group, chunks = []) { const duration = Math.max(0.25, Number(group?.duration || 1)); return chunks.map((chunk, index) => normalizeBlock({ text: chunk.text || chunk.tts_text || chunk.label || `Чанк ${index + 1}`, start_offset_sec: chunk.local_start_sec ?? chunk.start_offset_sec ?? 0, duration_sec: chunk.duration_sec || 0.5 }, index, duration, group?.subtitle_defaults)); }

  function blocksFromRows(card, groupDuration, fallbackDefaults = {}) {
    return [...card.querySelectorAll(".groupSubtitleBlockRow")].map((row, index) => {
      const value = (field) => row.querySelector(`[data-subtitle-field='${field}']`)?.value || "";
      return normalizeBlock({ id: row.dataset.subtitleId, enabled: row.querySelector("[data-subtitle-field='enabled']")?.checked !== false, text: value("text"), start_offset_sec: value("start_offset_sec"), duration_sec: value("duration_sec"), position: value("position"), font_family: value("font_family"), font_size: value("font_size"), color: value("color"), background: value("background"), background_opacity: value("background_opacity"), outline: value("outline"), max_words: value("max_words"), word_offset_sec: value("word_offset_sec"), order: index }, index, groupDuration, fallbackDefaults);
    });
  }

  function progressiveText(block, timeSec) {
    if (!block || block.enabled === false) return "";
    const text = String(block.text || "").replace(/\s+/g, " ").trim();
    if (!text) return "";
    const words = text.split(" ").filter(Boolean);
    if (!words.length) return "";
    const start = Number(block.start_offset_sec || 0);
    const duration = Math.max(0.05, Number(block.duration_sec || 0.05));
    const offset = clamp(block.word_offset_sec ?? 0, -5, 5);
    const adjustedTime = Number(timeSec || 0) - start + offset;
    if (adjustedTime < 0) return "";
    const wordDuration = duration / Math.max(1, words.length);
    const visibleCount = clamp(Math.floor(adjustedTime / Math.max(0.001, wordDuration)) + 1, 0, words.length);
    if (visibleCount <= 0) return "";
    const maxWords = Math.max(1, Math.round(clamp(block.max_words ?? DEFAULTS.max_words, 1, 40)));
    const chunkStart = Math.floor((visibleCount - 1) / maxWords) * maxWords;
    return words.slice(chunkStart, visibleCount).join(" ");
  }

  function progressiveBlocks(blocks = [], timeSec = 0, groupDuration = 1, fallbackDefaults = {}) {
    return (Array.isArray(blocks) ? blocks : [])
      .map((block, index) => normalizeBlock(block, index, groupDuration, fallbackDefaults))
      .map((block) => ({ ...block, full_text: block.text, text: progressiveText(block, timeSec) }))
      .filter((block) => block.enabled !== false && String(block.text || "").trim());
  }

  function segmentsForBlock(block = {}, groupStart = 0, groupEnd = null) {
    const normalized = normalizeBlock(block, 0, Math.max(0.05, Number(block.duration_sec || block.duration || 1)), block);
    const text = String(normalized.text || "").replace(/\s+/g, " ").trim();
    const words = text.split(" ").filter(Boolean);
    if (!words.length || normalized.enabled === false) return [];
    const startOffset = Number(normalized.start_offset_sec || 0);
    const duration = Math.max(0.05, Number(normalized.duration_sec || 0.05));
    const offset = clamp(normalized.word_offset_sec ?? 0, -5, 5);
    const wordDuration = duration / Math.max(1, words.length);
    const blockGlobalStart = Number(groupStart || 0) + startOffset;
    const blockGlobalEnd = blockGlobalStart + duration;
    const clampEnd = Number.isFinite(Number(groupEnd)) ? Number(groupEnd) : null;
    const segments = [];
    let previousText = "";
    for (let wordIndex = 0; wordIndex < words.length; wordIndex += 1) {
      const localStart = startOffset + (wordIndex * wordDuration) - offset;
      const nextLocal = startOffset + ((wordIndex + 1) * wordDuration) - offset;
      let start = Math.max(0, Number(groupStart || 0) + localStart);
      let end = Math.min(blockGlobalEnd, Number(groupStart || 0) + nextLocal);
      if (clampEnd !== null) {
        if (start >= clampEnd - 0.001) continue;
        end = Math.min(end, clampEnd);
      }
      if (end - start <= 0.001) continue;
      const currentText = progressiveText(normalized, start - Number(groupStart || 0) + 0.0005);
      if (!currentText) continue;
      const last = segments[segments.length - 1];
      if (last && currentText === previousText && Math.abs(last.end - start) <= 0.02) {
        last.end = end;
      } else {
        segments.push({ start, end, text: currentText });
      }
      previousText = currentText;
    }
    return segments;
  }

  function buildEvents(blocks = [], groupStart = 0, groupDuration = 1, fallbackDefaults = {}) {
    const duration = Math.max(0.05, Number(groupDuration || 1));
    const groupEnd = Number(groupStart || 0) + duration;
    return (Array.isArray(blocks) ? blocks : []).flatMap((block, index) => {
      const normalized = normalizeBlock(block, index, duration, fallbackDefaults);
      return segmentsForBlock(normalized, groupStart, groupEnd).map((segment) => ({
        ...normalized,
        block_id: normalized.id,
        start: segment.start,
        end: segment.end,
        full_text: normalized.text,
        text: segment.text,
      }));
    }).filter((event) => event.enabled !== false && String(event.text || "").trim()).sort((a, b) => a.start - b.start || a.end - b.end);
  }

  function rowHtml(block) {
    return `<div class="groupSubtitleBlockRow" data-subtitle-id="${escapeHtml(block.id)}"><label class="inlineCheck"><input type="checkbox" data-subtitle-field="enabled" ${block.enabled ? "checked" : ""} /> Показывать</label><label>Текст <textarea data-subtitle-field="text">${escapeHtml(block.text)}</textarea></label><label>Старт <input type="number" min="0" step="0.05" data-subtitle-field="start_offset_sec" value="${Number(block.start_offset_sec || 0).toFixed(2)}" /></label><label>Длительность <input type="number" min="0.05" step="0.05" data-subtitle-field="duration_sec" value="${Number(block.duration_sec || 0.5).toFixed(2)}" /></label><label>Позиция <select data-subtitle-field="position"><option value="bottom" ${block.position === "bottom" ? "selected" : ""}>снизу</option><option value="center" ${block.position === "center" ? "selected" : ""}>по центру</option><option value="top" ${block.position === "top" ? "selected" : ""}>сверху</option></select></label><label>Шрифт <input type="text" data-subtitle-field="font_family" value="${escapeHtml(block.font_family)}" /></label><label>Размер <input type="number" min="8" max="160" step="1" data-subtitle-field="font_size" value="${Number(block.font_size || 42)}" /></label><label>Макс. слов <input type="number" min="1" max="40" step="1" data-subtitle-field="max_words" value="${Number(block.max_words || 7)}" /><small class="subtitleOpacityHint">После лимита строка очищается и копит следующие слова</small></label><label>Сдвиг слов, сек <input type="number" min="-5" max="5" step="0.05" data-subtitle-field="word_offset_sec" value="${Number(block.word_offset_sec ?? 0).toFixed(2)}" /><small class="subtitleOpacityHint">− позже, 0 точно, + раньше</small></label><label>Цвет <input type="color" data-subtitle-field="color" value="${escapeHtml(block.color || "#ffffff")}" /></label><label>Фон <input type="color" data-subtitle-field="background" value="${escapeHtml(block.background || "#000000")}" /></label><label>Прозрачность фона <input type="number" min="0" max="1" step="0.05" data-subtitle-field="background_opacity" value="${Number(block.background_opacity ?? 0.45).toFixed(2)}" /><small class="subtitleOpacityHint">0 = без фона / прозрачно</small></label><label>Обводка <input type="number" min="0" max="12" step="1" data-subtitle-field="outline" value="${Number(block.outline || 0)}" /></label><button type="button" class="secondary deleteSubtitleBlockBtn">Удалить</button></div>`;
  }

  function appendRow(list, block) { list.insertAdjacentHTML("beforeend", rowHtml(block)); const row = list.lastElementChild; row.querySelector(".deleteSubtitleBlockBtn")?.addEventListener("click", () => row.remove()); return row; }

  function render(host, group, blocks = []) {
    if (!host) return;
    host.innerHTML = timelineHtml(group, blocks);
  }

  function timelineHtml(group, blocks = []) {
    return `<div class="groupSubtitleTimelineHead"><strong>Дорожка субтитров</strong><small>Субтитры видны только внутри добавленных блоков.</small></div>${laneHtml(group, blocks)}`;
  }

  function laneHtml(group, blocks = []) {
    const duration = Math.max(0.25, Number(group?.duration || 1));
    const normalized = blocks.map((block, index) => normalizeBlock(block, index, duration, group?.subtitle_defaults)).filter((block) => block.enabled);
    return `<div class="groupSubtitleTimelineLane" aria-label="Интегрированная дорожка субтитров группы">${normalized.map((block) => { const left = (block.start_offset_sec / duration) * 100; const width = Math.max(2, Math.min(100 - left, (block.duration_sec / duration) * 100)); return `<button type="button" class="groupSubtitleTimelineBlock pos-${escapeHtml(block.position)}" data-subtitle-id="${escapeHtml(block.id)}" style="left:${left}%;width:${width}%" title="${escapeHtml(block.text)}"><span>${escapeHtml(block.text || "Субтитры")}</span></button>`; }).join("") || `<div class="groupMediaTimelineEmpty compact">Нет блоков субтитров.</div>`}</div>`;
  }

  function bind(host, card) { host?.addEventListener("click", (event) => { const block = event.target.closest?.(".groupSubtitleTimelineBlock"); if (!block) return; card.querySelectorAll(".groupSubtitleBlockRow").forEach((row) => row.classList.toggle("selected", row.dataset.subtitleId === block.dataset.subtitleId)); card.querySelector(`.groupSubtitleBlockRow[data-subtitle-id='${CSS.escape(block.dataset.subtitleId)}']`)?.scrollIntoView({ block: "nearest", behavior: "smooth" }); }); }

  namespace.GroupSubtitleTimeline = { defaults, normalizeBlock, blockFromGroup, blocksFromChunks, blocksFromRows, progressiveText, progressiveBlocks, segmentsForBlock, buildEvents, appendRow, render, bind, laneHtml, timelineHtml };
})(window.XTTSStudio);
