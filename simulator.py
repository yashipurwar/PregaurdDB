import sqlite3
import json
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from backend.database import DB_PATH
from backend.models import (
    WhatIf_Simulation, Simulation_Data, Impact_Analysis, Change_Request
)

def run_whatif_simulation(
    main_db_path: str,
    change_type: str,
    target_table: str,
    target_record_id: Optional[str] = None,
    target_column: Optional[str] = None,
    proposed_value: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Executes a genuine isolated what-if simulation in an in-memory SQLite clone.
    The original persistent database is NEVER modified during this analysis.
    """
    # 1. Clone disk database into isolated in-memory SQLite instance
    src_conn = sqlite3.connect(main_db_path)
    mem_conn = sqlite3.connect(":memory:")
    src_conn.backup(mem_conn)
    src_conn.close()
    mem_conn.row_factory = sqlite3.Row
    mem_cursor = mem_conn.cursor()

    # Enable foreign keys in the in-memory simulation instance
    mem_cursor.execute("PRAGMA foreign_keys = ON;")

    # 2. Capture BEFORE State: Student Credit Totals & Rule Statuses
    def compute_student_credits(cursor):
        query = """
            SELECT s.student_id, s.name, s.gpa, s.status,
                   COALESCE(SUM(c.credits), 0) AS total_credits,
                   GROUP_CONCAT(c.course_id || ' (' || c.credits || 'cr)', ', ') AS enrolled_courses
            FROM students s
            LEFT JOIN enrollments e ON s.student_id = e.student_id AND e.status = 'ENROLLED'
            LEFT JOIN courses c ON e.course_id = c.course_id
            GROUP BY s.student_id, s.name, s.gpa, s.status
            ORDER BY s.student_id;
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        student_data = {}
        for r in rows:
            credits = r["total_credits"]
            gpa = r["gpa"]
            is_fulltime = (credits >= 12)
            is_deanslist = (credits >= 14 and gpa >= 3.50)
            student_data[r["student_id"]] = {
                "student_id": r["student_id"],
                "name": r["name"],
                "gpa": gpa,
                "total_credits": credits,
                "enrolled_courses": r["enrolled_courses"] or "None",
                "is_fulltime": is_fulltime,
                "is_deanslist": is_deanslist
            }
        return student_data

    before_students = compute_student_credits(mem_cursor)

    # Fetch before state of target record
    before_record = None
    if target_record_id:
        pk_col = "course_id" if target_table == "courses" else ("student_id" if target_table == "students" else "dept_id")
        mem_cursor.execute(f"SELECT * FROM {target_table} WHERE {pk_col} = ?", (target_record_id,))
        row = mem_cursor.fetchone()
        if row:
            before_record = dict(row)

    # 3. Apply the proposed change inside the isolated in-memory DB
    constraint_violations = []
    simulation_status = "SUCCESS"
    execution_error = None
    after_record = None

    try:
        if change_type == "UPDATE":
            pk_col = "course_id" if target_table == "courses" else ("student_id" if target_table == "students" else "dept_id")
            val = proposed_value
            # Type casting if integer
            if target_column in ["credits", "min_credits"]:
                try:
                    val = int(proposed_value)
                except (ValueError, TypeError):
                    pass
            elif target_column in ["gpa", "budget"]:
                try:
                    val = float(proposed_value)
                except (ValueError, TypeError):
                    pass

            mem_cursor.execute(f"UPDATE {target_table} SET {target_column} = ? WHERE {pk_col} = ?", (val, target_record_id))
            mem_conn.commit()

            mem_cursor.execute(f"SELECT * FROM {target_table} WHERE {pk_col} = ?", (target_record_id,))
            row = mem_cursor.fetchone()
            if row:
                after_record = dict(row)

        elif change_type == "DELETE":
            pk_col = "course_id" if target_table == "courses" else ("student_id" if target_table == "students" else "dept_id")
            mem_cursor.execute(f"DELETE FROM {target_table} WHERE {pk_col} = ?", (target_record_id,))
            mem_conn.commit()

        elif change_type == "INSERT":
            if payload:
                cols = list(payload.keys())
                vals = [payload[k] for k in cols]
                placeholders = ", ".join(["?"] * len(cols))
                mem_cursor.execute(f"INSERT INTO {target_table} ({', '.join(cols)}) VALUES ({placeholders})", vals)
                mem_conn.commit()
                after_record = payload

        elif change_type == "SCHEMA_CHANGE":
            # Simulate column drop or rename
            # SQLite 3.35.5+ supports ALTER TABLE DROP COLUMN
            try:
                mem_cursor.execute(f"ALTER TABLE {target_table} DROP COLUMN {target_column}")
                mem_conn.commit()
            except Exception as se:
                constraint_violations.append({
                    "constraint_type": "SCHEMA_DEPENDENCY",
                    "constraint_name": f"drop_col_{target_column}",
                    "details": f"Cannot drop column '{target_column}' directly: {str(se)}"
                })

    except sqlite3.IntegrityError as ie:
        simulation_status = "CONSTRAINT_VIOLATION"
        err_msg = str(ie)
        execution_error = err_msg
        c_type = "UNKNOWN"
        if "CHECK constraint failed" in err_msg:
            c_type = "CHECK"
        elif "UNIQUE constraint failed" in err_msg:
            c_type = "UNIQUE"
        elif "FOREIGN KEY constraint failed" in err_msg:
            c_type = "FOREIGN KEY"
        elif "NOT NULL constraint failed" in err_msg:
            c_type = "NOT NULL"

        constraint_violations.append({
            "constraint_type": c_type,
            "constraint_name": f"Integrity_Violation_{c_type}",
            "details": f"Database integrity violation occurred: {err_msg}"
        })

    except Exception as ex:
        simulation_status = "ERROR"
        execution_error = str(ex)
        constraint_violations.append({
            "constraint_type": "EXECUTION_ERROR",
            "constraint_name": "General_Exception",
            "details": str(ex)
        })

    # 4. Capture AFTER State & Compare
    after_students = {}
    if simulation_status == "SUCCESS":
        try:
            after_students = compute_student_credits(mem_cursor)
        except Exception:
            # If schema change broke credit aggregation (e.g., column dropped)
            after_students = {}
            constraint_violations.append({
                "constraint_type": "REGISTERED_VIEW_FAILURE",
                "constraint_name": "vw_student_credit_summary_broken",
                "details": f"Dropping or modifying column '{target_column}' broke downstream credit aggregation view."
            })
    else:
        # If simulation threw error, after state is identical or blocked
        after_students = before_students

    # 5. Compile Diff and Impact Data
    student_diffs = []
    affected_students_count = 0
    rule_violations_detected = []

    for s_id, b_stu in before_students.items():
        a_stu = after_students.get(s_id, b_stu)
        credit_diff = a_stu["total_credits"] - b_stu["total_credits"]
        changed = (credit_diff != 0) or (a_stu["is_fulltime"] != b_stu["is_fulltime"]) or (a_stu["is_deanslist"] != b_stu["is_deanslist"])

        rule_impacts = []
        if b_stu["is_fulltime"] and not a_stu["is_fulltime"]:
            rule_impacts.append("LOSES_FULLTIME_STATUS (Dropped below 12 credits)")
            rule_violations_detected.append(f"Student {s_id} ({b_stu['name']}) loses Full-Time status (12 -> {a_stu['total_credits']} credits)")

        if b_stu["is_deanslist"] and not a_stu["is_deanslist"]:
            rule_impacts.append("LOSES_DEANSLIST_STATUS (Dropped below 14 credits)")
            rule_violations_detected.append(f"Student {s_id} ({b_stu['name']}) loses Dean's Honors List status (14 -> {a_stu['total_credits']} credits)")

        if changed:
            affected_students_count += 1
            student_diffs.append({
                "student_id": s_id,
                "name": b_stu["name"],
                "gpa": b_stu["gpa"],
                "before_credits": b_stu["total_credits"],
                "after_credits": a_stu["total_credits"],
                "credit_delta": credit_diff,
                "before_fulltime": b_stu["is_fulltime"],
                "after_fulltime": a_stu["is_fulltime"],
                "before_deanslist": b_stu["is_deanslist"],
                "after_deanslist": a_stu["is_deanslist"],
                "rule_impacts": rule_impacts
            })

    # Close temporary in-memory clone cleanly
    mem_conn.close()

    # Construct Simulation Result
    result = {
        "simulation_status": simulation_status,
        "is_safe": len(constraint_violations) == 0 and len(rule_violations_detected) == 0,
        "execution_error": execution_error,
        "target_table": target_table,
        "target_record_id": target_record_id,
        "target_column": target_column,
        "before_record": before_record,
        "after_record": after_record,
        "affected_students_count": affected_students_count,
        "affected_records_count": 1 if target_record_id else (len(payload) if payload else 0),
        "constraint_violations": constraint_violations,
        "rule_violations": rule_violations_detected,
        "student_diffs": student_diffs,
        "notice": "Simulation only — original database untouched."
    }

    return result

def persist_simulation_records(
    db: Session,
    analysis_id: int,
    change_type: str,
    sim_result: Dict[str, Any]
) -> WhatIf_Simulation:
    """
    Saves simulation summary and row-level diffs into WhatIf_Simulation and Simulation_Data.
    """
    sim = WhatIf_Simulation(
        analysis_id=analysis_id,
        operation_type=change_type,
        simulated_data_impact=json.dumps({
            "affected_students_count": sim_result["affected_students_count"],
            "student_diffs": sim_result["student_diffs"],
            "before_record": sim_result["before_record"],
            "after_record": sim_result["after_record"]
        }),
        simulated_constraint_impact=json.dumps(sim_result["constraint_violations"]),
        simulated_dependencies=json.dumps(sim_result["rule_violations"])
    )
    db.add(sim)
    db.commit()

    # Store individual simulation data records
    if sim_result["target_record_id"]:
        d1 = Simulation_Data(
            simulation_id=sim.simulation_id,
            table_name=sim_result["target_table"],
            record_id=str(sim_result["target_record_id"]),
            old_value=json.dumps(sim_result["before_record"]) if sim_result["before_record"] else None,
            new_value=json.dumps(sim_result["after_record"]) if sim_result["after_record"] else str(sim_result.get("proposed_value")),
            impact_type="DIRECT_MODIFIED" if sim_result["simulation_status"] == "SUCCESS" else "CONSTRAINT_BLOCKED"
        )
        db.add(d1)

    for diff in sim_result["student_diffs"]:
        d_stu = Simulation_Data(
            simulation_id=sim.simulation_id,
            table_name="students",
            record_id=diff["student_id"],
            old_value=f"Credits: {diff['before_credits']}",
            new_value=f"Credits: {diff['after_credits']}",
            impact_type="RULE_VIOLATED" if diff["rule_impacts"] else "INDIRECT_CALCULATED"
        )
        db.add(d_stu)

    db.commit()
    return sim
