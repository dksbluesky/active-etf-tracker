const REPO = "dksbluesky/active-etf-tracker";
const WORKFLOW_FILE = "update-data.yml";
const DATA_URL = `https://raw.githubusercontent.com/${REPO}/main/data/active_etf_ranking.json`;
const PAT_KEY = "etf_tracker_gh_pat";

function getPAT() {
  return localStorage.getItem(PAT_KEY) || "";
}

function setPAT(token) {
  if (token) localStorage.setItem(PAT_KEY, token.trim());
}

function promptForPAT() {
  const existing = getPAT();
  const token = window.prompt(
    "Paste a GitHub Personal Access Token (classic, with 'repo' + 'workflow' scopes).\n" +
      "Stored only in this browser's localStorage, never sent anywhere except api.github.com.",
    existing
  );
  if (token !== null) setPAT(token);
  return getPAT();
}

async function loadRanking() {
  const res = await fetch(`${DATA_URL}?t=${Date.now()}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to load ranking data (${res.status})`);
  return res.json();
}

// raw.githubusercontent.com sits behind a CDN cache that can lag several minutes
// behind a fresh commit, even with a cache-busting query param. Right after a
// refresh completes, read via the Contents API instead - it reflects the latest
// commit immediately. Requires the PAT (already needed to trigger the refresh).
async function loadRankingFresh() {
  const res = await ghFetch(`/repos/${REPO}/contents/data/active_etf_ranking.json?ref=main&t=${Date.now()}`, {
    headers: { Accept: "application/vnd.github.raw" },
  });
  if (!res.ok) throw new Error(`Failed to load fresh ranking data (${res.status})`);
  return res.json();
}

// Returns null if this fund doesn't have holdings tracking wired up yet (404 is expected, not an error).
async function loadHoldings(fundId) {
  const url = `https://raw.githubusercontent.com/${REPO}/main/data/holdings/${fundId}.json`;
  const res = await fetch(`${url}?t=${Date.now()}`, { cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Failed to load holdings (${res.status})`);
  return res.json();
}

async function ghFetch(path, options = {}) {
  const token = getPAT();
  const res = await fetch(`https://api.github.com${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      ...(options.headers || {}),
    },
  });
  return res;
}

async function getLatestRunId() {
  const res = await ghFetch(`/repos/${REPO}/actions/workflows/${WORKFLOW_FILE}/runs?per_page=1`);
  if (!res.ok) return null;
  const j = await res.json();
  return j.workflow_runs && j.workflow_runs[0] ? j.workflow_runs[0].id : null;
}

// Keep only the 3 newest runs total across ALL workflows (not 3 per workflow type).
// A server-side cleanup_runs.yml also does this automatically after every data
// refresh; this is just an immediate pass so the Actions list doesn't wait for it.
async function cleanupOldRuns() {
  try {
    const res = await ghFetch(`/repos/${REPO}/actions/runs?per_page=100`);
    if (!res.ok) return;
    const data = await res.json();
    const allRuns = (data.workflow_runs || []).sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
    const toDelete = allRuns.slice(3);
    if (!toDelete.length) return;
    await Promise.all(
      toDelete.map((run) => ghFetch(`/repos/${REPO}/actions/runs/${run.id}`, { method: "DELETE" }))
    );
  } catch (_) {
    // best-effort; the server-side cleanup workflow will catch anything missed
  }
}

async function triggerRefresh(onStatus) {
  let token = getPAT();
  if (!token) token = promptForPAT();
  if (!token) {
    onStatus("No token provided, cancelled.", true);
    return false;
  }

  onStatus("Triggering data refresh...");
  const beforeId = await getLatestRunId();

  const dispatchRes = await ghFetch(`/repos/${REPO}/actions/workflows/${WORKFLOW_FILE}/dispatches`, {
    method: "POST",
    body: JSON.stringify({ ref: "main" }),
  });

  if (dispatchRes.status === 401 || dispatchRes.status === 403) {
    onStatus("Token rejected by GitHub (expired or wrong scopes). Click refresh again to re-enter it.", true);
    localStorage.removeItem(PAT_KEY);
    return false;
  }
  if (!dispatchRes.ok && dispatchRes.status !== 204) {
    onStatus(`Failed to trigger refresh (HTTP ${dispatchRes.status}).`, true);
    return false;
  }

  onStatus("Refresh started, waiting for it to finish (usually 20-40s)...");

  for (let attempt = 0; attempt < 40; attempt++) {
    await new Promise((r) => setTimeout(r, 3000));
    const newId = await getLatestRunId();
    if (newId && newId !== beforeId) {
      const runRes = await ghFetch(`/repos/${REPO}/actions/runs/${newId}`);
      if (runRes.ok) {
        const run = await runRes.json();
        if (run.status === "completed") {
          if (run.conclusion === "success") {
            onStatus("Done! Cleaning up old runs and reloading...");
            await cleanupOldRuns();
            return true;
          }
          onStatus(`Refresh job finished with status: ${run.conclusion}.`, true);
          return false;
        }
        onStatus(`Refresh running... (${run.status})`);
      }
    }
  }
  onStatus("Timed out waiting for refresh. Data may still update shortly.", true);
  return false;
}

function fmtPct(n) {
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

function fmtVolume(n) {
  if (n >= 1e8) return (n / 1e8).toFixed(2) + "億";
  if (n >= 1e4) return (n / 1e4).toFixed(1) + "萬";
  return String(n);
}
