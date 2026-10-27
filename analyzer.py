import json
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from backend.models import Course, Student, Faculty, Department, Enrollment, EligibilityRule, Table_Meta

def parse_and_validate_change(
    db: Session,
    change_type: str,
    target_table: str,
    target_record_id: Optional[str] = None,
    target_column: Optional[str] = None,
    proposed_value: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Parses and validates a proposed database change before passing to dependency and simulation engines.
    Generates safe parameterized SQL preview.
    """
    change_type = change_type.upper()
    valid_types = ["INSERT", "UPDATE", "DELETE", "SCHEMA_CHANGE"]
    if change_type not in valid_types:
        raise ValueError(f"Unsupported change type: {change_type}. Must be one of {valid_types}")

    result = {
        "change_type": change_type,
        "target_table": target_table,
        "target_record_id": target_record_id,
        "target_column": target_column,
        "original_value": None,
        "proposed_value": proposed_value,
        "sql_preview": "",
        "parameters": {},
        "target_record_found": False,
        "is_valid": True,
        "error_message": None
    }

    # Fetch original value for UPDATE or DELETE
    if target_table == "courses":
        if target_record_id:
            c = db.query(Course).filter(Course.course_id == target_record_id).first()
            if c:
                result["target_record_found"] = True
                if target_column and hasattr(c, target_column):
                    result["original_value"] = str(getattr(c, target_column))
                else:
                    result["original_value"] = json.dumps({"course_id": c.course_id, "title": c.title, "credits": c.credits, "dept_id": c.dept_id, "status": c.status})
    elif target_table == "students":
        if target_record_id:
            s = db.query(Student).filter(Student.student_id == target_record_id).first()
            if s:
                result["target_record_found"] = True
                if target_column and hasattr(s, target_column):
                    result["original_value"] = str(getattr(s, target_column))
                else:
                    result["original_value"] = json.dumps({"student_id": s.student_id, "name": s.name, "email": s.email, "gpa": s.gpa, "status": s.status})
    elif target_table == "departments":
        if target_record_id:
            d = db.query(Department).filter(Department.dept_id == target_record_id).first()
            if d:
                result["target_record_found"] = True
                if target_column and hasattr(d, target_column):
                    result["original_value"] = str(getattr(d, target_column))
                else:
                    result["original_value"] = json.dumps({"dept_id": d.dept_id, "dept_name": d.dept_name, "budget": d.budget})
    elif target_table == "faculty":
        if target_record_id:
            f = db.query(Faculty).filter(Faculty.faculty_id == target_record_id).first()
            if f:
                result["target_record_found"] = True
                result["original_value"] = json.dumps({"faculty_id": f.faculty_id, "name": f.name, "email": f.email, "dept_id": f.dept_id})

    # Generate parameterized SQL preview
    if change_type == "UPDATE":
        pk_col = "course_id" if target_table == "courses" else ("student_id" if target_table == "students" else "dept_id")
        result["sql_preview"] = f"UPDATE {target_table} SET {target_column} = :proposed_val WHERE {pk_col} = :target_id;"
        result["parameters"] = {"proposed_val": proposed_value, "target_id": target_record_id}

    elif change_type == "DELETE":
        pk_col = "course_id" if target_table == "courses" else ("student_id" if target_table == "students" else "dept_id")
        result["sql_preview"] = f"DELETE FROM {target_table} WHERE {pk_col} = :target_id;"
        result["parameters"] = {"target_id": target_record_id}

    elif change_type == "INSERT":
        if payload:
            cols = ", ".join(payload.keys())
            placeholders = ", ".join([f":{k}" for k in payload.keys()])
            result["sql_preview"] = f"INSERT INTO {target_table} ({cols}) VALUES ({placeholders});"
            result["parameters"] = payload
            result["proposed_value"] = json.dumps(payload)
        else:
            result["sql_preview"] = f"-- INSERT statement for {target_table} (empty payload)"

    elif change_type == "SCHEMA_CHANGE":
        result["sql_preview"] = f"ALTER TABLE {target_table} DROP COLUMN {target_column}; -- [Simulated Schema Modification]"
        result["parameters"] = {"table": target_table, "column": target_column}

    return result
