(async () => {
  const match = location.pathname.match(/^\/output\/gemini\/(\d{3}\/[^/]+)\/index\.html$/);
  if (!match) return;
  const output = match[1], editors = new Map();
  let data, busy = false, pending = null;
  const panel = document.createElement('section');
  panel.innerHTML = '<h2>Edit dialogue and try new takes</h2><p>Edit a line, generate another take, listen, then select the take you prefer. Rebuild video applies your selections to a separate video. The video above keeps playing its existing version.</p><button type="button" id="review-rebuild">Rebuild video with selected takes</button><p id="review-message" role="status" aria-live="polite"></p><nav id="review-renders" aria-label="Rebuilt videos"></nav><details><summary>Processing log</summary><pre id="review-log"></pre></details>';
  document.querySelector('table').before(panel);
  const message = panel.querySelector('#review-message'), rebuild = panel.querySelector('#review-rebuild');
  const style = document.createElement('style');
  style.textContent = '.review-text{display:block;box-sizing:border-box;width:100%;min-height:85px;font:inherit;margin:8px 0}.review-takes{display:block;max-width:100%;font:inherit;margin:8px 0}.review-controls button{font:inherit;margin:6px 8px 6px 0;padding:8px}.review-preview{display:block;max-width:100%}#review-log{white-space:pre-wrap}#review-renders a{display:block;margin:8px 0}';
  document.head.append(style);
  async function api(path, body) {
    const response = await fetch(path, body ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)} : {cache:'no-store'});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Request failed');
    return result;
  }
  function chosen(row, id) {
    if (id === 'japanese') return {id,text:row.text,audio:`japanese.wav#t=${row.start_sec},${row.end_sec}`};
    return id === 'original' ? {id, text:row.text, audio:`generated/line_${String(row.idx).padStart(3,'0')}.wav`} : row.takes.find(t => t.id === id);
  }
  function enable() {
    rebuild.disabled = busy || !data?.dirty;
    for (const e of editors.values()) {
      e.regenerate.disabled = busy || e.select.value === 'japanese';
      e.text.disabled = e.select.value === 'japanese';
      const row = data.rows.find(r => r.idx === e.idx), take = chosen(row, e.select.value);
      e.use.disabled = busy || e.select.value === row.selected || e.text.value.trim() !== take.text;
      e.use.textContent = e.select.value === row.selected ? 'Selected take' : 'Use this take';
    }
  }
  function preview(e, row, id) {
    const take = chosen(row, id);
    e.select.value = id; e.text.value = take.text;
    e.audio.src = `/output/gemini/${output}/${take.audio}`;
    enable();
  }
  async function load(latestIdx = null) {
    data = await api('/api/review?output=' + encodeURIComponent(output));
    for (const row of data.rows) {
      let e = editors.get(row.idx);
      if (!e) {
        const audio = [...document.querySelectorAll('table audio')].find(a => a.getAttribute('src') === `generated/line_${String(row.idx).padStart(3,'0')}.wav`);
        if (!audio) continue;
        const tr = audio.closest('tr'), textCell = tr.children[1], controls = document.createElement('div');
        controls.className = 'review-controls';
        const label = document.createElement('label'), text = document.createElement('textarea');
        label.textContent = `Lithuanian text — line ${row.idx}`; text.className = 'review-text'; text.lang = 'lt'; label.append(text);
        if (textCell.firstChild?.nodeType === Node.TEXT_NODE) textCell.firstChild.textContent = '';
        textCell.prepend(label);
        const regenerate = document.createElement('button'); regenerate.type = 'button'; regenerate.textContent = 'Regenerate this line';
        const select = document.createElement('select'); select.className = 'review-takes'; select.setAttribute('aria-label',`Takes for line ${row.idx}`);
        const player = document.createElement('audio'); player.controls = true; player.preload = 'none'; player.className = 'review-preview'; player.setAttribute('aria-label',`Preview take for line ${row.idx}`);
        const use = document.createElement('button'); use.type = 'button';
        controls.append(regenerate,select,player,use); textCell.append(controls);
        e = {idx:row.idx,text,regenerate,select,audio:player,use}; editors.set(row.idx,e);
        text.oninput = enable;
        select.onchange = () => preview(e,data.rows.find(r => r.idx === row.idx),select.value);
        use.onclick = async () => {
          try { const result = await api('/api/review/select',{output,idx:row.idx,take:select.value}); message.textContent = result.message; await load(); }
          catch (error) { message.textContent = error.message; }
        };
        regenerate.onclick = async () => {
          busy = true; enable();
          try { const result = await api('/api/review/regenerate',{output,idx:row.idx,text:text.value}); pending = {kind:'regenerate',idx:row.idx}; message.textContent = result.message; }
          catch (error) { busy = false; message.textContent = error.message; enable(); }
        };
      }
      const current = e.select.value;
      e.select.replaceChildren();
      const original = document.createElement('option'); original.value = 'original'; original.textContent = 'Original Lithuanian take'; e.select.append(original);
      const japanese = document.createElement('option'); japanese.value = 'japanese'; japanese.textContent = 'Original Japanese'; e.select.append(japanese);
      row.takes.forEach((take,n) => { const option = document.createElement('option'); option.value = take.id; option.textContent = `Take ${n+2}${take.id === row.selected ? ' — selected' : ''}`; e.select.append(option); });
      const id = row.idx === latestIdx && row.takes.length ? row.takes.at(-1).id : (current || row.selected);
      e.select.value = id;
      if (!current || row.idx === latestIdx) preview(e,row,id);
    }
    const renders = panel.querySelector('#review-renders'); renders.replaceChildren();
    data.renders.forEach((name,n) => { const a = document.createElement('a'); a.href = `/output/gemini/${name}/index.html`; a.textContent = `Open rebuilt video ${n+1}`; renders.append(a); });
    enable();
  }
  rebuild.onclick = async () => {
    busy = true; enable();
    try { const result = await api('/api/review/rebuild',{output}); pending = {kind:'rebuild'}; message.textContent = result.message; }
    catch (error) { busy = false; message.textContent = error.message; enable(); }
  };
  async function poll() {
    try {
      const job = await api('/api/status');
      busy = job.state === 'running';
      if (pending && job.review_output === output && job.kind === pending.kind && job.state !== 'running') {
        panel.querySelector('#review-log').textContent = job.log_text || '';
        if (job.state === 'complete') {
          const idx = pending.idx; message.textContent = pending.kind === 'regenerate' ? `New take ready for line ${idx}. Listen, then choose Use this take.` : 'New video ready. Open the rebuilt video below.';
          pending = null; await load(idx);
        } else { pending = null; message.textContent = 'Processing failed. Open the processing log for details.'; }
      }
      enable();
    } catch (error) { message.textContent = 'UI connection lost. ' + error.message; }
  }
  try { await load(); await poll(); setInterval(poll,1500); }
  catch (error) { message.textContent = error.message; }
})();
