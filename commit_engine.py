import json
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text
from backend.models import (
    Change_Request, Change_Log, Course, Student, Department, Faculty, Enrollment
)

def approve_or_reject_request(
    db: Session,
    request_id: int,
    action: str,  # 'APPROVE' or 'REJECT'
    user_id: int,
    reason: Optional[str] = None,
    selected_strategy: Optional[str] = None
) -> Dict[str, Any]:
    """
    Handles reviewer decision: approves or rejects a change request with explicit audit logging.
    """
    req = db.query(Change_Request).filter(Change_Request.request_id == request_id).first()
    if not req:
        raise ValueError(f"Change request #{request_id} not found.")

    if req.status == "COMMITTED":
        raise ValueError("Cannot modify an already committed change request.")

    action = action.upper()
    if action == "APPROVE":
        req.status = "APPROVED"
        if selected_strategy:
            req.selected_strategy = selected_strategy
        log_type = "REQUEST_APPROVED"
        note = f"Approved by User #{user_id}. Strategy: {req.selected_strategy or 'Default'}. Notes: {reason or 'Approved for safe application.'}"
    elif action == "REJECT":
        req.status = "REJECTED"
        req.rejection_reason = reason or "Rejected during faculty safety review."
        log_type = "REQUEST_REJECTED"
        note = f"Rejected by User #{user_id}. Reason: {req.rejection_reason}"
    else:
        raise ValueError("Action must be 'APPROVE' or 'REJECT'.")

    # Add Change_Log audit record
    log = Change_Log(
        request_id=req.request_id,
        user_id=user_id,
        change_type=log_type,
        previous_state=f"Status: PENDING_APPROVAL",
        new_state=f"Status: {req.status} | {note}",
        timestamp=datetime.utcnow()
    )
    db.add(log)
    db.commit()

    return {
        "request_id": req.request_id,
        "status": req.status,
        "selected_strategy": req.selected_strategy,
        "rejection_reason": req.rejection_reason,
        "message": f"Change request #{request_id} successfully {req.status.lower()}."
    }

def commit_approved_change(
    db: Session,
    request_id: int,
    user_id: int
) -> Dict[str, Any]:
    """
    Executes an approved change safely through controlled backend functions
    using an explicit transactional commit.
    Enforces that:
    1. Only APPROVED requests can be committed.
    2. REJECTED requests can NEVER be committed.
    3. Duplicate commits are strictly blocked.
    4. Records state change and commit event in Change_Log.
    """
    req = db.query(Change_Request).filter(Change_Request.request_id == request_id).first()
    if not req:
        raise ValueError(f"Change request #{request_id} not found.")

    if req.status == "COMMITTED":
        raise ValueError(f"Change request #{request_id} has already been committed. Duplicate commit blocked.")

    if req.status == "REJECTED":
        raise ValueError(f"Change request #{request_id} was rejected ({req.rejection_reason}) and cannot be committed.")

    if req.status != "APPROVED":
        raise ValueError(f"Change request #{request_id} is in '{req.status}' state. It must be APPROVED before committing.")

    # Execute inside transaction
    table = req.target_table
    rec_id = req.target_record_id
    col = req.target_column
    c_type = req.change_type
    strategy = req.selected_strategy or ""
    old_state = req.original_value or "N/A"
    new_state = req.proposed_value or "N/A"

    try:
        # Check if Strategy C (New Version) was selected for Course Credits
        if table == "courses" and col == "credits" and "Strategy C" in strategy:
            # Preserves CS101 at 4 credits, creates new version CS101-V2 with proposed credits
            new_course_id = f"{rec_id}-V2"
            existing_c = db.query(Course).filter(Course.course_id == rec_id).first()
            new_title = f"{existing_c.title if existing_c else 'Computer Science'} (Revised Curriculum)"
            new_credits = int(req.proposed_value)

            # Check if version already exists
            v2 = db.query(Course).filter(Course.course_id == new_course_id).first()
            if not v2:
                v2 = Course(
                    course_id=new_course_id,
                    title=new_title,
                    credits=new_credits,
                    dept_id=existing_c.dept_id if existing_c else "CS",
                    status="ACTIVE"
                )
                db.add(v2)
                db.flush()
            new_state = f"Created new version {new_course_id} with {new_credits} credits. Existing {rec_id} remains at {existing_c.credits} credits."

        elif c_type == "UPDATE":
            if table == "courses":
                c = db.query(Course).filter(Course.course_id == rec_id).first()
                if not c:
                    raise ValueError(f"Target course '{rec_id}' not found.")
                old_state = f"credits: {c.credits}, title: {c.title}"
                if col == "credits":
                    c.credits = int(req.proposed_value)
                elif col == "title":
                    c.title = req.proposed_value
                elif col == "status":
                    c.status = req.proposed_value
                new_state = f"credits: {c.credits}, title: {c.title}, status: {c.status}"

            elif table == "departments":
                d = db.query(Department).filter(Department.dept_id == rec_id).first()
                if not d:
                    raise ValueError(f"Target department '{rec_id}' not found.")
                old_state = f"budget: {d.budget}"
                if col == "budget":
                    d.budget = float(req.proposed_value)
                new_state = f"budget: {d.budget}"

            elif table == "students":
                s = db.query(Student).filter(Student.student_id == rec_id).first()
                if not s:
                    raise ValueError(f"Target student '{rec_id}' not found.")
                old_state = f"gpa: {s.gpa}, status: {s.status}"
                if col == "gpa":
                    s.gpa = float(req.proposed_value)
                elif col == "status":
                    s.status = req.proposed_value
                new_state = f"gpa: {s.gpa}, status: {s.status}"

        elif c_type == "DELETE":
            # For course deletion, if Strategy C (Soft delete) selected:
            if "Strategy C" in strategy or "Soft Delete" in strategy:
                c = db.query(Course).filter(Course.course_id == rec_id).first()
                if c:
                    old_state = f"status: {c.status}"
                    c.status = "INACTIVE"
                    new_state = "status: INACTIVE (Soft-deleted safely)"
            else:
                # Direct delete attempt
                if table == "courses":
                    c = db.query(Course).filter(Course.course_id == rec_id).first()
                    if c:
                        db.delete(c)
                        db.flush()

        elif c_type == "INSERT":
            if req.proposed_value:
                payload = json.loads(req.proposed_value)
                if table == "courses":
                    new_c = Course(**payload)
                    db.add(new_c)
                    db.flush()
                elif table == "students":
                    new_s = Student(**payload)
                    db.add(new_s)
                    db.flush()

        # Update Request Status
        req.status = "COMMITTED"

        # Record in Change_Log
        log = Change_Log(
            request_id=req.request_id,
            user_id=user_id,
            change_type=f"{c_type}_COMMITTED",
            previous_state=str(old_state),
            new_state=str(new_state),
            timestamp=datetime.utcnow()
        )
        db.add(log)
        db.commit()

        return {
            "status": "success",
            "request_id": req.request_id,
            "change_status": "COMMITTED",
            "previous_state": str(old_state),
            "new_state": str(new_state),
            "strategy_applied": req.selected_strategy,
            "message": f"Change request #{request_id} safely committed to database."
        }

    except Exception as e:
        db.rollback()
        # Record failed commit attempt in audit log
        fail_log = Change_Log(
            request_id=req.request_id,
            user_id=user_id,
            change_type=f"{c_type}_COMMIT_FAILED",
            previous_state=str(old_state),
            new_state=f"COMMIT_FAILED: {str(e)}",
            timestamp=datetime.utcnow()
        )
        db.add(fail_log)
        db.commit()
        raise e
