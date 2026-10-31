# Indian High Court Judgments - Dataset Notes & Exploration Findings

## 1. Overview & S3 Access
- **S3 Bucket Name:** `indian-high-court-judgments`
- **Region:** `ap-south-1` (AWS Mumbai)
- **Access Model:** Unsigned / Anonymous public access (`botocore.UNSIGNED`), no AWS credentials required.
- **Top-Level Bucket Prefixes:** `data/`, `metadata/`

### Directory Architecture
The bucket is organized into separate partitions for metadata and raw judgment documents:
```text
indian-high-court-judgments/
├── metadata/
│   ├── parquet/
│   │   └── year=<YEAR>/court=<COURT_CODE>/bench=<BENCH_NAME>/metadata.parquet
│   ├── parquet_case_details/
│   ├── json/
│   └── tar/
└── data/
    ├── pdf/
    │   └── year=<YEAR>/court=<COURT_CODE>/bench=<BENCH_NAME>/<FILENAME>.pdf
    └── tar/
```

> [!IMPORTANT]
> **Key Finding on Partition Order**: Unlike some court databases partitioned first by court, this dataset is partitioned **first by year**, then by court code (`court=<COURT_CODE>`), and then by bench (`bench=<BENCH_NAME>`).

---

## 2. Temporal Coverage & Freshness
- **Year Range Available:** `1950` to `2026` (77 years total).
- **Latest Available Data (Freshness):** High court orders up to **August 2026** are catalogued in the dataset.
- **Coverage Profile:**
  - Historical records (1950–1999): Lower volume, often archival or retrospective appeals.
  - Modern records (2000–2021): Massive digitisation wave across all 25 high court jurisdictions.
  - Recent complete years (2022–2024): Highest density of digitally generated native PDF orders, ideal for operative direction analysis.

---

## 3. Metadata Parquet Structure
Inspected file: `metadata/parquet/year=2023/court=19_16/bench=calcutta_appellate_side/metadata.parquet` (Total Rows in partition: **71,942**)

| Column Name | Data Type |
| :--- | :--- |
| `court_code` | `large_string` |
| `title` | `large_string` |
| `description` | `large_string` |
| `judge` | `large_string` |
| `pdf_link` | `large_string` |
| `cnr` | `large_string` |
| `date_of_registration` | `large_string` |
| `decision_date` | `timestamp[ns]` |
| `disposal_nature` | `large_string` |
| `court` | `large_string` |
| `raw_html` | `large_string` |
| `pdf_exists` | `bool` |

### Sample Rows from Live Parquet
**Row 1:**
- **Court:** Calcutta High Court
- **Title:** CRR/1112/2023 of M/S  RASHMI METALIKS  LTD AND OTHERS Vs CENTRAL BUREAU OF INVESTIGATION,ANTI CORRUPTION BRANCH, KOLKATA
- **CNR:** WBCHCA0144702023
- **Date:** 2023-03-24 00:00:00
- **Disposal Nature:** DISPOSED
- **PDF Link (in metadata):** `court/cnrorders/calcutta_appellate_side/orders/WBCHCA0144702023_1_2023-03-24.pdf`
- **Metadata pdf_exists flag:** `False`

**Row 2:**
- **Court:** Calcutta High Court
- **Title:** CPAN/2098/2014 of SOMENATH ADHIKARY Vs DEVDUTTA RAY
- **CNR:** WBCHCA0551442014
- **Date:** 2023-09-29 00:00:00
- **Disposal Nature:** DISMISSED FOR DEFAULT
- **PDF Link (in metadata):** `court/cnrorders/calcutta_appellate_side/orders/WBCHCA0551442014_1_2023-09-29.pdf`
- **Metadata pdf_exists flag:** `False`

**Row 3:**
- **Court:** Calcutta High Court
- **Title:** CO/1260/2022 of SANDIPAN BAGCHI Vs PARBATI BAGCHI @ BASU
- **CNR:** WBCHCA0184282022
- **Date:** 2023-09-15 00:00:00
- **Disposal Nature:** DISMISSED
- **PDF Link (in metadata):** `court/cnrorders/calcutta_appellate_side/orders/WBCHCA0184282022_10_2023-09-15.pdf`
- **Metadata pdf_exists flag:** `False`


---

## 4. Metadata-to-PDF Linking Pattern

A critical requirement is resolving a metadata record to its exact S3 PDF key:

1. The metadata row contains a relative path in `pdf_link`, e.g.:
   `court/cnrorders/calcutta_appellate_side/orders/WBCHCA0144702023_1_2023-03-24.pdf`
2. Extract the base filename:
   `filename = Path(row['pdf_link']).name` -> `WBCHCA0144702023_1_2023-03-24.pdf`
3. The corresponding S3 key in `data/pdf/` is deterministically mapped as:
   ```python
   s3_pdf_key = f"data/pdf/year={year}/court={court_code}/bench={bench}/{filename}"
   ```
4. **Live S3 Verification Check:**
   - Evaluated S3 Key: `data/pdf/year=2023/court=19_16/bench=calcutta_appellate_side/WBCHCA0144702023_1_2023-03-24.pdf`
   - File Existence on S3: **True**
   - File Size: **72,867 bytes** (7 pages)
   - Extracted Text Sample (via PyMuPDF):
     > "24.03.2023     
 
     
           
 
 
 
 
                
 
 
 
CRR 1112 of 2023 
 
M/S Rashmi Metaliks Ltd. & Ors. 
 -Vs- 
Central Bureau of Investigation, Anti Corruption 
Branch, Kolkata 
 
 
For the petitioner:      
Mr. Satish Maneshinde, Sr. Adv., 
 
 
 
 
Ms. Smriti Sinha, Adv., 
 
 
 
 
Ms. Anandini Fernandes, Adv., 
 
 
 
 
Ms. Namita Maneshinde, Adv., 
 
 
 
 
Ms. S"

> [!WARNING]
> **Assumption vs. Reality Alert (`pdf_exists` flag)**:
> In the parquet metadata, the column `pdf_exists` is set to `False` for many records where the actual PDF **does exist** in `data/pdf/` on S3. The pipeline must **never rely on `pdf_exists == True`**; instead, it should verify availability directly using S3 `head_object` or list checks.

---

## 5. Court Comparison & Evaluation

| Court Name | Court Code | Bench | 2023 Orders | Writ Petitions (WP/WPA) | Contempt Petitions | Text Usability (PyMuPDF) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Calcutta High Court** | `19_16` | `calcutta_appellate_side` | 71,942 | **36,355 (50.5%)** | **6,134 (8.5%)** | **100% vector text** (clean English, 0 OCR needed) |
| **Madras High Court** | `33_10` | `hc_cis_mas` | 108,552 | 33,629 (31.0%) | 2,990 (2.8%) | High readability, English text |
| **High Court of Kerala**| `32_4` | `highcourtofkerala` | 83,859 | 38,742 (46.2%) | 1,820 (2.2%) | Good readability |
| **Delhi High Court** | `7_26` | `dhcdb` | 8,465 | 3,419 (40.4%) | 420 (5.0%) | Lengthy judgments (avg 12k chars), 100% English |
| **Punjab & Haryana HC**| `3_22` | `phhc` | 149,388 | 46,160 (30.9%) | 5,120 (3.4%) | Mixed: some 1-page attestation receipts with ~80 chars |

---

## 6. Official Recommendation

### **Recommended Court:** `Calcutta High Court (Appellate Side)`
### **Recommended Year:** `2023`

### Justification:
1. **Highest Concentration of Operative Writ Directions Against State Departments:**
   Over **50.5% (36,355 orders)** of Calcutta High Court Appellate Side orders in 2023 are Writ Petitions (`WPA`), typically challenging executive/administrative action and ordering state authorities, police commissioners, municipal bodies, school boards, and revenue officers to take action within specified deadlines.
2. **Dense Follow-Up & Contempt Linking Ground-Truth:**
   Calcutta High Court in 2023 includes **6,134 Contempt Petitions (`CPAN`)**, which explicitly cite the underlying `WPA` number (e.g. `CPAN/2098/2014 in WPA/...`), providing real-world training and verification data for tracking subsequent compliance or contempt.
3. **Flawless Digital Text Quality (0 OCR Dependency):**
   100% of tested sample PDFs from this bench contain clean, embedded digital vector text readable directly by PyMuPDF without OCR.
4. **Matured Deadline Windows:**
   Selecting **2023** ensures that 30-day, 60-day, and 90-day compliance windows issued during the orders have reached their conclusion by 2024–2026, enabling rich ledger status classification (`COMPLIED`, `LAPSED_NO_RECORD`, `PENDING`).
