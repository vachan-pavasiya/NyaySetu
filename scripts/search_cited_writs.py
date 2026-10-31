"""Search for the 15 cited writs across Calcutta HC metadata in S3 (court 19_16).
"""
import re
import pyarrow.parquet as pq
import pyarrow.fs as fs

TARGETS = [
    {"type": "WPA", "num": "13757", "year": "2004", "raw": "WPA 13757 of 2004"},
    {"type": "WPA", "num": "3452", "year": "2014", "raw": "WPA 3452 of 2014"},
    {"type": "WPA", "num": "9009", "year": "2005", "raw": "WPA 9009 of 2005"},
    {"type": "WPA", "num": "5477", "year": "2022", "raw": "WPA 5477 of 2022"},
    {"type": "WPA", "num": "21513", "year": "2009", "raw": "WPA 21513 of 2009"},
    {"type": "WPA", "num": "2222", "year": "2022", "raw": "WPA 2222 of 2022"},
    {"type": "WPA", "num": "4835", "year": "2021", "raw": "WPA 4835 of 2021"},
    {"type": "WPA", "num": "7971", "year": "2021", "raw": "WPA 7971 of 2021"},
    {"type": "WPA", "num": "17378", "year": "2022", "raw": "WPA 17378 of 2022"},
    {"type": "WPA", "num": "4409", "year": "2022", "raw": "WPA 4409 of 2022"},
    {"type": "MAT", "num": "408", "year": "2022", "raw": "MAT 408 of 2022"},
    {"type": "WPLRT", "num": "888", "year": "2003", "raw": "WPLRT 888 of 2003"},
    {"type": "WPA", "num": "4466", "year": "2022", "raw": "WPA 4466 of 2022"},
    {"type": "WPA", "num": "18860", "year": "2021", "raw": "WPA 18860 of 2021"},
    {"type": "FMA", "num": "1879", "year": "2019", "raw": "FMA 1879 of 2019"},
]

def make_matcher(target):
    num = target["num"]
    yr = target["year"]
    ttype = target["type"]
    
    # Prefix variants: e.g. WPA, W.P.A., WP, W.P., WPA (W), WP(W)
    if ttype == "WPA":
        type_pat = r"(?:W\.?P\.?(?:A|C)?\.?(?:\s*\([A-Za-z0-9]+\))?)"
    else:
        type_pat = re.escape(ttype)
        
    pattern = re.compile(rf"\b{type_pat}[/\s\.]+{num}[/\s]+{yr}\b", re.IGNORECASE)
    # Also support exact pattern without type prefix if case_number has {num}/{yr}
    num_yr_pat = re.compile(rf"[^\d]{num}/{yr}\b")
    return target["raw"], pattern, num_yr_pat, target

matchers = [make_matcher(t) for t in TARGETS]

s3fs_client = fs.S3FileSystem(anonymous=True, region="ap-south-1")

benches = [
    "calcutta_appellate_side",
    "calcutta_original_side",
    "calcutta_circuit_bench_at_jalpaiguri",
    "calcutta_circuit_bench_at_port_blair",
]

found_records = {}

# Check decision years 2003 through 2023
for yr in range(2003, 2024):
    for bench in benches:
        path = f"indian-high-court-judgments/metadata/parquet/year={yr}/court=19_16/bench={bench}/metadata.parquet"
        try:
            pf = pq.ParquetFile(path, filesystem=s3fs_client)
        except Exception:
            continue
        
        # Read title, cnr, pdf_link, decision_date, pdf_exists
        table = pf.read(columns=["title", "cnr", "pdf_link", "decision_date", "pdf_exists", "court"])
        df = table.to_pandas()
        
        for idx, row in df.iterrows():
            title = str(row.get("title") or "")
            for raw_name, pat, num_yr_pat, t in matchers:
                if pat.search(title) or (t["type"] in title and num_yr_pat.search(title)):
                    if raw_name not in found_records:
                        found_records[raw_name] = []
                    found_records[raw_name].append({
                        "decision_year": yr,
                        "bench": bench,
                        "title": title,
                        "cnr": row.get("cnr"),
                        "pdf_link": row.get("pdf_link"),
                        "decision_date": str(row.get("decision_date")),
                        "pdf_exists": row.get("pdf_exists"),
                    })

print(f"\nSearch complete. Matches found for {len(found_records)} of {len(TARGETS)} targets:")
for raw, recs in found_records.items():
    print(f"\n--- {raw} (matched {len(recs)} orders) ---")
    for r in recs:
        print(f"  Year {r['decision_year']} [{r['bench']}]: {r['title'][:70]} | Date: {r['decision_date']} | pdf_exists: {r['pdf_exists']}")

missing = [t["raw"] for t in TARGETS if t["raw"] not in found_records]
print(f"\nNot found ({len(missing)} of {len(TARGETS)}):")
for m in missing:
    print(f"  {m}")

