/* EPPO retail oil price dashboard - no third-party code, no innerHTML with data (XSS-safe). */
'use strict';
(function () {
  const NS = 'http://www.w3.org/2000/svg';
  const $ = (s) => document.querySelector(s);
  const TH_M = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.'];
  const RANGES = [['30', '30 วัน'], ['90', '90 วัน'], ['180', '6 เดือน'], ['365', '1 ปี'], ['ytd', 'ปีนี้'], ['all', 'ทั้งหมด']];
  const PERIODS = [['daily', 'รายวัน'], ['monthly', 'รายเดือน'], ['yearly', 'รายปี']];
  const DEFAULT = { product: 'gh95', range: '365', period: 'daily', brands: ['ptt', 'bcp', 'shell', 'caltex'], avgPer: 'monthly' };
  let D = null;
  let state = load();

  // ---------------------------------------------------------------- helpers
  function h(tag, attrs, ...kids) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k === 'class') e.className = v;
      else if (k === 'style') e.style.cssText = v;   // CSSOM - allowed by the strict CSP
      else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? '' : v);
    }
    for (const c of kids.flat()) if (c != null) e.append(c instanceof Node ? c : document.createTextNode(String(c)));
    return e;
  }
  function s(tag, attrs, parent) {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null) continue;
      if ((k === 'fill' || k === 'stroke') && String(v).startsWith('var(')) e.style[k] = v;  // CSS variables via CSSOM
      else if (k === 'style') e.style.cssText = v;   // CSSOM - allowed by the strict CSP
      else e.setAttribute(k, v);
    }
    if (parent) parent.appendChild(e);
    return e;
  }
  const f2 = (v) => (v == null || isNaN(v) ? '—' : Number(v).toFixed(2));
  const sign = (v) => (v > 0 ? '+' : v < 0 ? '−' : '±') + Math.abs(v).toFixed(2);
  const be2 = (y) => String((+y + 543) % 100).padStart(2, '0');
  const thDate = (iso) => { const [y, m, d] = iso.split('-'); return `${+d} ${TH_M[+m - 1]} ${be2(y)}`; };
  const thMonth = (ym) => { const [y, m] = ym.split('-'); return `${TH_M[+m - 1]} ${be2(y)}`; };
  const thYear = (y) => `${+y + 543}`;
  const brand = (c) => D.brands.find((b) => b.code === c);
  const product = (c) => D.products.find((p) => p.code === c);
  const color = (c) => `var(--b-${c})`;
  const dashed = (c) => c === 'susco2';
  function load() {
    try { const v = JSON.parse(localStorage.getItem('oil-dash') || 'null'); if (v && v.product) return Object.assign({}, DEFAULT, v); } catch (e) { /* storage blocked */ }
    return Object.assign({}, DEFAULT);
  }
  function save() { try { localStorage.setItem('oil-dash', JSON.stringify(state)); } catch (e) { /* ignore */ } }
  function clear(n) { while (n.firstChild) n.removeChild(n.firstChild); return n; }

  // ---------------------------------------------------------------- data access
  function ser(b, p) { return D.series[b + '|' + p] || null; }
  function val(b, p, i) {
    const x = ser(b, p); if (!x) return null;
    const k = i - x.start; return k >= 0 && k < x.v.length ? x.v[k] : null;
  }
  function range() {
    const L = D.dates.length - 1; const last = D.dates[L];
    let from;
    if (state.range === 'all') from = D.dates[0];
    else if (state.range === 'ytd') from = last.slice(0, 4) + '-01-01';
    else { const d = new Date(last + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() - (+state.range - 1)); from = d.toISOString().slice(0, 10); }
    let i0 = D.dates.findIndex((d) => d >= from); if (i0 < 0) i0 = 0;
    return [i0, L];
  }
  function brandsWithData(p) { return D.brands.filter((b) => ser(b.code, p)).map((b) => b.code); }
  function visibleBrands() {
    const avail = new Set(brandsWithData(state.product));
    return D.brands.map((b) => b.code).filter((c) => state.brands.includes(c) && avail.has(c));
  }
  /** aggregate one brand/product over [i0,i1] into daily / monthly / yearly points */
  function agg(b, p, i0, i1, period) {
    const out = new Map();
    for (let i = i0; i <= i1; i++) {
      const v = val(b, p, i); const d = D.dates[i];
      const key = period === 'daily' ? d : period === 'monthly' ? d.slice(0, 7) : d.slice(0, 4);
      if (!out.has(key)) out.set(key, { key, sum: 0, n: 0, min: Infinity, max: -Infinity });
      if (v == null) continue;
      const o = out.get(key); o.sum += v; o.n++; o.min = Math.min(o.min, v); o.max = Math.max(o.max, v);
    }
    return [...out.values()].map((o) => ({ key: o.key, v: o.n ? o.sum / o.n : null, n: o.n, min: o.min, max: o.max }));
  }
  function keysFor(i0, i1, period) {
    const set = []; let last = null;
    for (let i = i0; i <= i1; i++) {
      const d = D.dates[i]; const k = period === 'daily' ? d : period === 'monthly' ? d.slice(0, 7) : d.slice(0, 4);
      if (k !== last) { set.push(k); last = k; }
    }
    return set;
  }
  const keyLabel = (k) => (k.length === 10 ? thDate(k) : k.length === 7 ? thMonth(k) : thYear(k));

  // ---------------------------------------------------------------- tooltip
  const tip = () => $('#tip');
  function showTip(evt, title, rows) {
    const t = clear(tip());
    t.append(h('div', { class: 't' }, title));
    for (const r of rows) {
      t.append(h('div', { class: 'r' },
        h('span', { class: 'n' }, r.key ? h('i', { class: 'key' }, h('i', { class: 'ln' + (r.dash ? ' dash' : ''), style: `border-color:${r.color}` })) : null, r.name),
        h('b', {}, r.value)));
    }
    t.hidden = false;
    const pad = 14; const w = t.offsetWidth; const hh = t.offsetHeight;
    let x = evt.clientX + pad; let y = evt.clientY + pad;
    if (x + w > window.innerWidth - 8) x = evt.clientX - w - pad;
    if (y + hh > window.innerHeight - 8) y = evt.clientY - hh - pad;
    t.style.left = Math.max(8, x) + 'px'; t.style.top = Math.max(8, y) + 'px';
  }
  function hideTip() { tip().hidden = true; }

  // ---------------------------------------------------------------- scales
  function niceTicks(min, max, count) {
    if (min === max) { min -= 1; max += 1; }
    const span = max - min; const step0 = span / Math.max(1, count);
    const mag = Math.pow(10, Math.floor(Math.log10(step0)));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((st) => st >= step0) || 10 * mag;
    const lo = Math.floor(min / step) * step; const hi = Math.ceil(max / step) * step;
    const ticks = []; for (let v = lo; v <= hi + step / 2; v += step) ticks.push(+v.toFixed(6));
    return { lo, hi, ticks, step };
  }

  // ---------------------------------------------------------------- line chart
  /** opts: {keys:[x keys], series:[{code,name,color,dash,values:[]}] , step, markers, height, endLabel} */
  function lineChart(host, opts) {
    clear(host);
    const W = Math.max(300, host.clientWidth); const H = opts.height || (W < 560 ? 240 : 320);
    const m = { l: 44, r: opts.endLabel ? 52 : 14, t: 10, b: 28 };
    const vals = opts.series.flatMap((x) => x.values).filter((v) => v != null);
    if (!vals.length || !opts.keys.length) { host.append(h('div', { class: 'empty' }, opts.empty || 'ไม่มีข้อมูลในช่วงที่เลือก')); return; }
    let mn = Math.min(...vals); let mx = Math.max(...vals);
    if (opts.zero) { mn = Math.min(0, mn); mx = Math.max(0, mx); }
    const pad = (mx - mn) * 0.08 || 0.5;
    const sc = niceTicks(opts.zero && mn >= 0 ? mn : mn - pad, mx + pad, W < 560 ? 4 : 6);
    const n = opts.keys.length;
    const X = (i) => m.l + (n === 1 ? (W - m.l - m.r) / 2 : (i * (W - m.l - m.r)) / (n - 1));
    const Y = (v) => m.t + ((sc.hi - v) * (H - m.t - m.b)) / (sc.hi - sc.lo);
    const svg = s('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': opts.aria || 'กราฟเส้น' });
    const g = s('g', { class: 'grid' }, svg);
    for (const t of sc.ticks) {
      s('line', { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t) }, g);
      const tx = s('text', { x: m.l - 6, y: Y(t) + 4, 'text-anchor': 'end' }, svg); tx.textContent = t.toFixed(sc.step < 1 ? 1 : 0);
    }
    s('line', { class: 'axis', x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b }, svg);
    // x ticks
    const maxT = Math.max(2, Math.floor((W - m.l - m.r) / 78));
    let tickIdx = [];
    if (opts.keys[0].length === 10) {  // daily: first day of each month
      opts.keys.forEach((k, i) => { if (i === 0 || k.slice(8) === '01') tickIdx.push(i); });
      if (tickIdx.length > 1 && tickIdx[1] - tickIdx[0] < 12) tickIdx.shift();
    } else tickIdx = opts.keys.map((_, i) => i);
    const every = Math.ceil(tickIdx.length / maxT);
    tickIdx.filter((_, j) => j % every === 0).forEach((i) => {
      const k = opts.keys[i];
      const tx = s('text', { x: X(i), y: H - 8, 'text-anchor': 'middle' }, svg);
      tx.textContent = k.length === 10 ? thMonth(k.slice(0, 7)) : keyLabel(k);
    });
    // series
    for (const se of opts.series) {
      let d = ''; let pen = false;
      se.values.forEach((v, i) => {
        if (v == null) { pen = false; return; }
        if (!pen) { d += `M${X(i)},${Y(v)}`; pen = true; return; }
        if (opts.step) d += `H${X(i)}V${Y(v)}`; else d += `L${X(i)},${Y(v)}`;
      });
      s('path', { d, class: 'series', stroke: se.color, 'stroke-dasharray': se.dash ? '5 4' : null }, svg);
      if (opts.markers) se.values.forEach((v, i) => { if (v != null) s('circle', { cx: X(i), cy: Y(v), r: 4, fill: se.color, stroke: 'var(--surface)', 'stroke-width': 2 }, svg); });
    }
    // selective direct label: end value of the first series only
    if (opts.endLabel && opts.series.length) {
      const se = opts.series[0]; let li = se.values.length - 1; while (li >= 0 && se.values[li] == null) li--;
      if (li >= 0) {
        s('circle', { cx: X(li), cy: Y(se.values[li]), r: 4, fill: se.color, stroke: 'var(--surface)', 'stroke-width': 2 }, svg);
        const t = s('text', { x: X(li) + 8, y: Y(se.values[li]) + 4, class: 'lbl strong' }, svg); t.textContent = f2(se.values[li]);
      }
    }
    // crosshair + tooltip (pointer & keyboard)
    const xh = s('line', { class: 'xhair', y1: m.t, y2: H - m.b, visibility: 'hidden' }, svg);
    const dots = s('g', {}, svg);
    const hit = s('rect', { x: m.l, y: 0, width: W - m.l - m.r, height: H, fill: 'transparent', tabindex: 0, 'aria-label': 'เลื่อนดูค่าด้วยปุ่มลูกศร' }, svg);
    let cur = n - 1;
    function at(i, evt) {
      cur = Math.max(0, Math.min(n - 1, i));
      xh.setAttribute('x1', X(cur)); xh.setAttribute('x2', X(cur)); xh.setAttribute('visibility', 'visible');
      clear(dots);
      const rows = [];
      for (const se of opts.series) {
        const v = se.values[cur];
        if (v != null) s('circle', { cx: X(cur), cy: Y(v), r: 4, fill: se.color, stroke: 'var(--surface)', 'stroke-width': 2 }, dots);
        rows.push({ key: true, color: se.color, dash: se.dash, name: se.name, value: f2(v) + (se.extra ? se.extra(cur) : '') });
      }
      const rect = svg.getBoundingClientRect();
      const e = evt && evt.clientX != null ? evt : { clientX: rect.left + (X(cur) / W) * rect.width, clientY: rect.top + 20 };
      showTip(e, (opts.titleFor || keyLabel)(opts.keys[cur]), rows);
    }
    hit.addEventListener('pointermove', (e) => {
      const r = svg.getBoundingClientRect(); const x = ((e.clientX - r.left) / r.width) * W;
      at(Math.round(((x - m.l) / (W - m.l - m.r)) * (n - 1)), e);
    });
    hit.addEventListener('pointerleave', () => { hideTip(); xh.setAttribute('visibility', 'hidden'); clear(dots); });
    hit.addEventListener('focus', () => at(cur));
    hit.addEventListener('blur', () => { hideTip(); xh.setAttribute('visibility', 'hidden'); clear(dots); });
    hit.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowLeft') { at(cur - 1); e.preventDefault(); }
      if (e.key === 'ArrowRight') { at(cur + 1); e.preventDefault(); }
    });
    host.append(svg);
  }

  // ---------------------------------------------------------------- grouped columns (yearly)
  function columnChart(host, keys, series) {
    clear(host);
    const W = Math.max(300, host.clientWidth); const H = W < 560 ? 240 : 320;
    const m = { l: 44, r: 14, t: 18, b: 28 };
    const vals = series.flatMap((x) => x.values).filter((v) => v != null);
    if (!vals.length) { host.append(h('div', { class: 'empty' }, 'ไม่มีข้อมูลในช่วงที่เลือก')); return; }
    const sc = niceTicks(0, Math.max(...vals) * 1.05, 5);
    const Y = (v) => m.t + ((sc.hi - v) * (H - m.t - m.b)) / (sc.hi - sc.lo);
    const svg = s('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'กราฟแท่งค่าเฉลี่ยรายปี' });
    const g = s('g', { class: 'grid' }, svg);
    for (const t of sc.ticks) { s('line', { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t) }, g); const tx = s('text', { x: m.l - 6, y: Y(t) + 4, 'text-anchor': 'end' }, svg); tx.textContent = t; }
    const band = (W - m.l - m.r) / keys.length;
    const bw = Math.min(24, (band * 0.8 - 2 * (series.length - 1)) / series.length);
    const groupW = series.length * bw + (series.length - 1) * 2;
    keys.forEach((k, i) => {
      const x0 = m.l + i * band + (band - groupW) / 2;
      const tx = s('text', { x: m.l + i * band + band / 2, y: H - 8, 'text-anchor': 'middle' }, svg); tx.textContent = keyLabel(k);
      series.forEach((se, j) => {
        const v = se.values[i]; if (v == null) return;
        const x = x0 + j * (bw + 2); const y = Y(v); const hgt = Y(0) - y; const r = Math.min(4, bw / 2);
        const p = s('path', { d: `M${x},${Y(0)}V${y + r}Q${x},${y} ${x + r},${y}H${x + bw - r}Q${x + bw},${y} ${x + bw},${y + r}V${Y(0)}Z`, fill: se.color, tabindex: 0 }, svg);
        const show = (e) => showTip(e, `${keyLabel(k)} · ${se.name}`, [{ key: true, color: se.color, name: 'เฉลี่ย', value: f2(v) }]);
        p.addEventListener('pointermove', show); p.addEventListener('pointerleave', hideTip);
        p.addEventListener('focus', () => { const r2 = p.getBoundingClientRect(); show({ clientX: r2.right, clientY: r2.top }); });
        p.addEventListener('blur', hideTip);
        if (bw >= 34 && hgt > 0) { const t = s('text', { x: x + bw / 2, y: y - 4, 'text-anchor': 'middle', class: 'lbl' }, svg); t.textContent = f2(v); }
      });
    });
    s('line', { class: 'axis', x1: m.l, x2: W - m.r, y1: Y(0), y2: Y(0) }, svg);
    host.append(svg);
  }

  // ---------------------------------------------------------------- export helpers (CSV + PNG for every chart)
  const EXPORTS = {};   // cardId -> { name, rows }  (rows[0] = header)
  function setExport(id, name, rows) { EXPORTS[id] = { name, rows }; }
  function saveBlob(blob, filename) {
    const a = h('a', { href: URL.createObjectURL(blob), download: filename });
    document.body.append(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }
  function csvText(rows) {
    const esc = (v) => { v = v == null ? '' : String(v); if (/^[=+\-@]/.test(v) && isNaN(+v)) v = "'" + v; return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
    return '﻿' + rows.map((r) => r.map(esc).join(',')).join('\n');
  }
  function exportCSV(id) {
    const x = EXPORTS[id]; if (!x) return;
    saveBlob(new Blob([csvText(x.rows)], { type: 'text/csv;charset=utf-8' }), `${x.name}_${D.meta.latest_date}.csv`);
  }
  function exportPNG(id) {
    const card = document.getElementById(id); const svg = card && card.querySelector('.chart svg');
    if (!svg) return;
    const clone = svg.cloneNode(true); const src = svg.querySelectorAll('*'); const dst = clone.querySelectorAll('*');
    src.forEach((el, i) => {   // resolve CSS variables / classes into inline presentation values
      const cs = getComputedStyle(el); const t = dst[i];
      for (const p of ['fill', 'stroke', 'stroke-width', 'stroke-dasharray', 'font-size', 'font-weight', 'font-family', 'opacity']) {
        const v = cs.getPropertyValue(p); if (v) t.setAttribute(p, v);
      }
      t.removeAttribute('class'); t.removeAttribute('style');
    });
    const vb = svg.viewBox.baseVal; const scale = 2; const pad = 16; const titleH = 34;
    const legendRows = [...card.querySelectorAll('.dl-row')].map((r) => ({ c: getComputedStyle(r.querySelector('.sw')).backgroundColor, t: [...r.children].slice(1).map((x) => x.textContent) }));
    const legW = legendRows.length ? 340 : 0;
    const canvas = document.createElement('canvas'); canvas.width = (vb.width + legW + pad * 2) * scale; canvas.height = (Math.max(vb.height, legendRows.length * 26) + pad * 2 + titleH) * scale;
    const ctx = canvas.getContext('2d'); const bg = getComputedStyle(document.body).backgroundColor;
    ctx.fillStyle = getComputedStyle(card).backgroundColor || bg; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.scale(scale, scale);
    ctx.fillStyle = getComputedStyle(document.body).color; ctx.font = '600 15px "IBM Plex Sans Thai", system-ui, sans-serif';
    ctx.fillText((card.querySelector('h2') || {}).textContent || '', pad, pad + 14);
    ctx.font = '11px system-ui, sans-serif'; ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--muted');
    ctx.fillText(`ที่มา: สนพ. (EPPO) · ข้อมูล ณ ${thDate(D.meta.latest_date)}`, pad, pad + 29);
    clone.setAttribute('width', vb.width); clone.setAttribute('height', vb.height); clone.setAttribute('xmlns', NS);
    const img = new Image();
    img.onload = () => {
      ctx.drawImage(img, pad, pad + titleH, vb.width, vb.height);
      legendRows.forEach((r, i) => {   // legend next to the donut so the PNG is readable on its own
        const x = pad + vb.width + 20; const y = pad + titleH + 30 + i * 26;
        ctx.fillStyle = r.c; ctx.fillRect(x, y - 10, 12, 12);
        ctx.fillStyle = getComputedStyle(document.body).color; ctx.font = '13px system-ui, sans-serif';
        ctx.fillText(r.t[0], x + 20, y); ctx.font = '600 13px system-ui, sans-serif'; ctx.fillText(r.t[1], x + 220, y);
        ctx.font = '13px system-ui, sans-serif'; ctx.fillText(r.t[2], x + 275, y);
      });
      canvas.toBlob((b) => saveBlob(b, `${EXPORTS[id] ? EXPORTS[id].name : id}_${D.meta.latest_date}.png`)); };
    img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(new XMLSerializer().serializeToString(clone));
  }

  // ---------------------------------------------------------------- horizontal bars: latest price per brand
  function priceBars(host) {
    clear(host);
    const p = state.product; const L = D.dates.length - 1; const ref = val('ptt', p, L);
    const rows = D.brands.filter((b) => !b.stale && val(b.code, p, L) != null).map((b) => ({ b, price: val(b.code, p, L) }));
    $('#bars-hint').textContent = `${product(p).th} · ${thDate(D.dates[L])} · ตัวเลขในวงเล็บ = ต่างจาก ปตท.`;
    setExport('card-bars', `ราคาล่าสุดรายแบรนด์_${p}`, [['แบรนด์', 'ราคา (บาท/ลิตร)', 'ต่างจาก ปตท.'], ...rows.map((r) => [r.b.th, r.price, ref == null ? '' : +(r.price - ref).toFixed(2)])]);
    if (!rows.length) { host.append(h('div', { class: 'empty' }, 'ยังไม่มีข้อมูลรายแบรนด์สำหรับชนิดนี้')); return; }
    const W = Math.max(300, host.clientWidth); const rowH = 30; const m = { l: 150, r: 108, t: 6, b: 22 };
    const H = m.t + m.b + rows.length * rowH;
    const hi = Math.max(...rows.map((r) => r.price));
    const sc = niceTicks(0, hi, 4);
    const X = (v) => m.l + (v / sc.hi) * (W - m.l - m.r);
    const svg = s('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'ราคาวันล่าสุดแต่ละแบรนด์' });
    const g = s('g', { class: 'grid' }, svg);
    for (const t of sc.ticks) { s('line', { x1: X(t), x2: X(t), y1: m.t, y2: H - m.b }, g); const tx = s('text', { x: X(t), y: H - 6, 'text-anchor': 'middle' }, svg); tx.textContent = t; }
    rows.forEach((r, i) => {
      const cy = m.t + i * rowH + rowH / 2; const bh = 16; const x0 = X(0); const x1 = X(r.price); const rr = 4;
      const name = s('text', { x: 0, y: cy + 4, class: 'lbl' }, svg); name.textContent = r.b.th;
      s('path', { d: `M${x0},${cy - bh / 2}H${x1 - rr}Q${x1},${cy - bh / 2} ${x1},${cy - bh / 2 + rr}V${cy + bh / 2 - rr}Q${x1},${cy + bh / 2} ${x1 - rr},${cy + bh / 2}H${x0}Z`, fill: color(r.b.code) }, svg);
      const d = ref == null || r.b.code === 'ptt' ? '' : ` (${r.price - ref === 0 ? '±0' : sign(r.price - ref)})`;
      const lab = s('text', { x: x1 + 6, y: cy + 4, class: 'lbl strong' }, svg); lab.textContent = f2(r.price) + d;
      const hitR = s('rect', { x: 0, y: cy - rowH / 2, width: W, height: rowH, fill: 'transparent', tabindex: 0 }, svg);
      const show = (e) => showTip(e, r.b.th, [{ name: 'ราคา', value: f2(r.price) }, { name: 'ต่างจาก ปตท.', value: ref == null ? '—' : (r.price - ref === 0 ? '0.00' : sign(r.price - ref)) }]);
      hitR.addEventListener('pointermove', show); hitR.addEventListener('pointerleave', hideTip);
      hitR.addEventListener('focus', () => { const b = hitR.getBoundingClientRect(); show({ clientX: b.left + 160, clientY: b.top }); });
      hitR.addEventListener('blur', hideTip);
    });
    s('line', { class: 'axis', x1: X(0), x2: X(0), y1: m.t, y2: H - m.b }, svg);
    host.append(svg);
  }

  // ---------------------------------------------------------------- donut: price structure (PTT)
  const STRUCT_PARTS = [
    ['เนื้อน้ำมัน (ณ โรงกลั่น)', (r) => (r.ex_refinery || 0) + (r.refinery_discount || 0), 'var(--c1)'],
    ['ภาษีสรรพสามิต + เทศบาล', (r) => (r.excise_tax || 0) + (r.municipal_tax || 0), 'var(--c2)'],
    ['กองทุนน้ำมันฯ', (r) => r.oil_fund || 0, 'var(--c3)'],
    ['กองทุนอนุรักษ์ฯ', (r) => r.conservation_fund || 0, 'var(--c4)'],
    ['ค่าการตลาด', (r) => r.marketing_margin || 0, 'var(--c5)'],
    ['ภาษีมูลค่าเพิ่ม (VAT)', (r) => (r.vat_wholesale || 0) + (r.vat_marketing_margin || 0), 'var(--c6)'],
  ];
  function donutCard(host) {
    clear(host);
    const p = state.product; const r = (D.structure_latest || []).find((x) => x.product_code === p);
    if (!r || r.wholesale == null) {
      $('#donut-hint').textContent = 'ภาษี · กองทุน · ค่าการตลาด จากไฟล์โครงสร้างราคารายวันของ สนพ.';
      host.append(h('div', { class: 'empty' }, (D.structure_latest || []).length ? 'สนพ. ไม่ได้เผยแพร่โครงสร้างราคาของชนิดน้ำมันนี้ — ลองเลือก แก๊สโซฮอล์ 95 หรือ ดีเซล B7' : 'ยังไม่มีข้อมูลโครงสร้างราคา — จะแสดงหลังระบบดึงข้อมูลครั้งแรกเสร็จ'));
      setExport('card-donut', 'โครงสร้างราคา', [['ส่วนประกอบ', 'บาท/ลิตร']]);
      return;
    }
    $('#donut-hint').textContent = `${product(p).th} · ${thDate(r.date)} · ราคาขายปลีก ${f2(r.retail)} บาท/ลิตร`;
    const parts = STRUCT_PARTS.map(([label, fn, c]) => ({ label, v: +fn(r).toFixed(4), c }));
    const pos = parts.filter((x) => x.v > 0); const neg = parts.filter((x) => x.v < 0);
    const total = pos.reduce((a, x) => a + x.v, 0);
    setExport('card-donut', `โครงสร้างราคา_${p}`, [['ส่วนประกอบ', 'บาท/ลิตร', '% ของราคาขายปลีก'], ...parts.map((x) => [x.label, x.v, +(x.v / r.retail * 100).toFixed(2)]), ['ราคาขายปลีก', r.retail, 100]]);
    const S = Math.min(260, Math.max(200, host.clientWidth * 0.45)); const R = S / 2 - 4; const r0 = R * 0.6; const cx = S / 2; const cy = S / 2;
    const svg = s('svg', { viewBox: `0 0 ${S} ${S}`, role: 'img', 'aria-label': 'สัดส่วนโครงสร้างราคา', style: `max-width:${S}px` });
    let a = -Math.PI / 2; const gap = 0.012;
    for (const x of pos) {
      const span = (x.v / total) * Math.PI * 2; const a0 = a + gap / 2; const a1 = a + span - gap / 2; a += span;
      if (a1 <= a0) continue;
      const large = a1 - a0 > Math.PI ? 1 : 0;
      const P = (rad, ang) => `${cx + rad * Math.cos(ang)},${cy + rad * Math.sin(ang)}`;
      const path = s('path', { d: `M${P(R, a0)}A${R},${R} 0 ${large} 1 ${P(R, a1)}L${P(r0, a1)}A${r0},${r0} 0 ${large} 0 ${P(r0, a0)}Z`, fill: x.c, tabindex: 0 }, svg);
      const show = (e) => showTip(e, x.label, [{ name: 'บาท/ลิตร', value: f2(x.v) }, { name: 'สัดส่วน', value: (x.v / total * 100).toFixed(1) + '%' }]);
      path.addEventListener('pointermove', show); path.addEventListener('pointerleave', hideTip);
      path.addEventListener('focus', () => { const b = path.getBoundingClientRect(); show({ clientX: b.right, clientY: b.top }); }); path.addEventListener('blur', hideTip);
    }
    const t1 = s('text', { x: cx, y: cy - 2, 'text-anchor': 'middle', class: 'lbl strong', style: 'font-size:20px' }, svg); t1.textContent = f2(r.retail);
    const t2 = s('text', { x: cx, y: cy + 16, 'text-anchor': 'middle', class: 'lbl' }, svg); t2.textContent = 'บาท/ลิตร';
    const legend = h('div', { class: 'donut-legend' });
    for (const x of parts) {
      legend.append(h('div', { class: 'dl-row' + (x.v < 0 ? ' neg' : '') }, h('i', { class: 'sw', style: `background:${x.c}` }), h('span', { class: 'n' }, x.label),
        h('b', {}, f2(x.v)), h('span', { class: 'pc' }, x.v > 0 ? (x.v / total * 100).toFixed(1) + '%' : 'ชดเชย')));
    }
    const wrap = h('div', { class: 'donut-wrap' }); wrap.append(h('div', { class: 'chart' }, svg), legend);
    host.append(wrap);
    if (neg.length) host.append(h('p', { class: 'hint' }, `ส่วนที่ติดลบ (${neg.map((x) => x.label + ' ' + f2(x.v)).join(', ')}) คือเงินที่กองทุนชดเชยให้ผู้ใช้ จึงไม่อยู่ในวงกลม — ยอดในวงกลม ${f2(total)} หักส่วนชดเชยแล้วเท่ากับราคาขายปลีก`));
  }

  // ---------------------------------------------------------------- vertical bars: monthly / yearly averages
  function avgBars() {
    const p = state.product; const [i0, i1] = range(); const per = state.avgPer || 'monthly';
    const codes = visibleBrands(); let keys = keysFor(i0, i1, per); if (per === 'monthly') keys = keys.slice(-12);
    const series = codes.map((c) => { const mp = new Map(agg(c, p, i0, i1, per).map((x) => [x.key, x])); return { code: c, name: brand(c).th, color: color(c), values: keys.map((k) => (mp.get(k) && mp.get(k).n ? mp.get(k).v : null)) }; })
      .filter((x) => x.values.some((v) => v != null));
    $('#avg-title').textContent = `กราฟแท่ง: ราคาเฉลี่ย${per === 'yearly' ? 'รายปี' : 'รายเดือน (12 เดือนล่าสุดในช่วงที่เลือก)'}`;
    const lg = clear($('#avg-legend')); if (series.length >= 2) for (const se of series) lg.append(h('span', { class: 'key' }, h('i', { class: 'sw', style: `background:${se.color}` }), se.name));
    const seg = clear($('#avg-per')); for (const [v, label] of [['monthly', 'รายเดือน'], ['yearly', 'รายปี']]) seg.append(h('button', { type: 'button', 'aria-pressed': String(per === v), onclick: () => { state.avgPer = v; save(); avgBars(); } }, label));
    setExport('card-avg', `ราคาเฉลี่ย_${per}_${p}`, [[per === 'yearly' ? 'ปี' : 'เดือน', ...series.map((x) => x.name)], ...keys.map((k, i) => [k, ...series.map((x) => (x.values[i] == null ? '' : +x.values[i].toFixed(3)))])]);
    columnChart($('#avg'), keys, series);
  }

  // ---------------------------------------------------------------- data coverage per brand
  function coverage() {
    const rows = D.brands.map((b) => {
      const cv = (D.coverage || {})[b.code] || {};
      const since = cv.first_real ? thDate(cv.first_real) : '—';
      const note = b.stale ? `สนพ. ยังแสดงราคาเก่า (มีผล ${b.stale_since}) จึงไม่นำมาใช้` : cv.history_source ? cv.history_source
        : b.code === 'bcp' ? 'สนพ. ไม่มีราคาย้อนหลังรายแบรนด์ — นำเข้าประวัติจากหน้า "ราคาน้ำมันย้อนหลัง" ของบางจากเองได้ (ไฟล์ data/manual/bcp_history.csv)'
        : 'สนพ. ไม่มีราคาย้อนหลังรายแบรนด์ — เริ่มเก็บทุกวันตั้งแต่ติดตั้งระบบ';
      return [h('td', {}, h('i', { class: 'dot', style: `background:${color(b.code)}` }), b.th), since, cv.days != null ? String(cv.days) : '0', note];
    });
    clear($('#coverage')).append(table(['แบรนด์', 'มีข้อมูลตั้งแต่', 'จำนวนวันที่มีข้อมูลจริง', 'หมายเหตุ'], rows, (i) => (D.brands[i].stale ? 'stale' : null)));
    setExport('card-coverage', 'ความครอบคลุมข้อมูล', [['แบรนด์', 'มีข้อมูลตั้งแต่', 'จำนวนวัน'], ...D.brands.map((b) => [b.th, ((D.coverage || {})[b.code] || {}).first_real || '', ((D.coverage || {})[b.code] || {}).days || 0])]);
  }

  // ---------------------------------------------------------------- KPIs
  function kpis() {
    const host = clear($('#kpis')); const p = state.product; const [i0, i1] = range();
    const ref = ser('ptt', p) ? 'ptt' : (brandsWithData(p)[0] || null);
    if (!ref) { host.append(h('div', { class: 'empty' }, 'ไม่มีข้อมูล')); return; }
    const refName = brand(ref).th;
    let li = i1; while (li >= i0 && val(ref, p, li) == null) li--;
    const last = val(ref, p, li); const back = val(ref, p, Math.max(0, li - 30));
    const pts = []; for (let i = i0; i <= i1; i++) { const v = val(ref, p, i); if (v != null) pts.push([i, v]); }
    const avg = pts.reduce((a, x) => a + x[1], 0) / (pts.length || 1);
    const mx = pts.reduce((a, x) => (x[1] > a[1] ? x : a), [0, -Infinity]);
    const mn = pts.reduce((a, x) => (x[1] < a[1] ? x : a), [0, Infinity]);
    let up = 0; let down = 0; for (let k = 1; k < pts.length; k++) { const d = pts[k][1] - pts[k - 1][1]; if (d > 0) up++; else if (d < 0) down++; }
    const tile = (label, value, delta, cls) => h('div', { class: 'kpi' }, h('div', { class: 'label' }, label),
      h('div', { class: 'value' }, value, h('small', {}, 'บาท/ลิตร')), delta ? h('div', { class: 'delta ' + (cls || '') }, delta) : null);
    const d30 = last != null && back != null ? last - back : null;
    host.append(
      tile(`ราคาล่าสุด ${refName}`, f2(last), d30 == null ? null : (d30 === 0 ? 'ไม่เปลี่ยนจาก 30 วันก่อน' : `${d30 > 0 ? '▲' : '▼'} ${Math.abs(d30).toFixed(2)} จาก 30 วันก่อน`), d30 > 0 ? 'up' : d30 < 0 ? 'down' : ''),
      tile('เฉลี่ยช่วงที่เลือก', f2(avg), `${refName} · ${pts.length} วัน`),
      tile('สูงสุดในช่วง', f2(mx[1]), pts.length ? thDate(D.dates[mx[0]]) : null),
      tile('ต่ำสุดในช่วง', f2(mn[1]), pts.length ? thDate(D.dates[mn[0]]) : null),
      h('div', { class: 'kpi' }, h('div', { class: 'label' }, 'ปรับราคาในช่วง'), h('div', { class: 'value' }, String(up + down), h('small', {}, 'ครั้ง')),
        h('div', { class: 'delta' }, h('span', { class: 'up' }, `▲ ขึ้น ${up}`), ' · ', h('span', { class: 'down' }, `▼ ลง ${down}`))));
  }

  // ---------------------------------------------------------------- trend
  function trend() {
    const p = state.product; const [i0, i1] = range(); const period = state.period;
    const codes = visibleBrands();
    const keys = keysFor(i0, i1, period);
    const series = codes.map((c) => {
      const pts = agg(c, p, i0, i1, period); const map = new Map(pts.map((x) => [x.key, x]));
      return { code: c, name: brand(c).th, color: color(c), dash: dashed(c), values: keys.map((k) => (map.get(k) || {}).v ?? null) };
    }).filter((x) => x.values.some((v) => v != null));
    $('#trend-title').textContent = `แนวโน้มราคา ${product(p).th} (${PERIODS.find((x) => x[0] === period)[1]})`;
    $('#trend-hint').textContent = period === 'daily' ? 'ราคาที่มีผลในแต่ละวัน · เส้นขั้นบันได = วันที่ปรับราคา'
      : 'ค่าเฉลี่ยของราคาทุกวันในเดือน/ปี (ถ่วงตามจำนวนวันที่ราคานั้นมีผล)';
    const lg = clear($('#trend-legend'));
    if (series.length >= 2) for (const se of series) lg.append(h('span', { class: 'key' }, h('i', { class: 'ln' + (se.dash ? ' dash' : ''), style: `border-color:${se.color}` }), se.name));
    setExport('card-trend', `แนวโน้มราคา_${p}_${period}`, [[period === 'daily' ? 'วันที่' : period === 'monthly' ? 'เดือน' : 'ปี', ...series.map((x) => x.name)],
      ...keys.map((k, i) => [k, ...series.map((x) => (x.values[i] == null ? '' : +x.values[i].toFixed(3)))])]);
    const host = $('#trend');
    if (period === 'yearly') columnChart(host, keys, series);
    else lineChart(host, { keys, series, step: period === 'daily', markers: period === 'monthly' && keys.length <= 24, endLabel: true, aria: 'กราฟแนวโน้มราคา' });
  }

  // ---------------------------------------------------------------- tables
  function table(head, rows, rowClass) {
    return h('table', {}, h('thead', {}, h('tr', {}, head.map((x) => h('th', { scope: 'col' }, x)))),
      h('tbody', {}, rows.map((r, i) => h('tr', { class: rowClass ? rowClass(i) : null }, r.map((c) => (c instanceof Node && c.tagName === 'TD' ? c : h('td', {}, c)))))));
  }
  function matrix() {
    const L = D.dates.length - 1;
    const prods = D.products.filter((p) => D.brands.some((b) => val(b.code, p.code, L) != null));
    const min = {}; for (const p of prods) min[p.code] = Math.min(...D.brands.map((b) => val(b.code, p.code, L)).filter((v) => v != null));
    const rows = D.brands.map((b) => {
      const name = h('td', {}, h('i', { class: 'dot', style: `background:${color(b.code)}` }), b.th,
        b.stale ? h('span', { class: 'hint' }, ` (สนพ. ยังแสดงราคาเก่าตั้งแต่ ${b.stale_since})`) : null);
      return [name, ...prods.map((p) => { const v = val(b.code, p.code, L); return h('td', { class: v != null && v === min[p.code] ? 'min' : null }, f2(v)); })];
    });
    clear($('#matrix')).append(table(['แบรนด์', ...prods.map((p) => p.th)], rows, (i) => (D.brands[i].stale ? 'stale' : null)));
    setExport('card-matrix', 'ราคาล่าสุดทุกแบรนด์', [['แบรนด์', ...prods.map((p) => p.th)], ...D.brands.filter((b) => !b.stale).map((b) => [b.th, ...prods.map((p) => val(b.code, p.code, L) ?? '')])]);
  }
  let pivotData = null;
  function pivot() {
    const p = state.product; const [i0, i1] = range(); const period = state.period === 'yearly' ? 'yearly' : 'monthly';
    const codes = brandsWithData(p); const keys = keysFor(i0, i1, period).reverse();
    const m = {}; const nd = {}; const full = {};
    for (const c of codes) for (const x of agg(c, p, i0, i1, period)) { m[c + x.key] = x.v; nd[c + x.key] = x.n; full[x.key] = Math.max(full[x.key] || 0, x.n); }
    const cell = (c, k) => (m[c + k] == null ? '—' : f2(m[c + k]) + (nd[c + k] < full[k] ? ` *${nd[c + k]}ว.` : ''));
    $('#pivot-title').textContent = `Pivot ค่าเฉลี่ย${period === 'yearly' ? 'รายปี' : 'รายเดือน'} · ${product(p).th}`;
    const head = [period === 'yearly' ? 'ปี' : 'เดือน', ...codes.map((c) => brand(c).th)];
    const rows = keys.map((k) => [keyLabel(k), ...codes.map((c) => cell(c, k))]);
    pivotData = [[period === 'yearly' ? 'year' : 'month', ...codes.map((c) => brand(c).th)], ...keys.map((k) => [k, ...codes.map((c) => (m[c + k] == null ? '' : m[c + k].toFixed(3)))])];
    clear($('#pivot')).append(table(head, rows));
    setExport('card-pivot', `pivot_${p}_${period}`, pivotData);
  }
  function changes() {
    const p = state.product; const [i0] = range(); const from = D.dates[i0];
    const list = (D.changes || []).filter((c) => c.product_code === p && c.date >= from);
    $('#changes-hint').textContent = `${product(p).th} · ${list.length} ครั้งในช่วงที่เลือก (ทุกแบรนด์)`;
    const rows = list.slice(0, 300).map((c) => [thDate(c.date),
      h('td', {}, h('i', { class: 'dot', style: `background:${color(c.brand_code)}` }), (brand(c.brand_code) || { th: c.brand_code }).th),
      f2(c.prev_price), f2(c.price), h('td', { class: c.change > 0 ? 'up' : 'down' }, `${c.change > 0 ? '▲' : '▼'} ${Math.abs(c.change).toFixed(2)}`)]);
    setExport('card-changes', `ประวัติปรับราคา_${p}`, [['วันที่', 'แบรนด์', 'ราคาเดิม', 'ราคาใหม่', 'เปลี่ยนแปลง'], ...list.map((c) => [c.date, (brand(c.brand_code) || { th: c.brand_code }).th, c.prev_price, c.price, c.change])]);
    const host = clear($('#changes'));
    if (!rows.length) host.append(h('div', { class: 'empty' }, 'ไม่มีการปรับราคาในช่วงที่เลือก'));
    else host.append(table(['วันที่', 'แบรนด์', 'ราคาเดิม', 'ราคาใหม่', 'เปลี่ยนแปลง'], rows));
  }
  function notes() {
    const host = clear($('#notes')); const mt = D.meta;
    host.append(h('p', {}, `ที่มา: ${mt.source}. ราคาขายปลีกมาตรฐานในเขต กทม. นนทบุรี ปทุมธานี สมุทรปราการ (ยังไม่รวมภาษีบำรุงท้องถิ่น).`),
      h('p', {}, `ข้อมูลรายแบรนด์เริ่มเก็บอัตโนมัติตั้งแต่ ${mt.per_brand_since ? thDate(mt.per_brand_since) : '—'}; ข้อมูลก่อนหน้านั้นเป็นราคา ปตท. จากไฟล์ "โครงสร้างราคาน้ำมัน" รายวันของ สนพ. (ราคาของผู้ค้าที่มีส่วนแบ่งตลาดสูงสุด) โดยวันหยุดใช้ราคาล่าสุดต่อ.`),
      h('p', {}, 'สนพ. เก็บปุ่มดาวน์โหลดย้อนหลังรายแบรนด์ไว้ถึงเดือนกรกฎาคม 2561 เท่านั้น จึงไม่สามารถย้อนหลังรายแบรนด์ปี 2568 ได้.'));
    for (const w of mt.warnings || []) host.append(h('p', {}, '⚠ ' + w));
  }

  // ---------------------------------------------------------------- controls
  function controls() {
    const sel = clear($('#f-product'));
    for (const p of D.products) if (brandsWithData(p.code).length) sel.append(h('option', { value: p.code, selected: p.code === state.product }, p.th));
    sel.onchange = () => { state.product = sel.value; save(); render(); };
    const seg = (host, items, key) => {
      clear(host);
      for (const [v, label] of items) host.append(h('button', { type: 'button', 'aria-pressed': String(state[key] === v), onclick: () => { state[key] = v; save(); render(); } }, label));
    };
    seg($('#f-range'), RANGES, 'range'); seg($('#f-period'), PERIODS, 'period');
    const chips = clear($('#f-brands')); const avail = new Set(brandsWithData(state.product));
    for (const b of D.brands) {
      const on = state.brands.includes(b.code);
      chips.append(h('button', { type: 'button', class: 'chip', 'aria-pressed': String(on), disabled: !avail.has(b.code),
        title: b.stale ? `สนพ. ยังแสดงราคาเก่า (ตั้งแต่ ${b.stale_since})` : (!avail.has(b.code) ? 'ไม่มีข้อมูลชนิดน้ำมันนี้' : b.en),
        onclick: () => { state.brands = on ? state.brands.filter((x) => x !== b.code) : [...state.brands, b.code]; save(); render(); } },
      h('i', { class: 'dot', style: `background:${color(b.code)}` }), b.th));
    }
    const [i0] = range(); const nb = $('#notice');
    const since = D.meta.per_brand_since;
    if (since && D.dates[i0] < since) {
      nb.hidden = false;
      nb.textContent = `ข้อมูลรายแบรนด์เริ่มเก็บตั้งแต่ ${thDate(since)} · ก่อนหน้านั้นกราฟแสดงเฉพาะ ปตท. (อ้างอิงโครงสร้างราคาน้ำมันของ สนพ.)`;
    } else nb.hidden = true;
  }

  function render() {
    if (!product(state.product) || !brandsWithData(state.product).length) state.product = 'gh95';
    controls(); kpis(); trend(); priceBars($('#bars')); donutCard($('#donut')); avgBars(); coverage(); matrix(); pivot(); changes();
  }

  function init() {
    $('#asof').textContent = thDate(D.meta.latest_date);
    $('#generated').textContent = D.meta.generated_at.replace('T', ' ').slice(0, 16);
    notes(); render();
    document.addEventListener('click', (e) => {
      const b = e.target.closest('[data-csv],[data-png]'); if (!b) return;
      if (b.dataset.csv) exportCSV(b.dataset.csv); else exportPNG(b.dataset.png);
    });
    let t; window.addEventListener('resize', () => { clearTimeout(t); t = setTimeout(render, 150); });
  }

  // theme toggle (remembered per browser)
  try { const th = localStorage.getItem('oil-theme'); if (th) document.documentElement.dataset.theme = th; } catch (e) { /* ignore */ }
  document.addEventListener('DOMContentLoaded', () => {
    $('#theme').addEventListener('click', () => {
      const dark = document.documentElement.dataset.theme ? document.documentElement.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
      document.documentElement.dataset.theme = dark ? 'light' : 'dark';
      try { localStorage.setItem('oil-theme', document.documentElement.dataset.theme); } catch (e) { /* ignore */ }
    });
    const src = window.__DASHBOARD_DATA__;   // (used only by the offline preview build)
    (src ? Promise.resolve(src) : fetch('data/dashboard.json', { cache: 'no-cache' }).then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); }))
      .then((j) => { D = j; init(); })
      .catch((e) => { clear($('#kpis')).append(h('div', { class: 'empty' }, 'โหลดข้อมูลไม่สำเร็จ: ' + e.message)); });
  });
})();
