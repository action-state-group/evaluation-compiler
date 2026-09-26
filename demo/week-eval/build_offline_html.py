import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
verifier = open(os.path.join(HERE, "aac-verifier.js")).read()
frag = open(os.path.join(HERE, "frag_v1.txt")).read().strip()
def esc(s): return s.replace("</script", "<\\/script")
OUT = os.path.expanduser("~/Downloads/tau2-airline-week1-full.html")

# Render the bundle as a PROVENANCE TREE: from the root (the weekly aggregate),
# follow each record's references[] (acted_on) and chain parent down to the daily
# reports and then the interaction acts. Nodes carry their disclosed originals.
render = r"""
const $ = (t, c, x) => { const e = document.createElement(t); if (c) e.className = c; if (x!=null) e.textContent = x; return e; };
const badge = (s) => $("span", "badge " + s, s);
(async () => {
  const app = document.getElementById("app");
  let bundle, res;
  try { bundle = window.AAC.decodeFragment(window.__FRAG__); res = await window.AAC.verifyBundle(bundle); }
  catch (e) { app.appendChild($("pre", "err", "decode/verify threw: " + (e && e.stack || e))); return; }

  const byId = {}; for (const r of bundle.records) byId[r.capsule_id] = r;
  const memberships = (bundle.completeness_certificate || {}).memberships || {};
  const seqOf = (id) => (memberships[id] && memberships[id].log_coordinates || {}).seq;
  const disc = bundle.disclosures || {};
  const specOf = (id) => { const ai = (disc[id] || {}).agent_input; return (ai && ai.spec_version) || ""; };
  const kind = (id) => { const s = specOf(id); return s.startsWith("evaluation-summary") ? "aggregate" : s.startsWith("evaluation-report") ? "report" : byId[id] ? "interaction" : "missing"; };
  // disclosure status per (id, member)
  const dstat = {}; for (const d of res.disclosures) { (dstat[d.capsuleId] = dstat[d.capsuleId] || {})[d.member] = d.status; }
  // edges: a node cites its references[].digest (acted_on) and its chain parent
  const childrenOf = (id) => {
    const r = byId[id]; if (!r) return [];
    const kids = [];
    for (const ref of (r.references || [])) if (ref.digest) kids.push(ref.digest);
    const parent = (r.chain || {}).parent_capsule_id; if (parent) kids.push(parent);
    return kids;
  };

  // header
  const head = $("div", "head");
  head.appendChild($("h1", null, "AAC Evidence Bundle — tau2-airline week 1 (provenance tree)"));
  const claims = $("div", "claims");
  for (const [k, label] of [["graphClosure", "graph closure"], ["intervalCoverage", "interval coverage"], ["perRecordMembership", "per-record membership"]]) {
    const c = $("div", "claim"); c.appendChild($("span", "lbl", label)); c.appendChild(badge(res[k].status)); claims.appendChild(c);
  }
  head.appendChild(claims);
  const counts = { aggregate: 0, report: 0, interaction: 0 };
  for (const r of bundle.records) counts[kind(r.capsule_id)]++;
  const dc = {}; for (const d of res.disclosures) dc[d.status] = (dc[d.status] || 0) + 1;
  head.appendChild($("div", "sub", counts.aggregate + " aggregate · " + counts.report + " daily reports · " + counts.interaction + " interaction capsules · disclosures " + Object.entries(dc).map(([k, v]) => v + " " + k).join(" · ")));
  app.appendChild(head);

  const node = (id, seen) => {
    const k = kind(id);
    const details = $("details", "node " + k);
    if (k === "aggregate" || k === "report") details.setAttribute("open", "");
    const sum = $("summary");
    sum.appendChild($("span", "k " + k, k));
    const s = seqOf(id); if (s != null) sum.appendChild($("span", "seq", "seq " + s));
    sum.appendChild($("span", "cid", id.slice(0, 16) + "…"));
    if (k === "missing") sum.appendChild(badge("declared missing"));
    const ds = dstat[id] || {};
    for (const m of Object.keys(ds).sort()) { const t = $("span", "m"); t.appendChild($("span", "mn", m)); t.appendChild(badge(ds[m] === "disclosure_match" ? "match" : ds[m])); sum.appendChild(t); }
    details.appendChild(sum);
    const revealed = disc[id] || {};
    for (const m of Object.keys(revealed).sort()) {
      details.appendChild($("div", "mlabel", "revealed " + m + ":"));
      details.appendChild($("pre", "content", JSON.stringify(revealed[m], null, 2)));
    }
    if (seen.has(id)) { details.appendChild($("div", "cycle", "(already shown above)")); return details; }
    seen.add(id);
    const kids = childrenOf(id);
    if (kids.length) {
      const box = $("div", "children");
      for (const c of kids) box.appendChild(node(c, seen));
      details.appendChild(box);
    }
    return details;
  };
  app.appendChild(node(bundle.root, new Set()));
})();
"""

html = (
'<!doctype html><html><head><meta charset="utf-8"><title>AAC Evidence Bundle — tau2-airline week 1</title>'
'<style>'
'body{font:13px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#0f1220;color:#e6e8f0}'
'.head{padding:20px 24px;background:#171a2e;border-bottom:1px solid #2a2f4a}'
'h1{font-size:18px;margin:0 0 10px}.sub{color:#9aa0c0;margin-top:8px}'
'.claims{display:flex;gap:14px;flex-wrap:wrap}.claim{display:flex;gap:8px;align-items:center;background:#0f1220;padding:6px 12px;border-radius:8px}'
'.lbl{color:#c7cbe6}'
'.badge{font-weight:600;padding:2px 8px;border-radius:6px;text-transform:uppercase;font-size:11px}'
'.pass,.match{background:#123a24;color:#57e389}.fail{background:#3a1216;color:#ff8a8a}.withheld,.declared.missing{background:#3a3212;color:#e8d15a}'
'.node{margin:6px 0 6px 0;background:#171a2e;border:1px solid #2a2f4a;border-radius:8px;padding:6px 12px}'
'.node summary{cursor:pointer;display:flex;gap:12px;align-items:center;flex-wrap:wrap}'
'.children{margin-left:22px;border-left:2px solid #2a2f4a;padding-left:12px}'
'#app>.node{margin:14px 24px}'
'.k{font-weight:700;padding:2px 8px;border-radius:6px;font-size:11px;text-transform:uppercase}'
'.k.aggregate{background:#2a1e46;color:#c9a6ff}.k.report{background:#123049;color:#7cc4ff}.k.interaction{background:#22283f;color:#9aa0c0}.k.missing{background:#332;color:#e8d15a}'
'.seq{color:#9aa0c0}.cid{font-family:ui-monospace,Menlo,monospace;color:#8890b8}'
'.m{display:flex;gap:6px;align-items:center}.mn{color:#c7cbe6}'
'.mlabel{color:#9aa0c0;margin:8px 0 2px}.cycle{color:#8890b8;font-style:italic;margin:4px 0}'
'.content{background:#0f1220;border:1px solid #2a2f4a;border-radius:6px;padding:10px;max-height:340px;overflow:auto;white-space:pre-wrap;font-family:ui-monospace,Menlo,monospace;font-size:12px}'
'.err{color:#ff8a8a;padding:24px}'
'</style></head><body><div id="app"></div>'
'<script>' + esc(verifier) + '</script>'
'<script>window.__FRAG__=' + json.dumps(frag) + ';</script>'
'<script>' + render + '</script>'
'</body></html>'
)
open(OUT, "w").write(html)
print("wrote", OUT, "bytes:", len(html))
