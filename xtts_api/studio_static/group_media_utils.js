window.XTTSStudio = window.XTTSStudio || {};

(function registerGroupMediaUtils(namespace) {
  const clamp = (value, min, max) => Math.max(min, Math.min(max, Number(value) || 0));

  function scheduledItems(items) {
    return (Array.isArray(items) ? items : []).filter((item) => item?.scheduled !== false);
  }

  function itemEnd(item) {
    return Number(item?.start_offset_sec || 0) + Math.max(0, Number(item?.duration_sec || item?.visual_duration_sec || 0));
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

  namespace.GroupMediaUtils = { scheduledItems, freeIntervals, bestFreeInterval };
})(window.XTTSStudio);
