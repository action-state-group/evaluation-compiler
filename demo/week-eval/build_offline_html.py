import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
verifier = open(os.path.join(HERE, "aac-verifier.js")).read()
frag = open(os.path.join(HERE, "frag_v1.txt")).read().strip()
def esc(s): return s.replace("</script", "<\\/script")
OUT = os.path.expanduser("~/Downloads/tau2-airline-week1-full.html")

render = r"""
const $ = (t, c, x) => { const e = document.createElement(t); if (c) e.className = c; if (x!=null) e.textContent = x; return e; };
const badge = (s) => { const b = $("span","badge "+s, s); return b; };
(async () => {
  const root = document.getElementById("app");
  let bundle, res;
  try {
    bundle = window.AAC.decodeFragment(window.__FRAG__);
    res = await window.AAC.verifyBundle(bundle);
  } catch (e) { root.appendChild($("pre","err","decode/verify threw: "+(e&&e.stack||e))); return; }
  const memberships = (bundle.completeness_certificate||{}).memberships || {};
  const seqOf = (id) => (memberships[id]&&memberships[id].log_coordinates||{}).seq;
  // header
  const h = $("div","head");
  h.appendChild($("h1",null,"AAC Evidence Bundle — tau2-airline week 1 (full)"));
  const claims = $("div","claims");
  for (const [k,label] of [["graphClosure","graph closure"],["intervalCoverage","interval coverage"],["perRecordMembership","per-record membership"]]) {
    const c = $("div","claim"); c.appendChild($("span","lbl",label)); c.appendChild(badge(res[k].status)); claims.appendChild(c);
  }
  h.appendChild(claims);
  const dc = {}; for (const d of res.disclosures) dc[d.status]=(dc[d.status]||0)+1;
  h.appendChild($("div","sub", `${bundle.records.length} capsules · disclosures ` + Object.entries(dc).map(([k,v])=>`${v} ${k}`).join(" · ")));
  root.appendChild(h);
  // per-record disclosure status
  const dstat = {}; for (const d of res.disclosures) { (dstat[d.capsuleId]=dstat[d.capsuleId]||{})[d.member]=d.status; }
  // classify records by the DISCLOSED payload spec_version (the sealed capsule's own
  // spec_version is always the AAC capsule spec, so it cannot distinguish eval records).
  const discOf = (id) => (bundle.disclosures||{})[id]||{};
  const specOf = (id) => { const ai=discOf(id).agent_input; return (ai&&ai.spec_version)||""; };
  const kind = (r) => { const s=specOf(r.capsule_id); return s.startsWith("evaluation-summary")?"aggregate":s.startsWith("evaluation-report")?"report":"interaction"; };
  const counts = {aggregate:0, report:0, interaction:0};
  for (const r of bundle.records) counts[kind(r)]++;
  h.appendChild($("div","sub", `${counts.aggregate} aggregate · ${counts.report} daily reports · ${counts.interaction} interaction capsules`));
  const recs = bundle.records.slice().sort((a,b)=> (seqOf(a.capsule_id)||0)-(seqOf(b.capsule_id)||0));
  const order = {aggregate:0, report:1, interaction:2};
  recs.sort((a,b)=> (order[kind(a)]-order[kind(b)]) || ((seqOf(a.capsule_id)||0)-(seqOf(b.capsule_id)||0)));
  for (const r of recs) {
    const id = r.capsule_id, k = kind(r);
    const row = $("details","rec "+k);
    if (k !== "interaction") row.setAttribute("open","");
    const sum = $("summary");
    sum.appendChild($("span","k "+k, k));
    sum.appendChild($("span","seq", "seq "+(seqOf(id)||"?")));
    sum.appendChild($("span","cid", id.slice(0,16)+"…"));
    const ds = dstat[id]||{};
    for (const m of Object.keys(ds)) { const t=$("span","m"); t.appendChild($("span","mn",m)); t.appendChild(badge(ds[m]==="disclosure_match"?"match":ds[m])); sum.appendChild(t); }
    row.appendChild(sum);
    const disclosed = (bundle.disclosures||{})[id]||{};
    for (const m of Object.keys(disclosed)) {
      row.appendChild($("div","mlabel","revealed "+m+":"));
      row.appendChild($("pre","content", JSON.stringify(disclosed[m], null, 2)));
    }
    root.appendChild(row);
  }
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
'.pass,.match{background:#123a24;color:#57e389}.fail{background:#3a1216;color:#ff8a8a}.withheld{background:#3a3212;color:#e8d15a}'
'.rec{margin:8px 24px;background:#171a2e;border:1px solid #2a2f4a;border-radius:8px;padding:6px 12px}'
'.rec summary{cursor:pointer;display:flex;gap:12px;align-items:center;flex-wrap:wrap}'
'.k{font-weight:700;padding:2px 8px;border-radius:6px;font-size:11px;text-transform:uppercase}'
'.k.aggregate{background:#2a1e46;color:#c9a6ff}.k.report{background:#123049;color:#7cc4ff}.k.interaction{background:#22283f;color:#9aa0c0}'
'.seq{color:#9aa0c0}.cid{font-family:ui-monospace,Menlo,monospace;color:#8890b8}'
'.m{display:flex;gap:6px;align-items:center}.mn{color:#c7cbe6}'
'.mlabel{color:#9aa0c0;margin:8px 0 2px}'
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
