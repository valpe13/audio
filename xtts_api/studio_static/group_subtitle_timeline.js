window.XTTSStudio = window.XTTSStudio || {};

(function registerGroupSubtitleTimeline(namespace) {
  const clamp = (value, min, max) => Math.max(min, Math.min(max, Number(value) || 0));
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"]/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[m]));
  const uuid = () => crypto.randomUUID?.() || `subtitle_${Date.now()}_${Math.random().toString(16).slice(2)}`;
  const DEFAULTS = { position: "bottom", font_family: "Arial", font_size: 42, color: "#ffffff", background: "#000000", background_opacity: 0.45, outline: 2 };

  function defaults(raw = {}) { return { ...DEFAULTS, ...(raw && typeof raw === "object" ? raw : {}) }; }

  function normalizeBlock(raw = {}, index = 0, groupDuration = 1, fallbackDefaults = {}) {
    const d = defaults(fallbackDefaults);
    const start = clamp(raw.start_offset_sec ?? raw.start ?? 0, 0, Math.max(0, groupDuration));
    const duration = clamp(raw.duration_sec ?? raw.duration ?? Math.max(0.25, groupDuration - start), 0.05, Math.max(0.05, groupDuration - start || groupDuration || 1));
    return { id: raw.id || uuid(), enabled: raw.enabled !== false, text: String(raw.text ?? ""), start_offset_sec: start, duration_sec: duration, position: ["top", "center", "bottom"].includes(raw.position) ? raw.position : d.position, font_family: String(raw.font_family || d.font_family), font_size: clamp(raw.font_size ?? d.font_size, 8, 160), color: String(raw.color || d.color), background: String(raw.background || d.background), background_opacity: clamp(raw.background_opacity ?? d.background_opacity, 0, 1), outline: clamp(raw.outline ?? d.outline, 0, 12), order: Number.isFinite(Number(raw.order)) ? Number(raw.order) : index };
  }

  function groupTextFromChunks(chunks = []) { return chunks.map((chunk) => String(chunk.text || chunk.tts_text || chunk.label || "").trim()).filter(Boolean).join(" "); }
  function blockFromGroup(group, chunks = []) { return normalizeBlock({ text: groupTextFromChunks(chunks) || group.summary || group.title || "Субтитры", start_offset_sec: 0, duration_sec: Math.max(0.25, Number(group?.duration || 1)) }, 0, Number(group?.duration || 1), group?.subtitle_defaults); }
  function blocksFromChunks(group, chunks = []) { const duration = Math.max(0.25, Number(group?.duration || 1)); return chunks.map((chunk, index) => normalizeBlock({ text: chunk.text || chunk.tts_text || chunk.label || `Чанк ${index + 1}`, start_offset_sec: chunk.local_start_sec ?? chunk.start_offset_sec ?? 0, duration_sec: chunk.duration_sec || 0.5 }, index, duration, group?.subtitle_defaults)); }

  function blocksFromRows(card, groupDuration, fallbackDefaults = {}) {
    return [...card.querySelectorAll(".groupSubtitleBlockRow")].map((row, index) => {
      const value = (field) => row.querySelector(`[data-subtitle-field='${field}']`)?.value || "";
      return normalizeBlock({ id: row.dataset.subtitleId, enabled: row.querySelector("[data-subtitle-field='enabled']")?.checked !== false, text: value("text"), start_offset_sec: value("start_offset_sec"), duration_sec: value("duration_sec"), position: value("position"), font_family: value("font_family"), font_size: value("font_size"), color: value("color"), background: value("background"), background_opacity: value("background_opacity"), outline: value("outline"), order: index }, index, groupDuration, fallbackDefaults);
    });
  }

  function rowHtml(block) {
    return `<div class="groupSubtitleBlockRow" data-subtitle-id="${escapeHtml(block.id)}"><label class="inlineCheck"><input type="checkbox" data-subtitle-field="enabled" ${block.enabled ? "checked" : ""} /> Показывать</label><label>Текст <textarea data-subtitle-field="text">${escapeHtml(block.text)}</textarea></label><label>Старт <input type="number" min="0" step="0.05" data-subtitle-field="start_offset_sec" value="${Number(block.start_offset_sec || 0).toFixed(2)}" /></label><label>Длительность <input type="number" min="0.05" step="0.05" data-subtitle-field="duration_sec" value="${Number(block.duration_sec || 0.5).toFixed(2)}" /></label><label>Позиция <select data-subtitle-field="position"><option value="bottom" ${block.position === "bottom" ? "selected" : ""}>снизу</option><option value="center" ${block.position === "center" ? "selected" : ""}>по центру</option><option value="top" ${block.position === "top" ? "selected" : ""}>сверху</option></select></label><label>Шрифт <input type="text" data-subtitle-field="font_family" value="${escapeHtml(block.font_family)}" /></label><label>Размер <input type="number" min="8" max="160" step="1" data-subtitle-field="font_size" value="${Number(block.font_size || 42)}" /></label><label>Цвет <input type="color" data-subtitle-field="color" value="${escapeHtml(block.color || "#ffffff")}" /></label><label>Фон <input type="color" data-subtitle-field="background" value="${escapeHtml(block.background || "#000000")}" /></label><label>Прозрачность фона <input type="number" min="0" max="1" step="0.05" data-subtitle-field="background_opacity" value="${Number(block.background_opacity ?? 0.45).toFixed(2)}" /></label><label>Обводка <input type="number" min="0" max="12" step="1" data-subtitle-field="outline" value="${Number(block.outline || 0)}" /></label><button type="button" class="secondary deleteSubtitleBlockBtn">Удалить</button></div>`;
  }

  function appendRow(list, block) { list.insertAdjacentHTML("beforeend", rowHtml(block)); const row = list.lastElementChild; row.querySelector(".deleteSubtitleBlockBtn")?.addEventListener("click", () => row.remove()); return row; }

  function render(host, group, blocks = []) {
    if (!host) return;
    const duration = Math.max(0.25, Number(group?.duration || 1));
    const normalized = blocks.map((block, index) => normalizeBlock(block, index, duration, group?.subtitle_defaults)).filter((block) => block.enabled);
    host.innerHTML = `<div class="groupSubtitleTimelineHead"><strong>Дорожка субтитров</strong><small>Субтитры видны только внутри добавленных блоков.</small></div><div class="groupSubtitleTimelineLane">${normalized.map((block) => { const left = (block.start_offset_sec / duration) * 100; const width = Math.max(2, Math.min(100 - left, (block.duration_sec / duration) * 100)); return `<button type="button" class="groupSubtitleTimelineBlock pos-${escapeHtml(block.position)}" data-subtitle-id="${escapeHtml(block.id)}" style="left:${left}%;width:${width}%" title="${escapeHtml(block.text)}"><span>${escapeHtml(block.text || "Субтитры")}</span></button>`; }).join("") || `<div class="groupMediaTimelineEmpty compact">Нет блоков субтитров.</div>`}</div>`;
  }

  function bind(host, card) { host?.addEventListener("click", (event) => { const block = event.target.closest?.(".groupSubtitleTimelineBlock"); if (!block) return; card.querySelectorAll(".groupSubtitleBlockRow").forEach((row) => row.classList.toggle("selected", row.dataset.subtitleId === block.dataset.subtitleId)); card.querySelector(`.groupSubtitleBlockRow[data-subtitle-id='${CSS.escape(block.dataset.subtitleId)}']`)?.scrollIntoView({ block: "nearest", behavior: "smooth" }); }); }

  namespace.GroupSubtitleTimeline = { defaults, normalizeBlock, blockFromGroup, blocksFromChunks, blocksFromRows, appendRow, render, bind };
})(window.XTTSStudio);
