from __future__ import annotations

from collections import defaultdict
import json, math, re, threading
from typing import Any
from sqlalchemy import text
from app.database import engine, get_session

try:
    from app.services.factory_resource_intelligence_service import FactoryResourceIntelligenceService
except Exception:
    FactoryResourceIntelligenceService = None

_LOCK = threading.Lock()
_READY = False

SAP_ALIASES = ("sap_code","sap","sap_no","sapcode","material_code","item_code","tyre_code","tire_code")
DESC_ALIASES = ("material_description","description","tyre_description","tire_description","item_description")
LINE_ALIASES = ("line","production_line","line_name")
CAVITY_ALIASES = ("oven_no","cavity","oven","oven_no_cavity","cavity_no","press_no")
DATE_ALIASES = ("plan_date","source_date","snapshot_date","workbook_date","production_date","date","updated_at","created_at","imported_at")
FACT_ALIASES = {
    "weight_kg":("weight_per_tyre_kg","weight_kg","weight","tyre_weight","tire_weight"),
    "key_code":("key_code","mold_key_code","mould_key_code","mold_code","mould_code"),
    "casing_type":("casing_type","casing_code","casing"),
    "curing":("normal_curing_minutes","curing_minutes","curing_cycle","curing_time"),
    "heel":("heel",),"soft":("soft",),"tread":("tred","tread"),
    "day_plan":("day_plan",),"night_plan":("night_plan",),
    "day_actual":("day_produced","day_actual","day_production"),
    "night_actual":("night_produced","night_actual","night_production"),
    "current_stock":("current_stock","live_stock","available_stock"),
    "total_stock":("total_stock","opening_stock"),"scrap":("scrap",),"blocked":("blocked","block"),
}
FIXED_MATERIALS = ("CORE","BAND","COMPOUND","BEAD","TOTAL BEAD","WGT")

def _clean(v: Any) -> str:
    if v is None: return ""
    s = str(v).strip()
    return "" if s.lower() in {"none","nan","null","#n/a","#value!"} else s

def _sap(v: Any) -> str:
    s = _clean(v)
    if s.endswith(".0"): s = s[:-2]
    d = re.sub(r"\D","",s)
    return d if 6 <= len(d) <= 12 else ""

def _num(v: Any) -> float:
    try: return float(v or 0)
    except Exception:
        m = re.search(r"-?\d+(?:\.\d+)?", _clean(v).replace(",",""))
        return float(m.group(0)) if m else 0.0

def _norm(v: Any) -> str:
    return " ".join(re.sub(r"[^A-Z0-9./+\- ]+"," ",_clean(v).upper()).split())

def _guess_size(desc: str) -> str:
    p = _clean(desc).split()
    if not p: return ""
    if len(p) >= 2 and re.match(r"^\d+(?:\.\d+)?X\d+(?:\.\d+)?$",p[0],re.I) and re.match(r"^\d+/\d+-\d+",p[1]):
        return f"{p[0]} {p[1]}"
    return p[0]

def _qid(name: str) -> str:
    return '"' + name.replace('"','""') + '"'

def _first(cols: set[str], aliases) -> str|None:
    lower = {c.lower():c for c in cols}
    for a in aliases:
        if a.lower() in lower: return lower[a.lower()]
    return None

def _material_type(table: str) -> str:
    n = _norm(table.replace("_"," "))
    if "TOTAL BEAD" in n: return "TOTAL BEAD"
    for x in ("CORE","BAND","COMPOUND","BEAD","WGT"):
        if x in n: return x
    if "MATERIAL" in n: return "MATERIAL"
    return ""

class TyreMasterMatrixService:
    @classmethod
    def ensure_schema(cls):
        global _READY
        if _READY: return
        with _LOCK:
            if _READY: return
            stmts = (
                """CREATE TABLE IF NOT EXISTS mpps_tyre_line_compatibility(
                    sap_code TEXT NOT NULL,line TEXT NOT NULL,compatibility VARCHAR(24) NOT NULL DEFAULT 'UNKNOWN',
                    evidence_count INTEGER NOT NULL DEFAULT 0,source VARCHAR(100) NOT NULL DEFAULT '',
                    last_seen TEXT NOT NULL DEFAULT '',updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(sap_code,line))""",
                """CREATE TABLE IF NOT EXISTS mpps_tyre_cavity_compatibility(
                    sap_code TEXT NOT NULL,line TEXT NOT NULL DEFAULT '',cavity TEXT NOT NULL,
                    compatibility VARCHAR(24) NOT NULL DEFAULT 'UNKNOWN',evidence_count INTEGER NOT NULL DEFAULT 0,
                    source VARCHAR(100) NOT NULL DEFAULT '',last_seen TEXT NOT NULL DEFAULT '',
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(sap_code,line,cavity))""",
                """CREATE TABLE IF NOT EXISTS mpps_tyre_v35_fact(
                    sap_code TEXT NOT NULL,fact_key VARCHAR(80) NOT NULL,fact_value TEXT NOT NULL DEFAULT '',
                    source_table TEXT NOT NULL DEFAULT '',source_date TEXT NOT NULL DEFAULT '',
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(sap_code,fact_key))""",
                """CREATE TABLE IF NOT EXISTS mpps_tyre_v35_material(
                    sap_code TEXT NOT NULL,material_type VARCHAR(80) NOT NULL,display_value TEXT NOT NULL DEFAULT '',
                    source_table TEXT NOT NULL DEFAULT '',source_date TEXT NOT NULL DEFAULT '',
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(sap_code,material_type))""",
                """CREATE TABLE IF NOT EXISTS mpps_tyre_v35_sync_state(
                    id INTEGER PRIMARY KEY,status VARCHAR(40) NOT NULL DEFAULT 'NEVER_SYNCED',
                    line_links INTEGER NOT NULL DEFAULT 0,cavity_links INTEGER NOT NULL DEFAULT 0,
                    fact_links INTEGER NOT NULL DEFAULT 0,material_links INTEGER NOT NULL DEFAULT 0,
                    message TEXT NOT NULL DEFAULT '',last_synced_at TIMESTAMP)""",
                "CREATE INDEX IF NOT EXISTS ix_v35_line_sap ON mpps_tyre_line_compatibility(sap_code)",
                "CREATE INDEX IF NOT EXISTS ix_v35_cavity_sap ON mpps_tyre_cavity_compatibility(sap_code)",
                "CREATE INDEX IF NOT EXISTS ix_v35_fact_sap ON mpps_tyre_v35_fact(sap_code)",
                "CREATE INDEX IF NOT EXISTS ix_v35_material_sap ON mpps_tyre_v35_material(sap_code)",
            )
            with engine.begin() as c:
                for s in stmts: c.execute(text(s))
                c.execute(text("INSERT INTO mpps_tyre_v35_sync_state(id) VALUES(1) ON CONFLICT(id) DO NOTHING"))
            _READY = True

    @classmethod
    def _catalog(cls):
        with engine.connect() as c:
            rows = c.execute(text("""SELECT table_name,column_name FROM information_schema.columns
                WHERE table_schema='public' ORDER BY table_name,ordinal_position""")).mappings().all()
        by = defaultdict(set)
        for r in rows: by[str(r["table_name"])].add(str(r["column_name"]))
        out = []
        for table, cols in by.items():
            if table.startswith("mpps_tyre_v35_"): continue
            sap = _first(cols,SAP_ALIASES)
            if not sap: continue
            out.append({"table":table,"cols":cols,"sap":sap,"desc":_first(cols,DESC_ALIASES),
                        "line":_first(cols,LINE_ALIASES),"cavity":_first(cols,CAVITY_ALIASES),
                        "date":_first(cols,DATE_ALIASES)})
        return out

    @classmethod
    def _up_line(cls,c,sap,line,source,seen=""):
        sap,line = _sap(sap),_clean(line)
        if not sap or not line: return
        c.execute(text("""INSERT INTO mpps_tyre_line_compatibility
            (sap_code,line,compatibility,evidence_count,source,last_seen)
            VALUES(:sap,:line,'CONFIRMED',1,:src,NULLIF(:seen,'')::date)
            ON CONFLICT(sap_code,line) DO UPDATE SET
            compatibility=CASE WHEN mpps_tyre_line_compatibility.source='MANUAL'
                AND mpps_tyre_line_compatibility.compatibility='INCOMPATIBLE'
                THEN 'INCOMPATIBLE' ELSE 'CONFIRMED' END,
            evidence_count=GREATEST(mpps_tyre_line_compatibility.evidence_count,1),
            source=CASE WHEN mpps_tyre_line_compatibility.source='MANUAL' THEN 'MANUAL' ELSE EXCLUDED.source END,
            last_seen=COALESCE(EXCLUDED.last_seen, mpps_tyre_line_compatibility.last_seen),
            updated_at=CURRENT_TIMESTAMP"""),{"sap":sap,"line":line,"src":source[:100],"seen":seen[:80]})

    @classmethod
    def _up_cavity(cls,c,sap,line,cavity,source,seen=""):
        sap,line,cavity = _sap(sap),_clean(line),_clean(cavity)
        if not sap or not cavity: return
        c.execute(text("""INSERT INTO mpps_tyre_cavity_compatibility
            (sap_code,line,cavity,compatibility,evidence_count,source,last_seen)
            VALUES(:sap,:line,:cav,'CONFIRMED',1,:src,NULLIF(:seen,'')::date)
            ON CONFLICT(sap_code,line,cavity) DO UPDATE SET
            compatibility=CASE WHEN mpps_tyre_cavity_compatibility.source='MANUAL'
                AND mpps_tyre_cavity_compatibility.compatibility='INCOMPATIBLE'
                THEN 'INCOMPATIBLE' ELSE 'CONFIRMED' END,
            evidence_count=GREATEST(mpps_tyre_cavity_compatibility.evidence_count,1),
            source=CASE WHEN mpps_tyre_cavity_compatibility.source='MANUAL' THEN 'MANUAL' ELSE EXCLUDED.source END,
            last_seen=COALESCE(EXCLUDED.last_seen, mpps_tyre_cavity_compatibility.last_seen),
            updated_at=CURRENT_TIMESTAMP"""),{"sap":sap,"line":line,"cav":cavity,"src":source[:100],"seen":seen[:80]})

    @classmethod
    def _up_fact(cls,c,sap,key,value,source,seen=""):
        sap,val = _sap(sap),_clean(value)
        if not sap or not val: return
        if key in {"weight_kg","day_plan","night_plan","day_actual","night_actual","current_stock","total_stock","scrap","blocked"} and _num(value)==0:
            return
        c.execute(text("""INSERT INTO mpps_tyre_v35_fact
            (sap_code,fact_key,fact_value,source_table,source_date)
            VALUES(:sap,:key,:val,:src,:seen)
            ON CONFLICT(sap_code,fact_key) DO UPDATE SET
            fact_value=EXCLUDED.fact_value,source_table=EXCLUDED.source_table,
            source_date=EXCLUDED.source_date,updated_at=CURRENT_TIMESTAMP"""),
            {"sap":sap,"key":key,"val":val,"src":source[:200],"seen":seen[:80]})

    @classmethod
    def sync_database_authority(cls, force=False):
        cls.ensure_schema()
        with engine.begin() as c:
            # SMDS is always authoritative master data and immediately confirms its line field.
            cols = {str(x) for x in c.execute(text("""SELECT column_name FROM information_schema.columns
                WHERE table_schema='public' AND table_name='smds'""")).scalars().all()}
            if "sap_code" in cols:
                wanted = {"sap_code"}
                line_col = _first(cols,LINE_ALIASES)
                if line_col: wanted.add(line_col)
                fact_cols = {}
                for key,aliases in FACT_ALIASES.items():
                    col = _first(cols,aliases)
                    if col: wanted.add(col); fact_cols[key]=col
                rows = c.execute(text("SELECT "+",".join(_qid(x) for x in wanted)+" FROM smds")).mappings().all()
                for r in rows:
                    sap = _sap(r.get("sap_code"))
                    if line_col: cls._up_line(c,sap,r.get(line_col),"smds")
                    for key,col in fact_cols.items(): cls._up_fact(c,sap,key,r.get(col),"smds")

            # Discover other committed DB sources written by Excel/import/planning modules.
            for item in cls._catalog():
                table, cols, sap_col = item["table"], item["cols"], item["sap"]
                if table in {"smds","mpps_tyre_line_compatibility","mpps_tyre_cavity_compatibility"}: continue
                line_col,cavity_col,date_col = item["line"],item["cavity"],item["date"]
                facts = {key:_first(cols,aliases) for key,aliases in FACT_ALIASES.items()}
                facts = {k:v for k,v in facts.items() if v}
                mtype = _material_type(table)
                if not line_col and not cavity_col and not facts and not mtype: continue
                selected = [sap_col]
                for x in (line_col,cavity_col,date_col,*facts.values()):
                    if x and x not in selected: selected.append(x)
                if mtype:
                    for x in list(cols)[:40]:
                        if x not in selected: selected.append(x)
                q = "SELECT "+",".join(_qid(x) for x in selected)+f" FROM {_qid(table)} WHERE {_qid(sap_col)} IS NOT NULL LIMIT 100000"
                try: rows = c.execute(text(q)).mappings().all()
                except Exception: continue
                for r in rows:
                    sap = _sap(r.get(sap_col))
                    if not sap: continue
                    seen = _clean(r.get(date_col)) if date_col else ""
                    line = _clean(r.get(line_col)) if line_col else ""
                    cavity = _clean(r.get(cavity_col)) if cavity_col else ""
                    if line: cls._up_line(c,sap,line,table,seen)
                    if cavity: cls._up_cavity(c,sap,line,cavity,table,seen)
                    for key,col in facts.items(): cls._up_fact(c,sap,key,r.get(col),table,seen)
                    if mtype:
                        values=[]
                        for col in selected:
                            if col in {sap_col,item.get("desc"),date_col,line_col,cavity_col}: continue
                            v=_clean(r.get(col))
                            if v and v not in values: values.append(v)
                            if len(values)>=4: break
                        display=" • ".join(values)[:800]
                        if display:
                            c.execute(text("""INSERT INTO mpps_tyre_v35_material
                                (sap_code,material_type,display_value,source_table,source_date)
                                VALUES(:sap,:typ,:val,:src,:seen)
                                ON CONFLICT(sap_code,material_type) DO UPDATE SET
                                display_value=EXCLUDED.display_value,source_table=EXCLUDED.source_table,
                                source_date=EXCLUDED.source_date,updated_at=CURRENT_TIMESTAMP"""),
                                {"sap":sap,"typ":mtype,"val":display,"src":table,"seen":seen})

            counts = {}
            counts["line_links"] = int(c.execute(text("SELECT COUNT(*) FROM mpps_tyre_line_compatibility WHERE compatibility='CONFIRMED'")).scalar() or 0)
            counts["cavity_links"] = int(c.execute(text("SELECT COUNT(*) FROM mpps_tyre_cavity_compatibility WHERE compatibility='CONFIRMED'")).scalar() or 0)
            counts["fact_links"] = int(c.execute(text("SELECT COUNT(*) FROM mpps_tyre_v35_fact")).scalar() or 0)
            counts["material_links"] = int(c.execute(text("SELECT COUNT(*) FROM mpps_tyre_v35_material")).scalar() or 0)
            c.execute(text("""UPDATE mpps_tyre_v35_sync_state SET status='SYNCED',
                line_links=:line_links,cavity_links=:cavity_links,fact_links=:fact_links,
                material_links=:material_links,message=:message,last_synced_at=CURRENT_TIMESTAMP WHERE id=1"""),
                {**counts,"message":f"Database authority: {counts['line_links']} line, {counts['cavity_links']} cavity, {counts['material_links']} material links"})
        return {"changed":True,"status":"SYNCED",**counts}

    @classmethod
    def _resources(cls):
        cls.ensure_schema()
        lines=set(); cavities=set()
        if FactoryResourceIntelligenceService is not None:
            try:
                with get_session() as session:
                    svc=FactoryResourceIntelligenceService()
                    for tab in ("lines","production_lines"):
                        try:
                            payload=svc.tab_snapshot(session,tab)
                            rows=payload if isinstance(payload,list) else next((payload.get(k) for k in ("rows","items","data","records") if isinstance(payload,dict) and isinstance(payload.get(k),list)),[])
                            for r in rows:
                                line=_clean(r.get("line") or r.get("production_line") or r.get("line_name") or r.get("name"))
                                if line: lines.add(line)
                            if lines: break
                        except Exception: pass
                    for tab in ("cavities","cavity"):
                        try:
                            payload=svc.tab_snapshot(session,tab)
                            rows=payload if isinstance(payload,list) else next((payload.get(k) for k in ("rows","items","data","records") if isinstance(payload,dict) and isinstance(payload.get(k),list)),[])
                            for r in rows:
                                line=_clean(r.get("line") or r.get("production_line") or r.get("line_name"))
                                cav=_clean(r.get("cavity") or r.get("oven_no") or r.get("oven_no_cavity") or r.get("oven") or r.get("name"))
                                if line: lines.add(line)
                                if cav: cavities.add((line,cav))
                            if cavities: break
                        except Exception: pass
            except Exception: pass
        with engine.connect() as c:
            for r in c.execute(text("SELECT line FROM mpps_tyre_line_compatibility GROUP BY line")).mappings().all():
                if _clean(r.get("line")): lines.add(_clean(r.get("line")))
            for r in c.execute(text("SELECT line,cavity FROM mpps_tyre_cavity_compatibility GROUP BY line,cavity")).mappings().all():
                if _clean(r.get("cavity")): cavities.add((_clean(r.get("line")),_clean(r.get("cavity"))))
        return sorted(lines),sorted(cavities)

    @classmethod
    def matrix_columns(cls):
        lines,cavities=cls._resources()
        with engine.connect() as c:
            extra=[_clean(x) for x in c.execute(text("SELECT material_type FROM mpps_tyre_v35_material GROUP BY material_type ORDER BY material_type")).scalars().all()]
        materials=list(FIXED_MATERIALS)+[x for x in extra if x and x not in FIXED_MATERIALS]
        cols=[
            {"group":"TYRE ITEM","label":"SAP Code","key":"sap_code","kind":"TEXT"},
            {"group":"TYRE ITEM","label":"Description","key":"description","kind":"TEXT"},
            {"group":"TYRE ITEM","label":"Tyre Size","key":"tyre_size","kind":"TEXT"},
            {"group":"TYRE ITEM","label":"Weight kg","key":"weight_kg","kind":"TEXT"},
        ]
        cols += [{"group":"LINE COMPATIBILITY","label":x,"key":f"line::{x}","kind":"COMPAT"} for x in lines]
        cols += [{"group":"CAVITY / OVEN COMPATIBILITY","label":f"{line} • {cav}" if line else cav,"key":f"cavity::{line}|{cav}","kind":"COMPAT"} for line,cav in cavities]
        cols += [{"group":"PROCESS","label":lab,"key":key,"kind":"TEXT"} for lab,key in (
            ("Mold / Key","key_code"),("Casing","casing_type"),("Curing","curing"),
            ("HEEL","heel"),("SOFT","soft"),("Tread","tread"))]
        cols += [{"group":"MATERIAL / COMPONENTS","label":x,"key":f"material::{x}","kind":"MATERIAL"} for x in materials]
        cols += [{"group":"PLAN / STOCK","label":lab,"key":key,"kind":"TEXT"} for lab,key in (
            ("Day Plan","day_plan"),("Night Plan","night_plan"),("Day Actual","day_actual"),
            ("Night Actual","night_actual"),("Current Stock","current_stock"),("Total Stock","total_stock"),
            ("Scrap","scrap"),("Block","blocked"))]
        cols += [{"group":"SOURCE","label":"Last Seen","key":"last_seen","kind":"TEXT"},
                 {"group":"SOURCE","label":"Latest Source","key":"latest_source","kind":"TEXT"}]
        return cols

    @classmethod
    def matrix_page(cls,search="",page=1,page_size=100):
        cls.ensure_schema()
        page=max(1,int(page)); page_size=max(50,min(200,int(page_size))); offset=(page-1)*page_size
        cols_meta=cls.matrix_columns()
        with engine.connect() as c:
            smds_cols={str(x) for x in c.execute(text("""SELECT column_name FROM information_schema.columns
                WHERE table_schema='public' AND table_name='smds'""")).scalars().all()}
            desc_col=_first(smds_cols,DESC_ALIASES)
            params={"limit":page_size,"offset":offset}; where=""
            if _clean(search):
                params["search"]=f"%{_clean(search)}%"
                where=f"WHERE (s.sap_code ILIKE :search OR COALESCE(s.{_qid(desc_col)},'') ILIKE :search)" if desc_col else "WHERE s.sap_code ILIKE :search"
            total=int(c.execute(text(f"SELECT COUNT(*) FROM smds s {where}"),params).scalar() or 0)
            base=[dict(r) for r in c.execute(text(f"""SELECT s.sap_code,
                {f"COALESCE(s.{_qid(desc_col)},'')" if desc_col else "''"} AS description
                FROM smds s {where} ORDER BY s.sap_code LIMIT :limit OFFSET :offset"""),params).mappings().all()]
            saps=[_clean(r.get("sap_code")) for r in base if _clean(r.get("sap_code"))]
            if not saps:
                return {"columns":cols_meta,"rows":[],"total":total,"page":page,"page_size":page_size,"page_count":max(1,math.ceil(total/page_size))}
            line_rows=c.execute(text("SELECT * FROM mpps_tyre_line_compatibility WHERE sap_code=ANY(:saps)"),{"saps":saps}).mappings().all()
            cav_rows=c.execute(text("SELECT * FROM mpps_tyre_cavity_compatibility WHERE sap_code=ANY(:saps)"),{"saps":saps}).mappings().all()
            fact_rows=c.execute(text("SELECT * FROM mpps_tyre_v35_fact WHERE sap_code=ANY(:saps)"),{"saps":saps}).mappings().all()
            mat_rows=c.execute(text("SELECT * FROM mpps_tyre_v35_material WHERE sap_code=ANY(:saps)"),{"saps":saps}).mappings().all()
        lm=defaultdict(dict); cm=defaultdict(dict); fm=defaultdict(dict); mm=defaultdict(dict)
        for r in line_rows: lm[_clean(r["sap_code"])][_clean(r["line"])]=dict(r)
        for r in cav_rows: cm[_clean(r["sap_code"])][(_clean(r["line"]),_clean(r["cavity"]))]=dict(r)
        for r in fact_rows: fm[_clean(r["sap_code"])][_clean(r["fact_key"])]=dict(r)
        for r in mat_rows: mm[_clean(r["sap_code"])][_clean(r["material_type"])]=dict(r)
        def sym(state):
            state=_clean(state).upper()
            return "✓" if state=="CONFIRMED" else ("✕" if state=="INCOMPATIBLE" else "?")
        out=[]
        for b in base:
            sap=_clean(b["sap_code"]); row={"sap_code":sap,"description":_clean(b["description"]),"tyre_size":_guess_size(b["description"])}
            for key in FACT_ALIASES:
                row[key]=fm[sap].get(key,{}).get("fact_value")
            dates=[]; sources=[]
            for col in cols_meta:
                key=col["key"]
                if key.startswith("line::"):
                    rec=lm[sap].get(key[6:]); row[key]=sym(rec.get("compatibility") if rec else "UNKNOWN")
                    if rec:
                        dates.append(_clean(rec.get("last_seen"))); sources.append(_clean(rec.get("source")))
                elif key.startswith("cavity::"):
                    raw=key[8:]; line,cav=raw.split("|",1); rec=cm[sap].get((line,cav)); row[key]=sym(rec.get("compatibility") if rec else "UNKNOWN")
                    if rec:
                        dates.append(_clean(rec.get("last_seen"))); sources.append(_clean(rec.get("source")))
                elif key.startswith("material::"):
                    rec=mm[sap].get(key[10:]); row[key]=rec.get("display_value") if rec else ""
                    if rec:
                        dates.append(_clean(rec.get("source_date"))); sources.append(_clean(rec.get("source_table")))
            for rec in fm[sap].values():
                dates.append(_clean(rec.get("source_date"))); sources.append(_clean(rec.get("source_table")))
            row["last_seen"]=max([x for x in dates if x],default="")
            uniq=[]
            for x in sources:
                if x and x not in uniq: uniq.append(x)
            row["latest_source"]=", ".join(uniq[:3])
            out.append(row)
        return {"columns":cols_meta,"rows":out,"total":total,"page":page,"page_size":page_size,"page_count":max(1,math.ceil(total/page_size))}

    @classmethod
    def quality_page(cls,search="",page=1,page_size=100):
        matrix=cls.matrix_page(search,page,page_size); rows=[]
        for src in matrix["rows"]:
            r=dict(src); issues=[]
            lines=[v for k,v in r.items() if k.startswith("line::")]
            cavities=[v for k,v in r.items() if k.startswith("cavity::")]
            mats=[v for k,v in r.items() if k.startswith("material::") and _clean(v)]
            if "✓" not in lines: issues.append("No confirmed line")
            if cavities and "✓" not in cavities: issues.append("No confirmed cavity")
            if not mats: issues.append("No material/component")
            for key,label in (("key_code","Mold/Key"),("casing_type","Casing"),("curing","Curing")):
                if not _clean(r.get(key)): issues.append(f"Missing {label}")
            r["issues"]=", ".join(issues) if issues else "Healthy"; r["issue_count"]=len(issues); rows.append(r)
        return {"rows":rows,"total":matrix["total"],"page":matrix["page"],"page_size":matrix["page_size"],"page_count":matrix["page_count"]}

    @classmethod
    def dashboard(cls):
        cls.ensure_schema()
        with engine.connect() as c:
            state=dict(c.execute(text("SELECT * FROM mpps_tyre_v35_sync_state WHERE id=1")).mappings().first() or {})
            items=int(c.execute(text("SELECT COUNT(*) FROM smds")).scalar() or 0)
            modules=[]
            try:
                modules=[dict(r) for r in c.execute(text("""SELECT module_key,module_name,purpose,status,
                    training_rows,history_days,readiness_score,model_version,last_trained_at
                    FROM mpps_tyre_ml_registry ORDER BY module_name""")).mappings().all()]
            except Exception: pass
        return {"item_count":items,"sync_state":state,"modules":modules}
