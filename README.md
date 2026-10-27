# PreGuard DB: Predictive Database Integrity & Change-Safety Framework

> **Academic Project Submission**  
> **Course:** BACSE202 — Database Systems  
> **Institution:** School of Computer Science and Engineering, Vellore Institute of Technology (VIT), Vellore  
> **Students:** Yashi Purwar (25BCE2959) & Navya (25BCE2962)  
> **Faculty Guide:** Prof. Saritha Murali  

---

## 1. Executive Summary & Purpose

Modern relational databases underpin mission-critical applications across universities, hospitals, and financial institutions. However, standard Database Management Systems (DBMS) operate on an **"execute-then-handle-errors"** model: modifications (`INSERT`, `UPDATE`, `DELETE`, and schema alterations) are executed directly, and unintended side-effects—such as cascaded downstream invalidations, broken business rules, or silent student standing disqualifications—are only discovered after data corruption has already taken place.

**PreGuard DB** is a predictive database integrity and change-safety framework designed to intercept proposed database modifications **before** they are committed. It performs:
1. **Change Parsing & Parameterized SQL Preview** (Preventing unsanitized injection).
2. **Dependency & Constraint Tracing** (Discovered catalog constraints vs registered metadata rules).
3. **Isolated What-If Simulation** in an in-memory clone (Preserving the live database).
4. **Multi-Factor Weighted Risk Scoring** via Equation (1).
5. **Alternative Strategy Comparison & Ranking** (Strategies A, B, and C).
6. **Reviewer Approval Gate & Controlled Commit** inside ACID transactions.
7. **Persistent Audit Logging & JSON/CSV Reporting**.

---

## 2. Core Architecture & 16 Relational Entities

PreGuard DB implements the 16 core relational entities documented in the project report (Section 4.2, Table 4):

| # | Relational Entity | Primary Key | Foreign Keys / Details | Purpose |
|---|-------------------|-------------|------------------------|---------|
| 1 | `User` | `user_id` | `role_id` → `Role` | Person proposing or reviewing changes |
| 2 | `Role` | `role_id` | — | Role definitions (Admin, Analyst, Reviewer) |
| 3 | `Database_Schema` | `schema_id` | — | Target database metadata and catalog version |
| 4 | `Table_Meta` | `table_id` | `schema_id` → `Database_Schema` | Relational tables registered in target database |
| 5 | `Column_Meta` | `column_id` | `table_id` → `Table_Meta` | Registered columns, datatypes, and nullability |
| 6 | `Constraint_Meta` | `constraint_id` | `table_id` → `Table_Meta` | PK, FK, CHECK, UNIQUE, and registered views/triggers |
| 7 | `Change_Request` | `request_id` | `user_id` → `User` | Proposed change with lifecycle states |
| 8 | `Impact_Analysis` | `analysis_id` | `request_id` → `Change_Request` | Output of dependency tracing & constraint engine |
| 9 | `WhatIf_Simulation` | `simulation_id` | `analysis_id` → `Impact_Analysis` | Results of execution in isolated sandbox |
| 10 | `Simulation_Data` | `data_id` | `simulation_id` → `WhatIf_Simulation` | Row-level before/after diffs and rule flags |
| 11 | `Risk_Assessment` | `risk_id` | `analysis_id` → `Impact_Analysis` | Weighted risk score, level, and factor breakdown |
| 12 | `Strategy` | `strategy_id` | `analysis_id` → `Impact_Analysis` | Alternative modification options (A, B, C) |
| 13 | `Recommendation` | `recommendation_id` | `strategy_id` → `Strategy` | Optimal safety strategy with plain-language rationale |
| 14 | `Change_Log` | `log_id` | `request_id`, `user_id` | Immutable audit trail of states and decisions |
| 15 | `Relational_Schema` | `schema_id` | — | Logical relational mapping specifications |
| 16 | `Physical_Design` | `design_id` | `schema_id` → `Relational_Schema` | Storage engine, indexing, and WAL details |

### Simulated University Target Schema
- `departments`: Academic departments, buildings, budgets.
- `faculty`: Instructors, department affiliations, academic ranks.
- `courses`: Course titles, credit configurations (`CHECK(credits > 0 AND credits <= 6)`).
- `students`: Student profiles, GPAs (`CHECK(gpa >= 0.0 AND gpa <= 4.0)`), academic statuses.
- `enrollments`: Student registrations referencing courses and students (`UNIQUE(student_id, course_id, semester)`).
- `eligibility_rules`: Academic standing thresholds (e.g. `RULE_FULLTIME`: min 12 credits; `RULE_DEANSLIST`: min 14 credits).

---

## 3. Risk Assessment Engine (Equation 1)

PreGuard DB computes an explainable composite risk index on a `0.00 – 100.00` scale:

$$\text{Risk Score } R = (w_{\text{dep}} \cdot S_{\text{dep}}) + (w_{\text{con}} \cdot S_{\text{con}}) + (w_{\text{biz}} \cdot S_{\text{biz}}) + (w_{\text{data}} \cdot S_{\text{data}}) + (w_{\text{cx}} \cdot S_{\text{cx}})$$

### Default Weights (Total = 100%):
- **Dependency Impact ($w_{\text{dep}} = 30\%$)**: Traces referencing foreign keys, registered views (`vw_student_credit_summary`), and triggers.
- **Constraint Risk ($w_{\text{con}} = 25\%$)**: Detects PK, FK, CHECK, UNIQUE, and NOT NULL violations.
- **Business Rule Risk ($w_{\text{biz}} = 20\%$)**: Identifies students whose total credits drop below critical academic thresholds (e.g. 12 credits).
- **Data Impact ($w_{\text{data}} = 15\%$)**: Measures volume of directly modified or indirectly recalculated records.
- **Change Complexity ($w_{\text{cx}} = 10\%$)**: Intrinsic complexity of the SQL operation.

### Configurable Threshold Bands:
- **Low (0 – 25)**: Safe to proceed. No integrity conflicts.
- **Medium (26 – 50)**: Review recommended. Minor dependent rule alignment needed.
- **High (51 – 75)**: Significant dependency or student standing violation predicted. Strategy modification required.
- **Critical (76 – 100)**: Hard constraint violation (FK/CHECK/UNIQUE) or widespread corruption. Block change.

---

## 4. Alternative Strategies (CS101 Scenario)

For the flagship scenario where **Course CS101 credits are proposed to change from 4 to 3**:

1. **Strategy A: Direct Update**
   - *Action:* `UPDATE courses SET credits = 3 WHERE course_id = 'CS101'`
   - *Risk:* **High (68.5)**
   - *Consequence:* All 5 enrolled students lose 1 credit. Rohan Verma (STU003) drops to 11 credits and immediately loses Full-Time Student Standing.
2. **Strategy B: Update Dependent Rules First**
   - *Action:* Revise eligibility thresholds or grant grandfathered waivers first, then update course.
   - *Risk:* **Medium (38.0)**
   - *Consequence:* Protects student standing, but historical transcripts are still altered.
3. **Strategy C: Create a New Course Version (RECOMMENDED)**
   - *Action:* Keep existing CS101 at 4 credits for current students; introduce `CS101-V2` with 3 credits for upcoming terms.
   - *Risk:* **Low (14.5)**
   - *Consequence:* 100% backward integrity preserved. Zero student standing disruptions.

---

## 5. Technology Stack & Prerequisites

- **Frontend:** React 19 + Vite 8 + Lucide Icons + Custom Academic CSS Dashboard.
- **Backend:** Python 3.10+ (FastAPI + Pydantic v2 + Uvicorn).
- **Database:** SQLite 3 with SQLAlchemy 2.0 (Foreign Keys strictly enabled).
- **Testing:** Pytest 8+ (12 comprehensive verification test cases).

All dependencies run 100% locally on standard laptops without cloud APIs, paid tokens, or GPUs.

---

## 6. Execution Instructions (Windows Terminal)

Open two terminal windows in the project directory: `C:\Users\Ruchi Purwar\Desktop\Databse_[jt`

### Terminal 1: Backend Server (FastAPI)
```powershell
# Navigate to project folder
Set-Location -LiteralPath "C:\Users\Ruchi Purwar\Desktop\Databse_[jt"

# Run backend server
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```
*(Keep Terminal 1 open. It serves API endpoints at `http://127.0.0.1:8000` and Swagger docs at `http://127.0.0.1:8000/docs`)*

### Terminal 2: Frontend Dashboard (React + Vite)
```powershell
# Navigate to frontend folder
Set-Location -LiteralPath "C:\Users\Ruchi Purwar\Desktop\Databse_[jt\frontend"

# Start Vite dev server
npm run dev
```
*(Keep Terminal 2 open. It serves the dashboard at `http://localhost:5173`)*

### Quick One-Click Launchers:
Alternatively, simply double-click the included batch scripts:
- `start_backend.bat`
- `start_frontend.bat`
- `run_tests.bat`

---

## 7. Running Backend Tests

To run the automated verification suite covering all 12 academic test cases:
```powershell
Set-Location -LiteralPath "C:\Users\Ruchi Purwar\Desktop\Databse_[jt"
python -m pytest tests/test_preguard.py -v
```

All 12 tests pass successfully:
1. `test_01_cs101_credits_change`: Identifies 5 affected students and rule violation.
2. `test_02_delete_course_with_enrollments`: Blocks delete on FK constraint.
3. `test_03_insert_violates_unique_constraint`: Catches duplicate student email.
4. `test_04_insert_violates_not_null_constraint`: Catches missing required title.
5. `test_05_update_violates_check_constraint`: Catches credits exceeding limit (> 6).
6. `test_06_schema_change_detects_registered_dependency`: Detects view & rule dependency.
7. `test_07_risk_weights_add_to_100_percent`: Validates weight normalization.
8. `test_08_risk_score_formula_calculation`: Verifies Equation (1) numerical accuracy.
9. `test_09_simulation_preserves_original_data`: Verifies isolated sandbox leaves disk untouched.
10. `test_10_rejected_requests_cannot_be_committed`: Enforces reviewer approval gate.
11. `test_11_approved_changes_recorded_in_audit_log`: Verifies persistent audit logging.
12. `test_12_repeated_commit_requests_blocked`: Prevents duplicate commits.

---

## 8. Final Review Demonstration Walkthrough

When presenting to faculty guide **Prof. Saritha Murali**, follow this 14-step sequence:

1. **Dashboard Overview:** Open `http://localhost:5173`. Explain the purpose of PreGuard DB and point to the live metric cards (Total Requests, Pending Approvals, Risk Distribution).
2. **Open Change Analyzer:** Click *Change Analyzer* in the sidebar.
3. **Select CS101 Preset:** Click the preset button **"CS101 Credits Update (4 -> 3)"**. Notice the auto-filled form and the live parameterized SQL preview.
4. **Run Analysis:** Click **"Run PreGuard Analysis"**. The backend processes the change through the 10-step safety pipeline.
5. **Show Dependencies & Affected Enrollments:** Review the *Dependencies Traced* card showing 5 active student enrollments connected to CS101 and the registered view `vw_student_credit_summary`.
6. **Open What-If Simulator:** Click *View What-If Diffs* or navigate to *What-If Simulator*. Point out the banner: `"Simulation only — original data unchanged"`.
7. **Demonstrate Row-Level Impact:** Show the student table diff:
   - Rohan Verma (`STU003`) credit total drops from 12 to 11.
   - Status changes from **Compliant (>=12)** to **NON-COMPLIANT (<12)**.
   - Rule violation triggered: `RULE_FULLTIME`.
8. **Explain Weighted Risk Score:** Navigate to *Risk Assessment*. Explain Equation (1) ($R = 68.50 \to \text{High Risk}$). Adjust the slider weights in real-time to demonstrate sensitivity analysis!
9. **Compare Strategies:** Navigate to *Strategy Comparison*. Show the comparison matrix for Strategy A (Direct Update), Strategy B (Update Rules First), and Strategy C (New Course Version).
10. **Select Strategy C:** Click **"Select & Submit for Approval"** on Strategy C (Low Risk 14.5).
11. **Approve at Approval Gate:** Navigate to *Change Requests*. Show the request in `PENDING_APPROVAL` status. Click **"Approve"** as reviewer Prof. Saritha Murali.
12. **Controlled Safe Commit:** Click **"Commit"**. The backend executes an ACID transaction, creates version `CS101-V2`, and logs the commit.
13. **Verify Database State:** Navigate to *Database Explorer*. Open table `courses`. Confirm that original `CS101` remains safely at 4 credits for enrolled students, while `CS101-V2` has been added with 3 credits.
14. **Verify Audit Trail:** Navigate to *Audit Logs*. Show the immutable event history and click **"Export Audit (JSON)"** or **"Export Audit (CSV)"** to demonstrate reporting compliance.
