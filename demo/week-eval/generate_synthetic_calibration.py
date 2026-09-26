#!/usr/bin/env python3
"""Create a labelled synthetic calibration-chain demo, never human evidence."""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, tempfile
from decimal import Decimal

CAPSULECTL=os.environ.get("CAPSULECTL","capsulectl"); PROFILE=os.environ.get("AAC_PROFILE","airlinedemo")
def cli(*args):
 p=subprocess.run([CAPSULECTL,*args],text=True,capture_output=True)
 if p.returncode: raise SystemExit(p.stderr.strip())
 return json.loads(p.stdout)
def publish(request):
 with tempfile.NamedTemporaryFile("w",delete=False) as f: json.dump(request,f); path=f.name
 try: return cli("publish","--profile",PROFILE,"--request",path).get("capsule_id")
 finally: os.unlink(path)
def payload(record):
 for a in record.get("artifacts",[]):
  if a.get("name") in ("agent_input","payload") and isinstance(a.get("content"),dict): return a["content"]
 return {}
def reports(month):
 after=0; found=[]
 while True:
  page=cli("cll","list","--profile",PROFILE,"--after",str(after),"--limit","1000")
  for entry in page.get("entries",[]):
   cid=entry.get("capsule_id") or entry["capsuleId"]; body=payload(cli("get","--profile",PROFILE,"--capsule-id",cid))
   if body.get("spec_version")=="evaluation-report/v1" and body.get("date","").startswith(month): found.append((cid,body))
  if not page.get("entries") or page.get("next_after") in (None,after): return found
  after=page["next_after"]
def req(action,timestamp,payload,chain=None):
 cap={"ActionID":action,"ActionType":"fyi","Operator":"ACME-AIR","Developer":"tau2-airline-synthetic-calibration@v1","Timestamp":timestamp}
 if chain: cap["Chain"]=chain
 return {"spec_version":"capsule-seal-request/v1","capsule":cap,"payload":payload}
def decimal(value): return format(Decimal(str(value)).quantize(Decimal(".0001")),"f")
def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--month",default="2026-09"); ap.add_argument("--seed",default="demo-synthetic-v1"); args=ap.parse_args()
 strata={"judge_pass":[],"judge_fail":[]}
 monthly_reports=reports(args.month)
 for cid,report in monthly_reports:
  verdict=report.get("daily_aggregate",{}).get("verdict")
  if verdict in ("pass","fail"): strata["judge_"+verdict].append(cid)
 for ids in strata.values(): ids.sort(key=lambda cid:(hashlib.sha256(len(args.seed.encode()).to_bytes(4,"big")+args.seed.encode()+cid.encode()).hexdigest(),cid))
 selected={s:ids[:min(2,len(ids))] for s,ids in strata.items()}
 manifest={"spec_version":"sample-manifest/v1","synthetic":True,"label":"illustrative synthetic stand-in, not human evidence","period_window":args.month,"audited_quantity":"daily_aggregate","N_p":len(strata["judge_pass"]),"N_f":len(strata["judge_fail"]),"n_p":len(selected["judge_pass"]),"n_f":len(selected["judge_fail"]),"seed":args.seed,"selection_rule":"SHA-256(u32be(len(utf8(seed))) || utf8(seed) || utf8(report_capsule_id)); ascending hex then id","selected":selected}
 manifest_id=publish(req("tau2-airline-synthetic-manifest-"+args.month,args.month+"-28T20:00:00Z",manifest))
 ratings=[]
 for stratum,ids in selected.items():
  for i,cid in enumerate(ids):
   verdict="unsure" if i==1 else ("fail" if stratum=="judge_pass" else "pass")
   rating={"spec_version":"human-rating/v1","synthetic":True,"label":"illustrative synthetic rating; not a human judgment","rated_quantity":"daily_aggregate","verdict":verdict,"blind":False,"rater":{"role":"synthetic-demo-generator","id":"synthetic"},"sampling":{"stratum":stratum,"audited_report_capsule_id":cid,"sample_manifest_capsule_id":manifest_id}}
   ratings.append((stratum,verdict,publish(req("tau2-airline-synthetic-rating-"+cid[:16],args.month+"-28T20:01:00Z",rating,{"ParentCapsuleID":cid,"Relation":"io.evaluation.human_rates"}))))
 usable={s:[v for st,v,_ in ratings if st==s and v!="unsure"] for s in strata}
 def estimate(values,event,stratum):
  if not values: return {"estimated":False,"estimate":None,"note":f"not estimated: no usable ratings in {stratum} stratum"}
  return {"estimated":True,"estimate":decimal(sum(value==event for value in values)/len(values)),"ci_95":{"lower":"0.0000","upper":"1.0000"}}
 summary={"spec_version":"calibration-summary/v1","synthetic":True,"label":"illustrative synthetic calibration only; replace with blind human ratings","period_window":args.month,"audited_quantity":"daily_aggregate","sampling":{"N_p":len(strata["judge_pass"]),"N_f":len(strata["judge_fail"]),"n_p":len(selected["judge_pass"]),"n_f":len(selected["judge_fail"]),"m_p":len(usable["judge_pass"]),"m_f":len(usable["judge_fail"]),"sample_manifest_capsule_id":manifest_id},"source_selection":{"contributing_report_capsule_ids":[cid for cid,_ in monthly_reports],"contributing_human_rating_capsule_ids":[rating_id for _,_,rating_id in ratings]},"estimates":{"false_pass_rate":estimate(usable["judge_pass"],"fail","judge_pass"),"false_fail_rate":estimate(usable["judge_fail"],"pass","judge_fail")},"nonresponse":{"unsure":sum(v=="unsure" for _,v,_ in ratings)},"drift":{"status":"not_available","reason":"single illustrative period"},"limitations":["Synthetic ratings are not human evidence.","Small demo samples have deliberately wide confidence intervals."]}
 print("CALIBRATION_SUMMARY_CAPSULE_ID="+publish(req("tau2-airline-synthetic-calibration-"+args.month,args.month+"-28T20:02:00Z",summary)))
if __name__=="__main__": main()
