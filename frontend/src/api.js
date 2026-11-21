async function req(path, opts = {}) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try { const j = await r.json(); msg = j.detail || msg; } catch {}
    throw new Error(msg);
  }
  return r.json();
}

const json = (method, body) => ({
  method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}),
});

export const api = {
  runs: () => req("/api/runs"),
  run: (id) => req(`/api/runs/${id}`),
  stats: () => req("/api/stats"),
  intake: () => req("/api/intake"),
  samples: () => req("/api/samples"),
  runSample: (file) => req(`/api/samples/${encodeURIComponent(file)}/run`, json("POST")),
  upload: (files) => {
    const fd = new FormData();
    [...files].forEach((f) => fd.append("files", f));
    return req("/api/upload", { method: "POST", body: fd });
  },
  review: (id, action, comment) => req(`/api/runs/${id}/review`, json("POST", { action, comment })),
  rerun: (id) => req(`/api/runs/${id}/rerun`, json("POST")),
  drafts: () => req("/api/drafts"),
  editDraft: (id, body) => req(`/api/drafts/${id}`, json("PATCH", body)),
  sendDraft: (id) => req(`/api/drafts/${id}/send`, json("POST")),
  discardDraft: (id) => req(`/api/drafts/${id}/discard`, json("POST")),
  pos: () => req("/api/pos"),
  vendors: () => req("/api/vendors"),
  reset: () => req("/api/admin/reset", json("POST")),
};

export const fileUrl = (id) => `/api/runs/${id}/file`;
