/* Isolated synthetic presentation study. No application or Brain API calls. */
const KEY = 'yggdress-open-air-study-v1';
const $ = (selector) => document.querySelector(selector);
const all = (selector) => [...document.querySelectorAll(selector)];
const seedNotes = [
  { id: 'slower', title: 'A slower kind of productivity', body: 'Leave room between the things that matter. A full calendar is not the same as a good day.\n\nTry keeping one clear intention for the morning, and enough space to notice what changes.', area: 'Personal', when: 'Updated yesterday', links: ['reading'] },
  { id: 'reading', title: 'What I want to learn next', body: 'Keep a short reading list. After each chapter, capture one idea in my own words.\n\nReturn to those ideas at the end of the week and see what connects.', area: 'Learning', when: 'Updated yesterday', links: ['slower'] },
  { id: 'outside', title: 'The long way home', body: 'The path around the lake takes a little longer. Leave the phone in a pocket and notice one thing that is different from yesterday.', area: 'Health', when: 'Added this week', links: [] },
];
const scenes = {
  morning: { asset: 'autumn-sunrise-clear', weather: '12° · Morning light', place: 'An alpine morning', greeting: 'Good morning, Alex. You have room to make today your own.' },
  afternoon: { asset: 'summer-afternoon-clear', weather: '18° · Clear skies', place: 'An alpine afternoon', greeting: 'Good afternoon, Alex. You have room to make today your own.' },
  night: { asset: 'summer-night-clear', weather: '9° · A clear night', place: 'An alpine evening', greeting: 'Good evening, Alex. A little room to bring the day to a close.' },
};
const initial = () => ({ version: 1, notes: seedNotes, tasks: { desk: true, chapter: false, outside: false }, routine: 0, scene: 'afternoon', reduced: false, quiet: false, activity: [] });
let state = initial();
let storageIssue = false;
try {
  const saved = JSON.parse(localStorage.getItem(KEY) || 'null');
  if (saved && saved.version === 1 && Array.isArray(saved.notes) && saved.notes.length <= 100 && saved.notes.every(n => n && typeof n.id === 'string' && typeof n.title === 'string' && n.title.length <= 160 && typeof n.body === 'string' && n.body.length <= 5000 && ['Work','Learning','Health','Personal'].includes(n.area) && typeof n.when === 'string' && Array.isArray(n.links) && n.links.every(l => typeof l === 'string'))) {
    state = { ...initial(), notes: saved.notes, tasks: Object.fromEntries(['desk','chapter','outside'].map(k => [k, typeof saved.tasks?.[k] === 'boolean' ? saved.tasks[k] : initial().tasks[k]])), routine: [0,10,40,70,90,100].includes(saved.routine) ? saved.routine : 0, scene: scenes[saved.scene] ? saved.scene : 'afternoon', reduced: saved.reduced === true, quiet: saved.quiet === true, activity: Array.isArray(saved.activity) ? saved.activity.filter(a => typeof a?.title === 'string' && typeof a?.when === 'string').slice(0,3) : [] };
  } else if (saved) storageIssue = true;
} catch { storageIssue = true; }
function persist(next) {
  localStorage.setItem(KEY, JSON.stringify(next));
  state = next;
}
let noticeTimer;
function notify(message) {
  $('#status').textContent = message;
  $('#status').classList.add('visible');
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => $('#status').classList.remove('visible'), 4200);
}
function icon(name) { const node = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); const use = document.createElementNS(node.namespaceURI, 'use'); use.setAttribute('href', '#' + name); node.append(use); node.setAttribute('aria-hidden','true'); return node; }
function openDialog(id) { const dialog = $(id); if (!dialog.open) dialog.showModal(); }
all('.close').forEach(button => button.addEventListener('click', () => button.closest('dialog').close()));
function showDetail(title, body) { $('#detail-title').textContent = title; $('#detail-body').textContent = body; openDialog('#detail-dialog'); }
const details = {
  Calendar: 'Your calendar will keep the same quiet visual language. This study only demonstrates Today; the real calendar and its data have not been changed.',
  Tasks: 'Three synthetic focus tasks appear on Today. Completing one here only updates this study in this browser.',
  Graph: 'The existing Brain graph remains unchanged. This study does not substitute a fictional graph for your real one.',
  Work: 'Design the reading corner. A small fictional project used to check how working life fits into this visual direction.',
  Learning: 'German practice, reading, and a few ideas to return to. Fictional content for this design study.',
  Health: 'A walk before sunset and a little space away from the screen. Fictional content for this design study.',
  Personal: 'A place for the thoughts that do not need to become a project. Fictional content for this design study.',
  'Daily planning': 'Weekly planning is outside this focused Today study. The existing application has not been restyled yet.',
  'Design the reading corner': '09:00–10:30 · Work\n\nSketch a comfortable place to read. Keep the morning focused on one useful decision. This is a synthetic agenda item.',
  'German practice': '16:00–16:45 · Learning\n\nReview the last lesson and try a short conversation. This is a synthetic agenda item.',
  'Evening walk': '18:00–18:30 · Health\n\nTake the path around the lake. This is a synthetic agenda item.',
};
all('[data-detail]').forEach(button => button.addEventListener('click', () => showDetail(button.dataset.detail, details[button.dataset.detail])));
function openNote(id) {
  const note = state.notes.find(n => n.id === id); if (!note) return;
  if ($('#search-dialog').open) $('#search-dialog').close();
  $('#note-title').textContent = note.title; $('#note-body').textContent = note.body || 'A thought with room to grow.'; $('#note-area').textContent = note.area + ' / DEMO NOTE';
  const links = $('#note-links'); links.replaceChildren();
  const linked = note.links.map(id => state.notes.find(n => n.id === id)).filter(Boolean);
  if (linked.length) { const label = document.createElement('p'); label.textContent = 'RELATED DEMO THOUGHTS'; links.append(label); linked.forEach(n => { const b = document.createElement('button'); b.textContent = n.title + ' ↗'; b.addEventListener('click', () => openNote(n.id)); links.append(b); }); }
  openDialog('#note-dialog');
}
function noteRow(note) {
  const b = document.createElement('button'); b.className = 'note-row'; b.append(icon('note'));
  const span = document.createElement('span'), title = document.createElement('strong'), meta = document.createElement('small'), arrow = document.createElement('i');
  title.textContent = note.title; meta.textContent = note.area + ' · ' + note.when; arrow.textContent = '↗'; span.append(title,meta); b.append(span,arrow); b.addEventListener('click', () => openNote(note.id)); return b;
}
function renderNotes() { $('#recent-notes').replaceChildren(...state.notes.slice(0,2).map(noteRow)); $('#note-count').textContent = String(state.notes.length); }
const defaultActivity = [{ title: 'Kept an idea from yesterday’s reading', when: 'Yesterday · Learning' }, { title: 'Made room for focused work', when: 'This morning · Work' }, { title: 'Went the long way home', when: 'Yesterday · Health' }];
function renderActivity() { $('#activity-list').replaceChildren(...[...state.activity,...defaultActivity].slice(0,3).map(item => { const row = document.createElement('div'); row.className = 'activity-item'; const p = document.createElement('p'), s = document.createElement('small'); p.textContent = item.title; s.textContent = item.when; p.append(s); row.append(icon('leaf'),p); return row; })); }
function renderFocus() { all('[data-task]').forEach(input => input.checked = state.tasks[input.dataset.task]); $('#focus-count').textContent = Object.values(state.tasks).filter(Boolean).length + ' / 3'; }
all('[data-task]').forEach(input => input.addEventListener('change', () => { try { persist({ ...state, tasks: { ...state.tasks, [input.dataset.task]: input.checked } }); renderFocus(); } catch { renderFocus(); notify('Could not keep this change. Browser storage is unavailable.'); } }));
function renderRoutine() {
  $('.progress').setAttribute('aria-valuenow', state.routine); $('.progress i').style.transform = 'scaleX(' + state.routine / 100 + ')';
  $('.routine-actions').hidden = state.routine === 0 || state.routine === 100;
  $('#routine-start').hidden = state.routine > 0 && state.routine < 100;
  $('#routine-start').replaceChildren(document.createTextNode(state.routine === 100 ? 'Start again ' : 'Start ritual '), icon('arrow'));
  $('#routine-status').textContent = state.routine === 0 ? 'Ready when you are.' : state.routine === 100 ? 'A chapter, a new perspective.' : 'In progress · ' + state.routine + '%';
}
function setRoutine(value) { try { persist({ ...state, routine: value }); renderRoutine(); if (value === 100) notify('Ritual complete. Kept in this study.'); } catch { notify('Could not keep progress. Browser storage is unavailable.'); } }
$('#routine-start').addEventListener('click', () => setRoutine(10));
$('#routine-progress').addEventListener('click', () => setRoutine(Math.min(90, state.routine + 30)));
$('#routine-complete').addEventListener('click', () => setRoutine(100));
function renderSearch() {
  const q = $('#search-field').value.trim().toLowerCase();
  const matches = state.notes.filter(n => (n.title + ' ' + n.body + ' ' + n.area).toLowerCase().includes(q));
  const container = $('#search-results'); container.replaceChildren();
  const count = document.createElement('p'); count.className = 'result-count'; count.textContent = matches.length + (matches.length === 1 ? ' thought' : ' thoughts'); container.append(count);
  if (!matches.length) { const p = document.createElement('p'); p.className = 'empty'; p.textContent = 'No thoughts match yet. Try another word, or capture something new.'; container.append(p); } else container.append(...matches.map(noteRow));
}
function openSearch() { $('#search-field').value = ''; renderSearch(); openDialog('#search-dialog'); $('#search-field').focus(); }
['#search-open','#notes-all','#notes-view'].forEach(id => $(id).addEventListener('click', openSearch));
$('#search-field').addEventListener('input', renderSearch);
$('#search-dialog').addEventListener('keydown', event => { const results = all('#search-results button'); if (!results.length) return; const i = results.indexOf(document.activeElement); if (event.key === 'ArrowDown') { event.preventDefault(); results[(i + 1) % results.length].focus(); } else if (event.key === 'ArrowUp') { event.preventDefault(); results[i <= 0 ? results.length - 1 : i - 1].focus(); } });
function openCapture() { $('#capture-error').textContent = ''; openDialog('#capture-dialog'); $('#capture-title').focus(); }
['#capture-open','#capture-top'].forEach(id => $(id).addEventListener('click', openCapture));
$('#capture-form').addEventListener('submit', async event => {
  event.preventDefault(); const title = $('#capture-title').value.trim();
  if (!title) { $('#capture-error').textContent = 'Give this thought a title first.'; $('#capture-title').focus(); return; }
  if (state.notes.length >= 100) { $('#capture-error').textContent = 'This small study holds up to 100 thoughts. Your text has been kept in the form.'; return; }
  const submit = $('#capture-form [type=submit]'); submit.disabled = true;
  try {
    await Promise.resolve();
    const note = { id: crypto.randomUUID(), title, body: $('#capture-body').value.trim(), area: $('#capture-area').value, when: 'Just captured', links: [] };
    persist({ ...state, notes: [note,...state.notes], activity: [{ title: 'Kept “' + title + '”', when: 'Just now · ' + note.area }, ...state.activity].slice(0,3) });
    renderNotes(); renderActivity(); $('#capture-dialog').close(); $('#capture-form').reset(); notify('Thought kept in this browser’s study.');
  } catch { $('#capture-error').textContent = 'Could not save in this browser. Your text is still here; try again when storage is available.'; }
  finally { submit.disabled = false; }
});
$('#lia-open').addEventListener('click', () => showDetail('A little perspective', 'Demo insight · no model call\n\n“A slower kind of productivity” and “What I want to learn next” both leave room for reflection instead of filling every hour.\n\nThis is a written example of an insight, not a live discovery about your Brain.'));
function renderPreferences() { document.body.dataset.reduced = String(state.reduced); document.body.dataset.quiet = String(state.quiet); $('#reduce-transparency').checked = state.reduced; $('#reduce-motion').checked = state.quiet; }
[['#reduce-transparency','reduced'],['#reduce-motion','quiet']].forEach(([id,key]) => $(id).addEventListener('change', () => { try { persist({ ...state, [key]: $(id).checked }); renderPreferences(); $('#appearance-error').textContent = ''; } catch { renderPreferences(); $('#appearance-error').textContent = 'Could not keep this preference. Browser storage is unavailable.'; } }));
['#appearance-open','#appearance-mobile','#scene-open'].forEach(id => $(id).addEventListener('click', () => openDialog('#appearance-dialog')));
const assetPath = (scene, size) => '../../scenes/' + scenes[scene].asset + '-' + size + '.webp';
function sceneText(scene) { $('#weather-label').textContent = scenes[scene].weather; $('.scene-place').textContent = scenes[scene].place; $('.welcome-caption').textContent = scenes[scene].greeting; $('#scene-name').textContent = scene[0].toUpperCase() + scene.slice(1); all('[data-scene]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.scene === scene))); document.body.style.setProperty('--moment-image', 'url("' + assetPath(scene,1920) + '")'); }
let sceneRequest = 0;
async function setScene(scene) {
  const request = ++sceneRequest; const image = new Image(); image.src = assetPath(scene, innerWidth < 700 ? 960 : 1920);
  try {
    await image.decode(); if (request !== sceneRequest) return;
    persist({ ...state, scene });
    const front = $('#scene-front'), back = $('#scene-back');
    back.style.transition = 'none'; back.style.opacity = '0'; back.src = image.src; back.getBoundingClientRect();
    back.style.transition = ''; back.style.opacity = '1'; sceneText(scene); $('#appearance-error').textContent = '';
    setTimeout(() => { if (request !== sceneRequest) return; front.removeAttribute('srcset'); front.src = image.src; back.style.transition = 'none'; back.style.opacity = '0'; }, state.quiet || matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 2050);
  } catch { if (request !== sceneRequest) return; $('#appearance-error').textContent = 'This scene could not load or be kept. The previous scene is still selected.'; notify('The previous scene is still selected. Try again when the scene is available.'); }
}
all('[data-scene]').forEach(button => button.addEventListener('click', () => setScene(button.dataset.scene)));
$('#scene-front').addEventListener('error', () => { notify('The landscape is unavailable. Your workspace is still readable.'); });
if (state.scene !== 'afternoon') { $('#scene-front').removeAttribute('srcset'); $('#scene-front').src = assetPath(state.scene, innerWidth < 700 ? 960 : 1920); }
$('#moment-open').addEventListener('click', () => openDialog('#moment-dialog'));
document.addEventListener('keydown', event => { if ((event.ctrlKey || event.metaKey) && ['k','n'].includes(event.key.toLowerCase())) { if (all('dialog').some(d => d.open)) return; event.preventDefault(); event.key.toLowerCase() === 'k' ? openSearch() : openCapture(); } });
renderNotes(); renderFocus(); renderRoutine(); renderActivity(); renderPreferences(); sceneText(state.scene);
if (storageIssue) notify('Some study data could not be restored. Sample thoughts are shown instead.');
