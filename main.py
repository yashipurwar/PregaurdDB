import json
import csv
import io
from datetime import datetime
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, Depends, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text, desc

from backend.database import get_db, DB_PATH, engine, Base
from backend.seed import seed_database
from backend.models import (
    User, Role, Database_Schema, Table_Meta, Column_Meta, Constraint_Meta,
    Change_Request, Impact_Analysis, WhatIf_Simulation, Simulation_Data,
    Risk_Assessment, Strategy, Recommendation, Change_Log,
    Course, Student, Faculty, Department, Enrollment, EligibilityRule
)
from backend.analyzer import parse_and_validate_change
from backend.dependencies import analyze_dependencies, get_full_schema_graph
from backend.simulator import run_whatif_simulation, persist_simulation_records
from backend.risk_engine import calculate_risk_assessment, DEFAULT_WEIGHTS
from backend.strategy_engine import generate_strategies_and_recommendation, persist_strategies_and_recommendation
from backend.commit_engine import approve_or_reject_request, commit_approved_change

app = FastAPI(
    title="PreGuard DB API",
    description="Predictive Database Integrity & Change-Safety Framework API",
    version="2.1.0"
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    # Initialize and auto-seed database if needed
    seed_database(force_reseed=False)

# ==========================================
# PYDANTIC SCHEMAS
# ==========================================

class AnalyzeChangeRequest(BaseModel):
    user_id: int = 2  # Default to Yashi Purwar
    change_type: str = Field(..., example="UPDATE")  # INSERT, UPDATE, DELETE, SCHEMA_CHANGE
    target_table: str = Field(..., example="courses")
    target_record_id: Optional[str] = Field(None, example="CS101")
    target_column: Optional[str] = Field(None, example="credits")
    proposed_value: Optional[str] = Field(None, example="3")
    description: Optional[str] = Field(None, example="Curriculum modernization reducing CS101 credit load from 4 to 3")
    payload: Optional[Dict[str, Any]] = None
    custom_weights: Optional[Dict[str, float]] = None

class RecalculateRiskRequest(BaseModel):
    weights: Dict[str, float]

class StrategySelectionRequest(BaseModel):
    selected_strategy: str

class ApprovalDecisionRequest(BaseModel):
    action: str = Field(..., example="APPROVE")  # APPROVE or REJECT
    user_id: int = 4  # Default to Prof. Saritha Murali (Reviewer)
    reason: Optional[str] = None
    selected_strategy: Optional[str] = None

class CommitRequest(BaseModel):
    user_id: int = 1  # Default to Admin

# ==========================================
# 1. DASHBOARD & SYSTEM METRICS
# ==========================================

@app.get("/api/dashboard/stats")
def get_dashboard_stats(db: Session = Depends(get_db)):
    total_requests = db.query(Change_Request).count()
    pending_approvals = db.query(Change_Request).filter(Change_Request.status == "PENDING_APPROVAL").count()
    approved_count = db.query(Change_Request).filter(Change_Request.status == "APPROVED").count()
    rejected_count = db.query(Change_Request).filter(Change_Request.status == "REJECTED").count()
    committed_count = db.query(Change_Request).filter(Change_Request.status == "COMMITTED").count()

    # Calculate real risk level counts from Risk_Assessment table
    assessments = db.query(Risk_Assessment).all()
    risk_counts = {"Low": 0, "Medium": 0, "High": 0, "Critical": 0}
    for ra in assessments:
        lvl = ra.risk_level
        if lvl in risk_counts:
            risk_counts[lvl] += 1

    # Recent change requests
    recent_requests = (
        db.query(Change_Request)
        .order_by(desc(Change_Request.created_at))
        .limit(6)
        .all()
    )
    req_list = []
    for r in recent_requests:
        ra = r.impact_analysis.risk_assessment if r.impact_analysis else None
        req_list.append({
            "request_id": r.request_id,
            "change_type": r.change_type,
            "target_table": r.target_table,
            "target_record_id": r.target_record_id,
            "target_column": r.target_column,
            "status": r.status,
            "selected_strategy": r.selected_strategy,
            "risk_score": ra.risk_score if ra else None,
            "risk_level": ra.risk_level if ra else "Unknown",
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M")
        })

    # Recent Audit Activity
    recent_logs = (
        db.query(Change_Log)
        .order_by(desc(Change_Log.timestamp))
        .limit(6)
        .all()
    )
    log_list = []
    for l in recent_logs:
        log_list.append({
            "log_id": l.log_id,
            "request_id": l.request_id,
            "user_name": l.user.name if l.user else f"User #{l.user_id}",
            "change_type": l.change_type,
            "previous_state": l.previous_state,
            "new_state": l.new_state,
            "timestamp": l.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        })

    return {
        "metrics": {
            "total_requests": total_requests,
            "pending_approvals": pending_approvals,
            "approved": approved_count,
            "rejected": rejected_count,
            "committed": committed_count,
            "risk_distribution": risk_counts
        },
        "default_weights": DEFAULT_WEIGHTS,
        "recent_requests": req_list,
        "recent_activity": log_list
    }

# ==========================================
# 2. PRESETS FOR DEMO WALKTHROUGH
# ==========================================

@app.get("/api/presets")
def get_demo_presets():
    return [
        {
            "id": "preset_cs101_credits",
            "title": "CS101 Credits Update (4 -> 3)",
            "subtitle": "Project Report Core Scenario",
            "change_type": "UPDATE",
            "target_table": "courses",
            "target_record_id": "CS101",
            "target_column": "credits",
            "proposed_value": "3",
            "description": "Curriculum committee proposal to reduce CS101 credit load from 4 to 3.",
            "highlight": "Affects 5 student enrollments; drops STU003 below 12cr Full-Time threshold."
        },
        {
            "id": "preset_delete_course_fk",
            "title": "Delete Course CS101 (FK Constraint)",
            "subtitle": "Referential Integrity Violation",
            "change_type": "DELETE",
            "target_table": "courses",
            "target_record_id": "CS101",
            "target_column": None,
            "proposed_value": None,
            "description": "Attempting to delete course CS101 while 5 active student enrollments reference it.",
            "highlight": "Triggers foreign key constraint restriction fk_enrollments_course."
        },
        {
            "id": "preset_unique_email_violation",
            "title": "Insert Student (Duplicate Email)",
            "subtitle": "Unique Constraint Violation",
            "change_type": "INSERT",
            "target_table": "students",
            "target_record_id": None,
            "target_column": "*",
            "proposed_value": json.dumps({"student_id": "STU999", "name": "Duplicate Candidate", "email": "aarav.s2026@vitstudent.ac.in", "gpa": 3.8}),
            "payload": {"student_id": "STU999", "name": "Duplicate Candidate", "email": "aarav.s2026@vitstudent.ac.in", "gpa": 3.8},
            "description": "Inserting a new student profile with an email address already registered to STU001.",
            "highlight": "Triggers UNIQUE constraint uq_student_email violation."
        },
        {
            "id": "preset_null_title_violation",
            "title": "Insert Course (Missing Required Title)",
            "subtitle": "NOT NULL Constraint Violation",
            "change_type": "INSERT",
            "target_table": "courses",
            "target_record_id": None,
            "target_column": "*",
            "proposed_value": json.dumps({"course_id": "CS999", "title": None, "credits": 4, "dept_id": "CS"}),
            "payload": {"course_id": "CS999", "title": None, "credits": 4, "dept_id": "CS"},
            "description": "Inserting a new course without providing a mandatory course title.",
            "highlight": "Triggers NOT NULL constraint violation on courses.title."
        },
        {
            "id": "preset_check_constraint_violation",
            "title": "Update Course Credits to 10",
            "subtitle": "CHECK Constraint Violation",
            "change_type": "UPDATE",
            "target_table": "courses",
            "target_record_id": "CS101",
            "target_column": "credits",
            "proposed_value": "10",
            "description": "Attempting to increase credits to 10, violating credit boundary check (credits <= 6).",
            "highlight": "Triggers CHECK constraint chk_course_credits failure."
        },
        {
            "id": "preset_schema_drop_credits",
            "title": "Simulate Dropping 'credits' Column",
            "subtitle": "Schema Change & View Dependency",
            "change_type": "SCHEMA_CHANGE",
            "target_table": "courses",
            "target_record_id": None,
            "target_column": "credits",
            "proposed_value": None,
            "description": "Simulating structural schema alteration dropping the credits column from courses table.",
            "highlight": "Detects registered view and triggers: breaks vw_student_credit_summary and eligibility rules."
        }
    ]

# ==========================================
# 3. CHANGE ANALYZER & COMPLETE PIPELINE
# ==========================================

@app.post("/api/changes/analyze")
def analyze_change(req: AnalyzeChangeRequest, db: Session = Depends(get_db)):
    """
    Core Pipeline:
    1. Parse & validate proposed change
    2. Analyze dependencies & constraints
    3. Run isolated what-if simulation (original DB untouched!)
    4. Compute transparent weighted risk assessment
    5. Evaluate alternative strategies & generate recommendation
    6. Persist results in PreGuard application database
    """
    # 1. Parse & Validate
    parsed = parse_and_validate_change(
        db=db,
        change_type=req.change_type,
        target_table=req.target_table,
        target_record_id=req.target_record_id,
        target_column=req.target_column,
        proposed_value=req.proposed_value,
        payload=req.payload
    )

    # 2. Dependency Tracing
    dep_data = analyze_dependencies(
        db=db,
        target_table=req.target_table,
        target_column=req.target_column,
        target_record_id=req.target_record_id
    )

    # 3. Run Isolated What-If Simulation
    sim_result = run_whatif_simulation(
        main_db_path=DB_PATH,
        change_type=req.change_type,
        target_table=req.target_table,
        target_record_id=req.target_record_id,
        target_column=req.target_column,
        proposed_value=req.proposed_value,
        payload=req.payload
    )

    # 4. Multi-Factor Risk Assessment
    risk_data = calculate_risk_assessment(
        change_type=req.change_type,
        target_table=req.target_table,
        target_column=req.target_column,
        dependencies_data=dep_data,
        simulation_result=sim_result,
        custom_weights=req.custom_weights
    )

    # 5. Alternative Strategy Evaluation & Recommendation
    strat_data = generate_strategies_and_recommendation(
        change_type=req.change_type,
        target_table=req.target_table,
        target_record_id=req.target_record_id or "",
        target_column=req.target_column or "",
        proposed_value=req.proposed_value or "",
        risk_assessment=risk_data,
        simulation_result=sim_result
    )

    # 6. Persist to PreGuard Application Tables
    change_req = Change_Request(
        user_id=req.user_id,
        change_type=req.change_type,
        target_table=req.target_table,
        target_record_id=req.target_record_id,
        target_column=req.target_column,
        original_value=parsed["original_value"],
        proposed_value=req.proposed_value or (json.dumps(req.payload) if req.payload else None),
        sql_statement=parsed["sql_preview"],
        description=req.description or f"Proposed {req.change_type} on {req.target_table}",
        status="PENDING_APPROVAL",
        selected_strategy=strat_data["recommended_strategy"]
    )
    db.add(change_req)
    db.commit()

    # Save Impact Analysis
    affected_tables = [req.target_table]
    if dep_data["direct_dependencies"]:
        affected_tables.extend([d["target_table"] for d in dep_data["direct_dependencies"]])

    ia = Impact_Analysis(
        request_id=change_req.request_id,
        affected_tables=json.dumps(list(set(affected_tables))),
        affected_columns=json.dumps([req.target_column] if req.target_column else []),
        affected_records=json.dumps([req.target_record_id] if req.target_record_id else []),
        dependency_impact=json.dumps(dep_data),
        constraint_violations=json.dumps(sim_result["constraint_violations"])
    )
    db.add(ia)
    db.commit()

    # Save Simulation & Simulation_Data
    persist_simulation_records(
        db=db,
        analysis_id=ia.analysis_id,
        change_type=req.change_type,
        sim_result=sim_result
    )

    # Save Risk Assessment
    ra = Risk_Assessment(
        analysis_id=ia.analysis_id,
        risk_score=risk_data["risk_score"],
        risk_level=risk_data["risk_level"],
        risk_factors=json.dumps(risk_data)
    )
    db.add(ra)
    db.commit()

    # Save Strategies & Recommendation
    persist_strategies_and_recommendation(
        db=db,
        analysis_id=ia.analysis_id,
        strategy_payload=strat_data
    )

    # Record Initial Audit Event
    log_entry = Change_Log(
        request_id=change_req.request_id,
        user_id=req.user_id,
        change_type="PROPOSED_AND_ANALYZED",
        previous_state=parsed["original_value"] or "N/A",
        new_state=req.proposed_value or "N/A",
        timestamp=datetime.utcnow()
    )
    db.add(log_entry)
    db.commit()

    return {
        "status": "success",
        "request_id": change_req.request_id,
        "parsed_operation": parsed,
        "dependency_analysis": dep_data,
        "whatif_simulation": sim_result,
        "risk_assessment": risk_data,
        "strategy_evaluation": strat_data,
        "change_request": {
            "request_id": change_req.request_id,
            "status": change_req.status,
            "created_at": change_req.created_at.strftime("%Y-%m-%d %H:%M:%S")
        }
    }

# ==========================================
# 4. CHANGE REQUESTS MANAGEMENT
# ==========================================

@app.get("/api/changes")
def list_change_requests(
    status: Optional[str] = None,
    change_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Change_Request).order_by(desc(Change_Request.created_at))
    if status and status != "ALL":
        query = query.filter(Change_Request.status == status)
    if change_type and change_type != "ALL":
        query = query.filter(Change_Request.change_type == change_type)

    results = []
    for r in query.all():
        ra = r.impact_analysis.risk_assessment if r.impact_analysis else None
        results.append({
            "request_id": r.request_id,
            "user_id": r.user_id,
            "user_name": r.user.name if r.user else f"User #{r.user_id}",
            "change_type": r.change_type,
            "target_table": r.target_table,
            "target_record_id": r.target_record_id,
            "target_column": r.target_column,
            "original_value": r.original_value,
            "proposed_value": r.proposed_value,
            "sql_statement": r.sql_statement,
            "description": r.description,
            "status": r.status,
            "selected_strategy": r.selected_strategy,
            "rejection_reason": r.rejection_reason,
            "risk_score": ra.risk_score if ra else None,
            "risk_level": ra.risk_level if ra else "Unknown",
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S")
        })
    return results

@app.get("/api/changes/{request_id}")
def get_change_request_details(request_id: int, db: Session = Depends(get_db)):
    r = db.query(Change_Request).filter(Change_Request.request_id == request_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Change request not found")

    ia = r.impact_analysis
    ra = ia.risk_assessment if ia else None
    sim = ia.whatif_simulation if ia else None
    strategies = ia.strategies if ia else []

    sim_data_records = []
    if sim:
        for sd in sim.simulation_data_records:
            sim_data_records.append({
                "table_name": sd.table_name,
                "record_id": sd.record_id,
                "old_value": sd.old_value,
                "new_value": sd.new_value,
                "impact_type": sd.impact_type
            })

    strat_list = []
    rec_obj = None
    for s in strategies:
        s_dict = {
            "strategy_id": s.strategy_id,
            "strategy_type": s.strategy_type,
            "description": s.description,
            "estimated_cost": s.estimated_cost,
            "estimated_time": s.estimated_time,
            "risk_score": s.risk_score,
            "recommendation": None
        }
        if s.recommendations:
            rec = s.recommendations[0]
            s_dict["recommendation"] = {
                "recommended_strategy": rec.recommended_strategy,
                "reason": rec.reason,
                "expected_outcome": rec.expected_outcome
            }
            rec_obj = s_dict["recommendation"]
        strat_list.append(s_dict)

    # Sort strategies by risk score
    strat_list.sort(key=lambda x: x["risk_score"])

    # Audit logs
    logs = []
    for l in r.change_logs:
        logs.append({
            "log_id": l.log_id,
            "user_name": l.user.name if l.user else f"User #{l.user_id}",
            "change_type": l.change_type,
            "previous_state": l.previous_state,
            "new_state": l.new_state,
            "timestamp": l.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        })

    return {
        "request": {
            "request_id": r.request_id,
            "user_id": r.user_id,
            "user_name": r.user.name if r.user else f"User #{r.user_id}",
            "change_type": r.change_type,
            "target_table": r.target_table,
            "target_record_id": r.target_record_id,
            "target_column": r.target_column,
            "original_value": r.original_value,
            "proposed_value": r.proposed_value,
            "sql_statement": r.sql_statement,
            "description": r.description,
            "status": r.status,
            "selected_strategy": r.selected_strategy,
            "rejection_reason": r.rejection_reason,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S")
        },
        "impact_analysis": {
            "affected_tables": json.loads(ia.affected_tables) if ia and ia.affected_tables else [],
            "affected_columns": json.loads(ia.affected_columns) if ia and ia.affected_columns else [],
            "affected_records": json.loads(ia.affected_records) if ia and ia.affected_records else [],
            "dependency_impact": json.loads(ia.dependency_impact) if ia and ia.dependency_impact else {},
            "constraint_violations": json.loads(ia.constraint_violations) if ia and ia.constraint_violations else []
        } if ia else None,
        "simulation": {
            "simulation_id": sim.simulation_id if sim else None,
            "data_impact": json.loads(sim.simulated_data_impact) if sim and sim.simulated_data_impact else {},
            "constraint_impact": json.loads(sim.simulated_constraint_impact) if sim and sim.simulated_constraint_impact else [],
            "dependencies_impact": json.loads(sim.simulated_dependencies) if sim and sim.simulated_dependencies else [],
            "data_records": sim_data_records
        } if sim else None,
        "risk_assessment": {
            "risk_score": ra.risk_score if ra else None,
            "risk_level": ra.risk_level if ra else None,
            "details": json.loads(ra.risk_factors) if ra and ra.risk_factors else {}
        } if ra else None,
        "strategies": strat_list,
        "recommendation": rec_obj,
        "audit_logs": logs
    }

# ==========================================
# 5. RISK RECALCULATION & STRATEGY SELECTION
# ==========================================

@app.post("/api/changes/{request_id}/recalculate-risk")
def recalculate_risk(
    request_id: int,
    req: RecalculateRiskRequest,
    db: Session = Depends(get_db)
):
    cr = db.query(Change_Request).filter(Change_Request.request_id == request_id).first()
    if not cr or not cr.impact_analysis:
        raise HTTPException(status_code=404, detail="Change request or analysis not found")

    ia = cr.impact_analysis
    dep_data = json.loads(ia.dependency_impact) if ia.dependency_impact else {}

    # Run fresh simulation to get precise factors
    sim_result = run_whatif_simulation(
        main_db_path=DB_PATH,
        change_type=cr.change_type,
        target_table=cr.target_table,
        target_record_id=cr.target_record_id,
        target_column=cr.target_column,
        proposed_value=cr.proposed_value
    )

    new_risk = calculate_risk_assessment(
        change_type=cr.change_type,
        target_table=cr.target_table,
        target_column=cr.target_column,
        dependencies_data=dep_data,
        simulation_result=sim_result,
        custom_weights=req.weights
    )

    # Update Risk_Assessment record
    ra = ia.risk_assessment
    if ra:
        ra.risk_score = new_risk["risk_score"]
        ra.risk_level = new_risk["risk_level"]
        ra.risk_factors = json.dumps(new_risk)
        db.commit()

    return new_risk

@app.post("/api/changes/{request_id}/select-strategy")
def select_strategy(
    request_id: int,
    req: StrategySelectionRequest,
    db: Session = Depends(get_db)
):
    cr = db.query(Change_Request).filter(Change_Request.request_id == request_id).first()
    if not cr:
        raise HTTPException(status_code=404, detail="Change request not found")

    cr.selected_strategy = req.selected_strategy
    db.commit()
    return {"status": "success", "selected_strategy": cr.selected_strategy}

# ==========================================
# 6. APPROVAL & CONTROLLED COMMIT
# ==========================================

@app.post("/api/changes/{request_id}/approve")
def handle_approval_decision(
    request_id: int,
    req: ApprovalDecisionRequest,
    db: Session = Depends(get_db)
):
    try:
        res = approve_or_reject_request(
            db=db,
            request_id=request_id,
            action=req.action,
            user_id=req.user_id,
            reason=req.reason,
            selected_strategy=req.selected_strategy
        )
        return res
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))

@app.post("/api/changes/{request_id}/commit")
def handle_commit(
    request_id: int,
    req: CommitRequest,
    db: Session = Depends(get_db)
):
    try:
        res = commit_approved_change(
            db=db,
            request_id=request_id,
            user_id=req.user_id
        )
        return res
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Commit transaction failed: {str(e)}")

# ==========================================
# 7. DEPENDENCY EXPLORER ENDPOINTS
# ==========================================

@app.get("/api/dependencies/graph")
def get_dependency_graph(db: Session = Depends(get_db)):
    return get_full_schema_graph(db)

@app.get("/api/dependencies/analyze")
def get_element_dependencies(
    table: str,
    column: Optional[str] = None,
    record_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    return analyze_dependencies(db, target_table=table, target_column=column, target_record_id=record_id)

# ==========================================
# 8. DATABASE EXPLORER & RESET
# ==========================================

@app.get("/api/database/tables")
def get_database_tables(db: Session = Depends(get_db)):
    """
    Returns list of tables with schemas, counts, and classification.
    """
    tables = [
        {"name": "courses", "category": "University Domain", "description": "Course catalog & credit configurations", "records": db.query(Course).count()},
        {"name": "students", "category": "University Domain", "description": "Student profiles and academic status", "records": db.query(Student).count()},
        {"name": "enrollments", "category": "University Domain", "description": "Student course registrations and grades", "records": db.query(Enrollment).count()},
        {"name": "departments", "category": "University Domain", "description": "Academic faculties and budgets", "records": db.query(Department).count()},
        {"name": "faculty", "category": "University Domain", "description": "Faculty instructors and advisors", "records": db.query(Faculty).count()},
        {"name": "eligibility_rules", "category": "University Domain", "description": "Academic thresholds and standing rules", "records": db.query(EligibilityRule).count()},
        # PreGuard Framework 16 Entities
        {"name": "change_requests", "category": "PreGuard Core", "description": "Proposed database changes & statuses", "records": db.query(Change_Request).count()},
        {"name": "impact_analyses", "category": "PreGuard Core", "description": "Predictive impact analysis outputs", "records": db.query(Impact_Analysis).count()},
        {"name": "whatif_simulations", "category": "PreGuard Core", "description": "Isolated simulation runs", "records": db.query(WhatIf_Simulation).count()},
        {"name": "simulation_data", "category": "PreGuard Core", "description": "Row-level before/after diffs", "records": db.query(Simulation_Data).count()},
        {"name": "risk_assessments", "category": "PreGuard Core", "description": "Multi-factor risk scores & levels", "records": db.query(Risk_Assessment).count()},
        {"name": "strategies", "category": "PreGuard Core", "description": "Evaluated modification strategies", "records": db.query(Strategy).count()},
        {"name": "recommendations", "category": "PreGuard Core", "description": "Recommended safe strategy & rationale", "records": db.query(Recommendation).count()},
        {"name": "change_logs", "category": "PreGuard Core", "description": "Persistent audit trail of actions", "records": db.query(Change_Log).count()},
        {"name": "users", "category": "PreGuard Core", "description": "System actors and reviewers", "records": db.query(User).count()},
        {"name": "roles", "category": "PreGuard Core", "description": "Role-based privileges", "records": db.query(Role).count()},
        {"name": "database_schemas", "category": "PreGuard Core", "description": "Target database metadata catalog", "records": db.query(Database_Schema).count()},
        {"name": "tables_meta", "category": "PreGuard Core", "description": "Registered table metadata", "records": db.query(Table_Meta).count()},
        {"name": "columns_meta", "category": "PreGuard Core", "description": "Registered column metadata", "records": db.query(Column_Meta).count()},
        {"name": "constraints_meta", "category": "PreGuard Core", "description": "Catalog constraints & registered rules", "records": db.query(Constraint_Meta).count()},
        {"name": "relational_schemas", "category": "PreGuard Core", "description": "Logical relational mappings", "records": db.query(Relational_Schema).count()},
        {"name": "physical_designs", "category": "PreGuard Core", "description": "Physical storage and index structures", "records": db.query(Physical_Design).count()},
    ]
    return tables

@app.get("/api/database/table/{table_name}")
def get_table_data(
    table_name: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db)
):
    # Safe lookup of permitted tables
    allowed_tables = {
        "courses": Course,
        "students": Student,
        "enrollments": Enrollment,
        "departments": Department,
        "faculty": Faculty,
        "eligibility_rules": EligibilityRule,
        "change_requests": Change_Request,
        "impact_analyses": Impact_Analysis,
        "whatif_simulations": WhatIf_Simulation,
        "simulation_data": Simulation_Data,
        "risk_assessments": Risk_Assessment,
        "strategies": Strategy,
        "recommendations": Recommendation,
        "change_logs": Change_Log,
        "users": User,
        "roles": Role,
        "database_schemas": Database_Schema,
        "tables_meta": Table_Meta,
        "columns_meta": Column_Meta,
        "constraints_meta": Constraint_Meta,
        "relational_schemas": Relational_Schema,
        "physical_designs": Physical_Design
    }

    if table_name not in allowed_tables:
        raise HTTPException(status_code=400, detail="Invalid table name")

    model = allowed_tables[table_name]
    total = db.query(model).count()
    rows = db.query(model).offset((page - 1) * page_size).limit(page_size).all()

    # Get column names and metadata
    columns = [c.name for c in model.__table__.columns]

    items = []
    for r in rows:
        row_dict = {}
        for col in columns:
            val = getattr(r, col)
            if isinstance(val, datetime):
                row_dict[col] = val.strftime("%Y-%m-%d %H:%M:%S")
            else:
                row_dict[col] = val
        items.append(row_dict)

    return {
        "table_name": table_name,
        "columns": columns,
        "total_records": total,
        "page": page,
        "page_size": page_size,
        "rows": items
    }

@app.post("/api/database/reset")
def reset_database_endpoint():
    """
    Resets and re-seeds the entire database with pristine demo records.
    """
    res = seed_database(force_reseed=True)
    return res

# ==========================================
# 9. AUDIT LOGS & REPORT EXPORT
# ==========================================

@app.get("/api/audit/logs")
def get_audit_logs(
    operation: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    q = db.query(Change_Log).order_by(desc(Change_Log.timestamp))
    if operation and operation != "ALL":
        q = q.filter(Change_Log.change_type.contains(operation))

    logs = []
    for l in q.limit(limit).all():
        ra = None
        if l.change_request and l.change_request.impact_analysis:
            ra = l.change_request.impact_analysis.risk_assessment

        logs.append({
            "log_id": l.log_id,
            "request_id": l.request_id,
            "user_name": l.user.name if l.user else f"User #{l.user_id}",
            "change_type": l.change_type,
            "previous_state": l.previous_state,
            "new_state": l.new_state,
            "risk_score": ra.risk_score if ra else "—",
            "risk_level": ra.risk_level if ra else "—",
            "timestamp": l.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        })
    return logs

@app.get("/api/audit/export/{request_id}")
def export_change_report(
    request_id: int,
    format: str = Query("json", regex="^(json|csv)$"),
    db: Session = Depends(get_db)
):
    """
    Exports a comprehensive change safety report as JSON or CSV.
    """
    r = db.query(Change_Request).filter(Change_Request.request_id == request_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Request not found")

    ia = r.impact_analysis
    ra = ia.risk_assessment if ia else None
    sim = ia.whatif_simulation if ia else None

    report = {
        "report_title": "PreGuard DB — Predictive Database Integrity & Change-Safety Audit Report",
        "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "request_details": {
            "request_id": r.request_id,
            "submitted_by": r.user.name if r.user else f"User #{r.user_id}",
            "change_type": r.change_type,
            "target_table": r.target_table,
            "target_record_id": r.target_record_id,
            "target_column": r.target_column,
            "original_value": r.original_value,
            "proposed_value": r.proposed_value,
            "sql_statement": r.sql_statement,
            "status": r.status,
            "selected_strategy": r.selected_strategy,
            "rejection_reason": r.rejection_reason
        },
        "risk_assessment": {
            "overall_score": ra.risk_score if ra else "N/A",
            "risk_level": ra.risk_level if ra else "N/A",
            "factors": json.loads(ra.risk_factors) if ra and ra.risk_factors else {}
        },
        "simulation_summary": {
            "simulation_id": sim.simulation_id if sim else "N/A",
            "data_impact": json.loads(sim.simulated_data_impact) if sim and sim.simulated_data_impact else {},
            "constraint_violations": json.loads(sim.simulated_constraint_impact) if sim and sim.simulated_constraint_impact else []
        }
    }

    if format == "json":
        return report

    # CSV Format
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["PreGuard DB Change-Safety Export Report"])
    writer.writerow(["Generated At", report["generated_at"]])
    writer.writerow([])
    writer.writerow(["Field", "Value"])
    for k, v in report["request_details"].items():
        writer.writerow([k, str(v)])
    writer.writerow(["Risk Score", str(report["risk_assessment"]["overall_score"])])
    writer.writerow(["Risk Level", str(report["risk_assessment"]["risk_level"])])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=preguard_report_req_{request_id}.csv"}
    )
