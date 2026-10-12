// Loads data from the local API (127.0.0.1), then the screens. Recordings for the latest 5 runs are
// preloaded for the run panels; any other activity's recording is fetched when you open it.
(async () => {
  const get = async url => { const r = await fetch(url); if (!r.ok) throw new Error(`${url}: ${r.status}`); return r.json(); };
  try {
    const [summary, routes] = await Promise.all([get('api/summary'), get('api/routes')]);
    const runs = summary.activities.filter(a => a.s === 'run' && a.has_rec && a.km >= 1).slice(0, 5);
    await Promise.all(runs.map(async a => { a.rec = await get(`api/activities/${encodeURIComponent(a.id)}/recording`); }));
    summary.activities.forEach(a => { a.route = routes[a.id] || null; });
    window.REAL = summary;
  } catch (e) {
    document.querySelector('main').innerHTML = '<p class="muted">Could not load data from the local server. Is <code>uv run suunto-app</code> running?</p>';
    return;
  }
  for (const src of ['core.js', 'views.js', 'dash.js']) {
    await new Promise((ok, fail) => { const s = document.createElement('script'); s.src = src; s.onload = ok; s.onerror = fail; document.body.appendChild(s); });
  }
})();
