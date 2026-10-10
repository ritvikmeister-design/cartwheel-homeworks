"""Build session-grouped review records for the Cartwheel review app.

One record per cartwheel.session_id, with every turn in order, each tool call
paired with its result, and the verified answer key (expected outcome, the live
database record, and the applicable policy text) attached for side-by-side review.
"""
from __future__ import annotations
import json, math, pathlib, random, re, sqlite3, collections

REPO = pathlib.Path(__file__).resolve().parents[2]
STATE = REPO / "analysis" / "state"
TOOLS = {'get_order','list_my_orders','find_order','search_products','search_help_center',
         'get_policy','issue_refund','cancel_order','escalate_to_human'}

def _attrs(obj):
    md = obj.get("metadata") or {}
    a = md.get("attributes")
    if isinstance(a, str):
        try: a = json.loads(a)
        except Exception: a = {}
    return a or {}

def _text(v, limit=4000):
    if v is None: return ""
    if isinstance(v, str): s = v
    else:
        try:
            if isinstance(v, list):
                parts = []
                for m in v:
                    if isinstance(m, dict):
                        for p in (m.get("parts") or []):
                            if isinstance(p, dict) and p.get("content"):
                                parts.append(str(p["content"]))
                        if not m.get("parts") and m.get("content"):
                            parts.append(str(m["content"]))
                s = "\n".join(parts) if parts else json.dumps(v)[:limit]
            else: s = json.dumps(v)[:limit]
        except Exception: s = str(v)[:limit]
    return s[:limit]

# ---------- ground truth ----------
conn = sqlite3.connect(REPO/"data/cartwheel.db"); conn.row_factory = sqlite3.Row
ASOF = conn.execute("SELECT value FROM meta WHERE key='world_asof'").fetchone()[0]
POLICY = {}
for f in sorted((REPO/"data/policies").glob("*.md")):
    t = f.read_text(); pid = re.search(r"^policy_id:\s*(\S+)", t, re.M)
    body = re.sub(r"^#.*$", "", t.split("---")[-1], flags=re.M)
    if pid: POLICY[pid.group(1)] = re.sub(r"\s+", " ", body).strip()
spec = (REPO/"SPEC.md").read_text()
hits = list(re.finditer(r"\*\*([A-Z]+-\d+)\.\*\*", spec))
SPEC = {}
for i, m in enumerate(hits):
    end = hits[i+1].start() if i+1 < len(hits) else len(spec)
    SPEC[m.group(1)] = re.sub(r"\s+", " ", re.split(r"\n#{1,6}\s", spec[m.end():end])[0]).strip().rstrip(" -|")

def record_for(t):
    out = {}
    if "order_id" in t:
        r = conn.execute("""SELECT o.id, o.status, o.ordered_at, o.shipped_at, o.delivered_at,
            o.refund_eligible, printf('%.2f', o.total_cents/100.0) total_usd, s.name store,
            COALESCE(s.return_window_days_override,30) window_days, s.restocking_fee_opt_in,
            p.title product, p.store_id product_store,
            CAST(julianday(?)-julianday(o.delivered_at) AS INTEGER) age_days
            FROM orders o JOIN stores s ON s.id=o.store_id JOIN products p ON p.id=o.product_id
            WHERE o.id=?""", (ASOF, t["order_id"])).fetchone()
        out["order"] = dict(r) if r else {"id": t["order_id"], "note": "DOES NOT EXIST"}
    if "product_id" in t:
        r = conn.execute("""SELECT p.id, p.title, printf('%.2f', p.price_cents/100.0) price_usd,
            s.name store FROM products p JOIN stores s ON s.id=p.store_id WHERE p.id=?""",
            (t["product_id"],)).fetchone()
        out["product"] = dict(r) if r else None
    u = conn.execute("SELECT id, name, role, store_id FROM users WHERE id=?", (t["user_id"],)).fetchone()
    out["caller"] = dict(u) if u else None
    out["world_asof"] = ASOF
    return out

# ---------- load ----------
plan = {json.loads(l)["id"]: json.loads(l)
        for l in (REPO/"scenarios/support_scenarios.jsonl").read_text().splitlines() if l.strip()}
results = {json.loads(l)["scenario_id"]: json.loads(l)
           for l in (REPO/"scenarios/final-results.jsonl").read_text().splitlines() if l.strip()}
export = json.load(open(REPO/"traces/support_traces.json"))

by_session = collections.defaultdict(list)
for tr in export["traces"]:
    a = _attrs(tr)
    sid = a.get("cartwheel.session_id")
    if sid: by_session[sid].append(tr)

samples = []
for sid, trs in by_session.items():
    trs.sort(key=lambda x: x.get("createdAt") or x.get("timestamp") or "")
    a0 = _attrs(trs[0])
    scen = a0.get("cartwheel.scenario_id")
    if scen not in plan: continue
    p = plan[scen]; t = p["tuple"]
    turns = []
    for i, tr in enumerate(trs, 1):
        obs = tr.get("observations") or []
        calls = []
        for o in obs:
            if isinstance(o, dict) and o.get("name") in TOOLS:
                calls.append({"name": o["name"],
                              "args": _text(o.get("input"), 1200),
                              "result": _text(o.get("output"), 2500),
                              "level": o.get("level")})
        turns.append({"n": i, "trace_id": tr.get("id"), "html_path": tr.get("htmlPath"),
                      "user": _text(tr.get("input"), 2000), "agent": _text(tr.get("output"), 6000),
                      "tools": calls, "span_count": len(obs),
                      "latency": tr.get("latency")})
    pol = [x.strip() for x in re.split(r"[+,]", str(t.get("applicable_policy") or "")) if x.strip() in POLICY]
    refs = re.findall(r"(?:RESP|ESC|AUTH|SCOPE)-\d", str(p["expected"]["source"].get("reference") or ""))
    samples.append({
        "session_id": sid, "scenario_id": scen, "scenario_group": p["scenario_group"],
        "data_quality_case_id": p["data_quality_case_id"],
        "role": t["role"], "user_id": t["user_id"], "intent": t["intent"],
        "difficulty": t["difficulty"], "user_style": t["user_style"],
        "turn_count": t["turn_count"], "tools_needed": t["tools_needed"],
        "applicable_policy": t.get("applicable_policy"),
        "prompt_version": a0.get("cartwheel.prompt_version"),
        "model": results.get(scen, {}).get("model"),
        "duration_s": results.get(scen, {}).get("duration_s"),
        "expected": p["expected"],
        "record": record_for(t),
        "policy_text": {k: POLICY[k] for k in pol},
        "spec_text": {k: SPEC[k] for k in refs if k in SPEC},
        "turns": turns,
        "tool_names": [c["name"] for tn in turns for c in tn["tools"]],
    })

# ---------- features, clusters, 2D projection ----------
ROLE_IX = {"shopper": 0.0, "merchant": 1.0, "support": 2.0}
def feats(s):
    return [float(s["turn_count"]), float(len(s["tool_names"])),
            float(len(set(s["tool_names"]))), ROLE_IX.get(s["role"], 0.0),
            1.0 if any(n in ("issue_refund","cancel_order","escalate_to_human") for n in s["tool_names"]) else 0.0,
            float(sum(len(t["agent"]) for t in s["turns"])) / 500.0,
            1.0 if s["scenario_group"] == "challenge" else 0.0]
X = [feats(s) for s in samples]
cols = list(zip(*X))
mu = [sum(c)/len(c) for c in cols]
sd = [max(1e-9, math.sqrt(sum((v-m)**2 for v in c)/len(c))) for c, m in zip(cols, mu)]
Z = [[(v-m)/s for v, m, s in zip(row, mu, sd)] for row in X]

def kmeans(Z, k=8, iters=60, seed=11):
    rnd = random.Random(seed)
    cent = [list(Z[i]) for i in rnd.sample(range(len(Z)), min(k, len(Z)))]
    lab = [0]*len(Z)
    for _ in range(iters):
        for i, z in enumerate(Z):
            lab[i] = min(range(len(cent)), key=lambda c: sum((a-b)**2 for a, b in zip(z, cent[c])))
        for c in range(len(cent)):
            pts = [Z[i] for i in range(len(Z)) if lab[i] == c]
            if pts: cent[c] = [sum(col)/len(col) for col in zip(*pts)]
    return lab
labels = kmeans(Z)

def pca2(Z):
    n, d = len(Z), len(Z[0])
    cov = [[sum(Z[i][a]*Z[i][b] for i in range(n))/n for b in range(d)] for a in range(d)]
    def power(cov, exclude=None, iters=200):
        v = [1.0/math.sqrt(d)]*d
        for _ in range(iters):
            w = [sum(cov[a][b]*v[b] for b in range(d)) for a in range(d)]
            if exclude:
                dot = sum(w[a]*exclude[a] for a in range(d))
                w = [w[a]-dot*exclude[a] for a in range(d)]
            nrm = math.sqrt(sum(x*x for x in w)) or 1.0
            v = [x/nrm for x in w]
        return v
    p1 = power(cov); p2 = power(cov, exclude=p1)
    return [[sum(z[a]*p1[a] for a in range(d)), sum(z[a]*p2[a] for a in range(d))] for z in Z]
proj = pca2(Z)

for s, lab, xy in zip(samples, labels, proj):
    s["cluster"] = int(lab)
    s["xy"] = [round(xy[0], 4), round(xy[1], 4)]

STATE.mkdir(parents=True, exist_ok=True)
(STATE/"samples.json").write_text(json.dumps({"samples": samples}, indent=2) + "\n")
(STATE/"graph.json").write_text(json.dumps({"nodes": [
    {"session_id": s["session_id"], "scenario_id": s["scenario_id"], "x": s["xy"][0],
     "y": s["xy"][1], "cluster": s["cluster"], "role": s["role"],
     "group": s["scenario_group"], "tools": len(s["tool_names"])} for s in samples]}, indent=2) + "\n")

print("sessions:", len(samples))
print("clusters:", dict(sorted(collections.Counter(s["cluster"] for s in samples).items())))
print("multi-turn sessions:", sum(1 for s in samples if s["turn_count"] > 1))
print("sessions with >=1 tool call:", sum(1 for s in samples if s["tool_names"]))
print("with policy text attached:", sum(1 for s in samples if s["policy_text"]))
print("with spec text attached:", sum(1 for s in samples if s["spec_text"]))
print("wrote", STATE/"samples.json", "and", STATE/"graph.json")
