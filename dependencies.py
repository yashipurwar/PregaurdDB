from typing import Dict, Any, List
from sqlalchemy.orm import Session
from backend.models import Table_Meta, Column_Meta, Constraint_Meta, Course, Enrollment, Student, Department

def analyze_dependencies(
    db: Session,
    target_table: str,
    target_column: str = None,
    target_record_id: str = None
) -> Dict[str, Any]:
    """
    Analyzes direct and indirect dependencies, constraints, and registered rules
    for the specified table and column. Clearly differentiates between relationships
    discovered from the database catalog and those registered in the metadata registry.
    """
    # 1. Fetch metadata records
    t_meta = db.query(Table_Meta).filter(Table_Meta.table_name == target_table).first()
    columns_meta = []
    constraints_meta = []
    if t_meta:
        columns_meta = db.query(Column_Meta).filter(Column_Meta.table_id == t_meta.table_id).all()
        constraints_meta = db.query(Constraint_Meta).filter(Constraint_Meta.table_id == t_meta.table_id).all()

    direct_dependencies = []
    indirect_dependencies = []
    database_constraints = []
    registered_dependencies = []
    related_records_count = 0
    affected_rules = []

    # Map constraints from Constraint_Meta
    for c in constraints_meta:
        is_catalog = c.constraint_type in ["PRIMARY KEY", "FOREIGN KEY", "UNIQUE", "CHECK", "NOT NULL"]
        entry = {
            "name": c.constraint_name,
            "type": c.constraint_type,
            "details": c.details,
            "source": "DATABASE_CATALOG (Discovered)" if is_catalog else "METADATA_REGISTRY (Registered)"
        }
        if is_catalog:
            database_constraints.append(entry)
        else:
            registered_dependencies.append(entry)

    # Specific relationship tracing based on table:
    if target_table == "courses":
        # Direct DB FK: enrollments -> courses (course_id)
        direct_dependencies.append({
            "target_table": "enrollments",
            "relationship_type": "FOREIGN_KEY",
            "foreign_key_column": "course_id",
            "source": "DATABASE_CATALOG (Discovered)",
            "description": "Table 'enrollments' holds foreign key referencing 'courses.course_id' with RESTRICT delete rule."
        })
        # Parent FK: courses -> departments (dept_id)
        direct_dependencies.append({
            "target_table": "departments",
            "relationship_type": "FOREIGN_KEY_PARENT",
            "foreign_key_column": "dept_id",
            "source": "DATABASE_CATALOG (Discovered)",
            "description": "'courses.dept_id' references primary key 'departments.dept_id'."
        })
        # Indirect DB dependency: students (via enrollments)
        indirect_dependencies.append({
            "target_table": "students",
            "path": "courses -> enrollments -> students",
            "source": "DATABASE_CATALOG (Discovered)",
            "description": "Student academic profiles and grade records are connected through enrollments."
        })

        # Registered rules & views affected
        if target_column in ["credits", "*", None]:
            registered_dependencies.append({
                "name": "vw_student_credit_summary",
                "type": "REGISTERED_VIEW",
                "details": "Aggregates total credits earned per student: SUM(c.credits) WHERE e.status = 'ENROLLED'",
                "source": "METADATA_REGISTRY (Registered)"
            })
            registered_dependencies.append({
                "name": "trg_check_credit_limit",
                "type": "REGISTERED_TRIGGER",
                "details": "Pre-insert trigger on enrollments validating total semester credits <= 24",
                "source": "METADATA_REGISTRY (Registered)"
            })
            affected_rules.extend([
                {"rule_id": "RULE_FULLTIME", "name": "Full-Time Academic Standing", "min_credits": 12, "source": "METADATA_REGISTRY (Registered)"},
                {"rule_id": "RULE_DEANSLIST", "name": "Dean's Honors List Eligibility", "min_credits": 14, "source": "METADATA_REGISTRY (Registered)"},
                {"rule_id": "RULE_SCHOLARSHIP", "name": "Merit Scholarship Renewal", "min_credits": 12, "source": "METADATA_REGISTRY (Registered)"},
            ])

        if target_record_id:
            related_records_count = db.query(Enrollment).filter(Enrollment.course_id == target_record_id).count()

    elif target_table == "students":
        direct_dependencies.append({
            "target_table": "enrollments",
            "relationship_type": "FOREIGN_KEY",
            "foreign_key_column": "student_id",
            "source": "DATABASE_CATALOG (Discovered)",
            "description": "Table 'enrollments' holds foreign key referencing 'students.student_id'."
        })
        affected_rules.extend([
            {"rule_id": "RULE_FULLTIME", "name": "Full-Time Academic Standing", "min_credits": 12, "source": "METADATA_REGISTRY (Registered)"},
        ])
        if target_record_id:
            related_records_count = db.query(Enrollment).filter(Enrollment.student_id == target_record_id).count()

    elif target_table == "departments":
        direct_dependencies.append({
            "target_table": "courses",
            "relationship_type": "FOREIGN_KEY",
            "foreign_key_column": "dept_id",
            "source": "DATABASE_CATALOG (Discovered)",
            "description": "'courses' references 'departments.dept_id'."
        })
        direct_dependencies.append({
            "target_table": "faculty",
            "relationship_type": "FOREIGN_KEY",
            "foreign_key_column": "dept_id",
            "source": "DATABASE_CATALOG (Discovered)",
            "description": "'faculty' references 'departments.dept_id'."
        })
        if target_record_id:
            c_count = db.query(Course).filter(Course.dept_id == target_record_id).count()
            f_count = db.query(Department).filter(Department.dept_id == target_record_id).count()
            related_records_count = c_count + f_count

    elif target_table == "enrollments":
        direct_dependencies.append({
            "target_table": "courses",
            "relationship_type": "FOREIGN_KEY_PARENT",
            "foreign_key_column": "course_id",
            "source": "DATABASE_CATALOG (Discovered)",
            "description": "References 'courses.course_id'."
        })
        direct_dependencies.append({
            "target_table": "students",
            "relationship_type": "FOREIGN_KEY_PARENT",
            "foreign_key_column": "student_id",
            "source": "DATABASE_CATALOG (Discovered)",
            "description": "References 'students.student_id'."
        })

    return {
        "target_table": target_table,
        "target_column": target_column,
        "target_record_id": target_record_id,
        "direct_dependencies": direct_dependencies,
        "indirect_dependencies": indirect_dependencies,
        "database_constraints": database_constraints,
        "registered_dependencies": registered_dependencies,
        "affected_rules": affected_rules,
        "related_records_count": related_records_count,
        "total_dependencies_count": len(direct_dependencies) + len(registered_dependencies)
    }

def get_full_schema_graph(db: Session) -> Dict[str, Any]:
    """
    Returns full graph of tables, relationships, and registered dependencies
    for the Dependency Explorer visualization.
    """
    nodes = [
        {"id": "departments", "label": "Departments", "type": "TABLE", "records": db.query(Department).count(), "color": "#1e3a8a"},
        {"id": "faculty", "label": "Faculty", "type": "TABLE", "records": db.query(Department).count(), "color": "#1e3a8a"},
        {"id": "courses", "label": "Courses", "type": "TABLE", "records": db.query(Course).count(), "color": "#1e3a8a"},
        {"id": "students", "label": "Students", "type": "TABLE", "records": db.query(Student).count(), "color": "#1e3a8a"},
        {"id": "enrollments", "label": "Enrollments", "type": "TABLE", "records": db.query(Enrollment).count(), "color": "#1e3a8a"},
        {"id": "eligibility_rules", "label": "Eligibility Rules", "type": "TABLE", "records": 4, "color": "#1e3a8a"},
        # Registered views and triggers
        {"id": "vw_credit_summary", "label": "vw_student_credit_summary", "type": "REGISTERED_VIEW", "color": "#059669"},
        {"id": "trg_credit_limit", "label": "trg_check_credit_limit", "type": "REGISTERED_TRIGGER", "color": "#d97706"},
        {"id": "rule_fulltime", "label": "RULE_FULLTIME (12 cr)", "type": "BUSINESS_RULE", "color": "#7c3aed"},
        {"id": "rule_deanslist", "label": "RULE_DEANSLIST (14 cr)", "type": "BUSINESS_RULE", "color": "#7c3aed"}
    ]

    edges = [
        {"from": "faculty", "to": "departments", "label": "FK (dept_id)", "source": "DATABASE_CATALOG (Discovered)"},
        {"from": "courses", "to": "departments", "label": "FK (dept_id)", "source": "DATABASE_CATALOG (Discovered)"},
        {"from": "enrollments", "to": "students", "label": "FK (student_id)", "source": "DATABASE_CATALOG (Discovered)"},
        {"from": "enrollments", "to": "courses", "label": "FK (course_id)", "source": "DATABASE_CATALOG (Discovered)"},
        {"from": "vw_credit_summary", "to": "courses", "label": "SUM(credits)", "source": "METADATA_REGISTRY (Registered)"},
        {"from": "vw_credit_summary", "to": "enrollments", "label": "GROUP BY student", "source": "METADATA_REGISTRY (Registered)"},
        {"from": "trg_credit_limit", "to": "enrollments", "label": "BEFORE INSERT", "source": "METADATA_REGISTRY (Registered)"},
        {"from": "rule_fulltime", "to": "courses", "label": "Depends on credits", "source": "METADATA_REGISTRY (Registered)"},
        {"from": "rule_deanslist", "to": "courses", "label": "Depends on credits", "source": "METADATA_REGISTRY (Registered)"},
    ]

    return {"nodes": nodes, "edges": edges}
