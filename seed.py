import json
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from backend.database import engine, Base, SessionLocal
from backend.models import (
    Department, Faculty, Course, Student, Enrollment, EligibilityRule,
    User, Role, Database_Schema, Table_Meta, Column_Meta, Constraint_Meta,
    Change_Request, Impact_Analysis, WhatIf_Simulation, Simulation_Data,
    Risk_Assessment, Strategy, Recommendation, Change_Log,
    Relational_Schema, Physical_Design
)

def init_db():
    Base.metadata.create_all(bind=engine)

def seed_database(force_reseed=False):
    init_db()
    db: Session = SessionLocal()
    try:
        # Check if already seeded
        existing_courses = db.query(Course).count()
        if existing_courses > 0 and not force_reseed:
            return {"status": "already_seeded", "message": "Database already contains seed data."}

        if force_reseed:
            # Clear all tables cleanly
            Base.metadata.drop_all(bind=engine)
            Base.metadata.create_all(bind=engine)

        # ----------------------------------------------------
        # 1. ROLES & USERS
        # ----------------------------------------------------
        r_admin = Role(role_id=1, role_name="Database Administrator", description="Full schema control, change commit authority")
        r_analyst = Role(role_id=2, role_name="Database Analyst", description="Proposes changes, runs what-if simulations and risk scoring")
        r_reviewer = Role(role_id=3, role_name="Faculty Reviewer / Guide", description="Inspects predictive analyses and approves/rejects change requests")
        db.add_all([r_admin, r_analyst, r_reviewer])
        db.commit()

        u_admin = User(user_id=1, name="System Administrator", email="admin@preguard.edu", role_id=1)
        u_yashi = User(user_id=2, name="Yashi Purwar (25BCE2959)", email="yashi.purwar@vitstudent.ac.in", role_id=2)
        u_navya = User(user_id=3, name="Navya (25BCE2962)", email="navya@vitstudent.ac.in", role_id=2)
        u_guide = User(user_id=4, name="Prof. Saritha Murali", email="saritha.murali@vit.ac.in", role_id=3)
        db.add_all([u_admin, u_yashi, u_navya, u_guide])
        db.commit()

        # ----------------------------------------------------
        # 2. UNIVERSITY DOMAIN DATA
        # ----------------------------------------------------
        d_cs = Department(dept_id="CS", dept_name="Computer Science & Engineering", building="Technology Tower 4", budget=450000.0)
        d_math = Department(dept_id="MATH", dept_name="Department of Mathematics", building="Science Block 2", budget=180000.0)
        d_eng = Department(dept_id="ENG", dept_name="Humanities & Languages", building="Silver Jubilee Tower", budget=120000.0)
        d_phys = Department(dept_id="PHYS", dept_name="Physics & Applied Sciences", building="Science Block 1", budget=160000.0)
        db.add_all([d_cs, d_math, d_eng, d_phys])
        db.commit()

        fac_1 = Faculty(faculty_id="FAC01", name="Prof. Saritha Murali", email="saritha.murali@vit.ac.in", dept_id="CS", title="Associate Professor Senior")
        fac_2 = Faculty(faculty_id="FAC02", name="Dr. K. Raman", email="k.raman@vit.ac.in", dept_id="CS", title="Professor")
        fac_3 = Faculty(faculty_id="FAC03", name="Dr. Arvind Sharma", email="a.sharma@vit.ac.in", dept_id="MATH", title="Assistant Professor")
        fac_4 = Faculty(faculty_id="FAC04", name="Dr. Malini Iyer", email="m.iyer@vit.ac.in", dept_id="PHYS", title="Associate Professor")
        db.add_all([fac_1, fac_2, fac_3, fac_4])
        db.commit()

        # Courses
        c_cs101 = Course(course_id="CS101", title="Computer Programming & Problem Solving", credits=4, dept_id="CS", status="ACTIVE")
        c_cs201 = Course(course_id="CS201", title="Data Structures and Algorithms", credits=4, dept_id="CS", status="ACTIVE")
        c_cs301 = Course(course_id="CS301", title="Database Systems", credits=3, dept_id="CS", status="ACTIVE")
        c_math101 = Course(course_id="MATH101", title="Calculus & Linear Algebra", credits=4, dept_id="MATH", status="ACTIVE")
        c_eng101 = Course(course_id="ENG101", title="Technical Communication", credits=3, dept_id="ENG", status="ACTIVE")
        c_phys101 = Course(course_id="PHYS101", title="Engineering Physics & Optics", credits=4, dept_id="PHYS", status="ACTIVE")
        db.add_all([c_cs101, c_cs201, c_cs301, c_math101, c_eng101, c_phys101])
        db.commit()

        # Students
        s1 = Student(student_id="STU001", name="Aarav Sharma", email="aarav.s2026@vitstudent.ac.in", gpa=3.82, status="ACTIVE")
        s2 = Student(student_id="STU002", name="Priya Patel", email="priya.p2026@vitstudent.ac.in", gpa=3.91, status="ACTIVE")
        s3 = Student(student_id="STU003", name="Rohan Verma", email="rohan.v2026@vitstudent.ac.in", gpa=3.42, status="ACTIVE")
        s4 = Student(student_id="STU004", name="Ananya Iyer", email="ananya.i2026@vitstudent.ac.in", gpa=3.75, status="ACTIVE")
        s5 = Student(student_id="STU005", name="Vikram Malhotra", email="vikram.m2026@vitstudent.ac.in", gpa=2.85, status="ACTIVE")
        s6 = Student(student_id="STU006", name="Sneha Reddy", email="sneha.r2026@vitstudent.ac.in", gpa=3.65, status="ACTIVE")
        db.add_all([s1, s2, s3, s4, s5, s6])
        db.commit()

        # Enrollments:
        # STU001: CS101(4) + CS201(4) + CS301(3) + MATH101(4) = 15 credits
        # STU002: CS101(4) + CS301(3) + ENG101(3) + PHYS101(4) = 14 credits (Dean's list boundary: 14)
        # STU003: CS101(4) + CS201(4) + MATH101(4) = 12 credits (Full-time boundary: 12)
        # STU004: CS101(4) + CS201(4) + CS301(3) + MATH101(4) + PHYS101(4) = 19 credits
        # STU005: CS101(4) + ENG101(3) = 7 credits
        # STU006 (Control - not in CS101): CS201(4) + CS301(3) + MATH101(4) = 11 credits
        enrollments = [
            Enrollment(student_id="STU001", course_id="CS101", semester="Fall 2026", grade="A", status="ENROLLED"),
            Enrollment(student_id="STU001", course_id="CS201", semester="Fall 2026", grade="A-", status="ENROLLED"),
            Enrollment(student_id="STU001", course_id="CS301", semester="Fall 2026", grade="IP", status="ENROLLED"),
            Enrollment(student_id="STU001", course_id="MATH101", semester="Fall 2026", grade="B+", status="ENROLLED"),

            Enrollment(student_id="STU002", course_id="CS101", semester="Fall 2026", grade="A", status="ENROLLED"),
            Enrollment(student_id="STU002", course_id="CS301", semester="Fall 2026", grade="IP", status="ENROLLED"),
            Enrollment(student_id="STU002", course_id="ENG101", semester="Fall 2026", grade="A", status="ENROLLED"),
            Enrollment(student_id="STU002", course_id="PHYS101", semester="Fall 2026", grade="A-", status="ENROLLED"),

            Enrollment(student_id="STU003", course_id="CS101", semester="Fall 2026", grade="B", status="ENROLLED"),
            Enrollment(student_id="STU003", course_id="CS201", semester="Fall 2026", grade="B+", status="ENROLLED"),
            Enrollment(student_id="STU003", course_id="MATH101", semester="Fall 2026", grade="B", status="ENROLLED"),

            Enrollment(student_id="STU004", course_id="CS101", semester="Fall 2026", grade="A", status="ENROLLED"),
            Enrollment(student_id="STU004", course_id="CS201", semester="Fall 2026", grade="A", status="ENROLLED"),
            Enrollment(student_id="STU004", course_id="CS301", semester="Fall 2026", grade="IP", status="ENROLLED"),
            Enrollment(student_id="STU004", course_id="MATH101", semester="Fall 2026", grade="A-", status="ENROLLED"),
            Enrollment(student_id="STU004", course_id="PHYS101", semester="Fall 2026", grade="A", status="ENROLLED"),

            Enrollment(student_id="STU005", course_id="CS101", semester="Fall 2026", grade="C+", status="ENROLLED"),
            Enrollment(student_id="STU005", course_id="ENG101", semester="Fall 2026", grade="B", status="ENROLLED"),

            Enrollment(student_id="STU006", course_id="CS201", semester="Fall 2026", grade="A-", status="ENROLLED"),
            Enrollment(student_id="STU006", course_id="CS301", semester="Fall 2026", grade="IP", status="ENROLLED"),
            Enrollment(student_id="STU006", course_id="MATH101", semester="Fall 2026", grade="B+", status="ENROLLED"),
        ]
        db.add_all(enrollments)
        db.commit()

        # Eligibility Rules
        r1 = EligibilityRule(
            rule_id="RULE_FULLTIME",
            rule_name="Full-Time Academic Standing",
            min_credits=12,
            description="Students must enroll in at least 12 credits to maintain full-time student status and hostel/visa privileges."
        )
        r2 = EligibilityRule(
            rule_id="RULE_DEANSLIST",
            rule_name="Dean's Honors List Eligibility",
            min_credits=14,
            description="Requires min 14 credits enrolled and cumulative GPA >= 3.50 for Dean's Commendation."
        )
        r3 = EligibilityRule(
            rule_id="RULE_SCHOLARSHIP",
            rule_name="Merit Scholarship Renewal",
            min_credits=12,
            description="Requires continuous full-time enrollment of at least 12 credits per semester."
        )
        r4 = EligibilityRule(
            rule_id="RULE_GRAD_CLEAR",
            rule_name="Graduation Credit Threshold",
            min_credits=18,
            description="Minimum 18 credits registered in senior year for graduation clearance audit."
        )
        db.add_all([r1, r2, r3, r4])
        db.commit()

        # ----------------------------------------------------
        # 3. SCHEMA METADATA REGISTRY (16-ENTITY METADATA)
        # ----------------------------------------------------
        schema_meta = Database_Schema(
            schema_id=1,
            database_name="VIT_University_SIM",
            version="2.1.0",
            description="Simulated University Academic & Enrollment Database for Change-Safety Prototype"
        )
        db.add(schema_meta)
        db.commit()

        rel_schema = Relational_Schema(
            schema_id=1,
            database_name="VIT_University_SIM",
            version="2.1.0",
            description="Logical relational schema: 6 relational tables, referential integrities and business rules"
        )
        phys_design = Physical_Design(
            design_id=1,
            schema_id=1,
            storage_details="SQLite B-Tree storage engine with Write-Ahead Logging (WAL) and synchronous=NORMAL",
            index_details="B-Tree indexes on PKs, FKs (enrollments.student_id, enrollments.course_id), Unique emails",
            partitioning_details="Logical partitioning by academic semester for enrollment and historical audits"
        )
        db.add_all([rel_schema, phys_design])
        db.commit()

        # Register metadata for each table:
        table_defs = [
            ("departments", "Academic departments within the university", [
                ("dept_id", "VARCHAR(10)", False, None),
                ("dept_name", "VARCHAR(100)", False, None),
                ("building", "VARCHAR(50)", True, None),
                ("budget", "REAL", True, "100000.0")
            ], [
                ("PRIMARY KEY", "pk_departments", "dept_id is primary key"),
            ]),
            ("faculty", "Faculty members and instructors", [
                ("faculty_id", "VARCHAR(10)", False, None),
                ("name", "VARCHAR(100)", False, None),
                ("email", "VARCHAR(100)", False, None),
                ("dept_id", "VARCHAR(10)", False, None),
                ("title", "VARCHAR(50)", True, "'Assistant Professor'")
            ], [
                ("PRIMARY KEY", "pk_faculty", "faculty_id is primary key"),
                ("FOREIGN KEY", "fk_faculty_dept", "FOREIGN KEY (dept_id) REFERENCES departments(dept_id)"),
                ("UNIQUE", "uq_faculty_email", "email must be unique across all faculty members"),
            ]),
            ("courses", "Academic courses and curriculum offerings", [
                ("course_id", "VARCHAR(10)", False, None),
                ("title", "VARCHAR(100)", False, None),
                ("credits", "INTEGER", False, None),
                ("dept_id", "VARCHAR(10)", False, None),
                ("status", "VARCHAR(20)", True, "'ACTIVE'")
            ], [
                ("PRIMARY KEY", "pk_courses", "course_id is primary key"),
                ("FOREIGN KEY", "fk_courses_dept", "FOREIGN KEY (dept_id) REFERENCES departments(dept_id)"),
                ("CHECK", "chk_course_credits", "credits > 0 AND credits <= 6"),
                ("REGISTERED_VIEW", "vw_student_credit_summary", "Aggregates sum(credits) for enrolled students"),
                ("REGISTERED_RULE", "RULE_FULLTIME", "Evaluates total student credits >= 12 using courses.credits"),
                ("REGISTERED_TRIGGER", "trg_check_credit_limit", "Registered trigger enforcing max 24 credits per semester"),
            ]),
            ("students", "Enrolled university students", [
                ("student_id", "VARCHAR(10)", False, None),
                ("name", "VARCHAR(100)", False, None),
                ("email", "VARCHAR(100)", False, None),
                ("gpa", "REAL", True, "3.5"),
                ("enrolled_date", "VARCHAR(20)", True, None),
                ("status", "VARCHAR(20)", True, "'ACTIVE'")
            ], [
                ("PRIMARY KEY", "pk_students", "student_id is primary key"),
                ("UNIQUE", "uq_student_email", "email must be unique across all students"),
                ("CHECK", "chk_student_gpa", "gpa >= 0.0 AND gpa <= 4.0"),
            ]),
            ("enrollments", "Course registrations and student term grades", [
                ("enrollment_id", "INTEGER", False, None),
                ("student_id", "VARCHAR(10)", False, None),
                ("course_id", "VARCHAR(10)", False, None),
                ("semester", "VARCHAR(20)", False, None),
                ("grade", "VARCHAR(5)", True, "'IP'"),
                ("status", "VARCHAR(20)", True, "'ENROLLED'")
            ], [
                ("PRIMARY KEY", "pk_enrollments", "enrollment_id is auto-increment primary key"),
                ("FOREIGN KEY", "fk_enrollments_student", "FOREIGN KEY (student_id) REFERENCES students(student_id) ON DELETE RESTRICT"),
                ("FOREIGN KEY", "fk_enrollments_course", "FOREIGN KEY (course_id) REFERENCES courses(course_id) ON DELETE RESTRICT"),
                ("UNIQUE", "uq_student_course_semester", "UNIQUE(student_id, course_id, semester)"),
            ]),
            ("eligibility_rules", "Institutional academic threshold and standing rules", [
                ("rule_id", "VARCHAR(20)", False, None),
                ("rule_name", "VARCHAR(100)", False, None),
                ("min_credits", "INTEGER", False, None),
                ("description", "TEXT", True, None),
                ("status", "VARCHAR(20)", True, "'ACTIVE'")
            ], [
                ("PRIMARY KEY", "pk_eligibility_rules", "rule_id is primary key"),
            ]),
        ]

        for t_name, t_desc, cols, constraints in table_defs:
            t_meta = Table_Meta(schema_id=1, table_name=t_name, description=t_desc)
            db.add(t_meta)
            db.commit()

            for c_name, c_type, c_null, c_def in cols:
                cm = Column_Meta(
                    table_id=t_meta.table_id,
                    column_name=c_name,
                    data_type=c_type,
                    is_nullable=c_null,
                    default_value=c_def
                )
                db.add(cm)

            for c_type, c_name_str, c_det in constraints:
                cn = Constraint_Meta(
                    table_id=t_meta.table_id,
                    constraint_type=c_type,
                    constraint_name=c_name_str,
                    details=c_det
                )
                db.add(cn)
            db.commit()

        # ----------------------------------------------------
        # 4. INITIAL HISTORICAL CHANGE REQUESTS & AUDIT LOGS
        # ----------------------------------------------------
        # Seed Request 1: Adding course CS301 (Historical committed change)
        cr1 = Change_Request(
            request_id=1,
            user_id=2,  # Yashi
            change_type="INSERT",
            target_table="courses",
            target_record_id="CS301",
            target_column="*",
            original_value=None,
            proposed_value=json.dumps({"course_id": "CS301", "title": "Database Systems", "credits": 3, "dept_id": "CS", "status": "ACTIVE"}),
            sql_statement="INSERT INTO courses (course_id, title, credits, dept_id, status) VALUES ('CS301', 'Database Systems', 3, 'CS', 'ACTIVE')",
            description="Add core database curriculum course CS301",
            status="COMMITTED",
            selected_strategy="Strategy A: Direct Insert",
            created_at=datetime.utcnow() - timedelta(days=2)
        )
        db.add(cr1)
        db.commit()

        ia1 = Impact_Analysis(
            analysis_id=1,
            request_id=1,
            affected_tables=json.dumps(["courses"]),
            affected_columns=json.dumps(["course_id", "title", "credits", "dept_id"]),
            affected_records=json.dumps(["CS301"]),
            dependency_impact=json.dumps({"foreign_keys": ["departments.CS"], "registered_views": [], "rules": []}),
            constraint_violations=json.dumps([]),
            created_at=datetime.utcnow() - timedelta(days=2)
        )
        db.add(ia1)
        db.commit()

        ra1 = Risk_Assessment(
            risk_id=1,
            analysis_id=1,
            risk_score=12.5,
            risk_level="Low",
            risk_factors=json.dumps({
                "dependency_score": 10.0,
                "constraint_score": 5.0,
                "business_rule_score": 10.0,
                "data_impact_score": 15.0,
                "complexity_score": 25.0,
                "weights": {"dependency": 0.30, "constraint": 0.25, "business_rule": 0.20, "data_impact": 0.15, "complexity": 0.10},
                "explanation": "Standard row insertion referencing valid department key 'CS'. No integrity or business rule violations."
            }),
            created_at=datetime.utcnow() - timedelta(days=2)
        )
        db.add(ra1)
        db.commit()

        log1 = Change_Log(
            log_id=1,
            request_id=1,
            user_id=1,  # Admin committed
            change_type="INSERT",
            previous_state="NULL",
            new_state=json.dumps({"course_id": "CS301", "title": "Database Systems", "credits": 3, "dept_id": "CS"}),
            timestamp=datetime.utcnow() - timedelta(days=2)
        )
        db.add(log1)
        db.commit()

        # Seed Request 2: Department budget update (Approved)
        cr2 = Change_Request(
            request_id=2,
            user_id=3,  # Navya
            change_type="UPDATE",
            target_table="departments",
            target_record_id="CS",
            target_column="budget",
            original_value="400000.0",
            proposed_value="450000.0",
            sql_statement="UPDATE departments SET budget = 450000.0 WHERE dept_id = 'CS'",
            description="FY2026 CS Dept Lab modernization grant allocation",
            status="APPROVED",
            selected_strategy="Strategy A: Direct Update",
            created_at=datetime.utcnow() - timedelta(days=1)
        )
        db.add(cr2)
        db.commit()

        ia2 = Impact_Analysis(
            analysis_id=2,
            request_id=2,
            affected_tables=json.dumps(["departments"]),
            affected_columns=json.dumps(["budget"]),
            affected_records=json.dumps(["CS"]),
            dependency_impact=json.dumps({"foreign_keys": [], "registered_views": [], "rules": []}),
            constraint_violations=json.dumps([]),
            created_at=datetime.utcnow() - timedelta(days=1)
        )
        db.add(ia2)
        db.commit()

        ra2 = Risk_Assessment(
            risk_id=2,
            analysis_id=2,
            risk_score=15.0,
            risk_level="Low",
            risk_factors=json.dumps({
                "dependency_score": 10.0,
                "constraint_score": 10.0,
                "business_rule_score": 10.0,
                "data_impact_score": 20.0,
                "complexity_score": 25.0,
                "weights": {"dependency": 0.30, "constraint": 0.25, "business_rule": 0.20, "data_impact": 0.15, "complexity": 0.10},
                "explanation": "Numerical budget increase on parent entity. No foreign key constraints broken."
            }),
            created_at=datetime.utcnow() - timedelta(days=1)
        )
        db.add(ra2)
        db.commit()

        log2 = Change_Log(
            log_id=2,
            request_id=2,
            user_id=4,  # Faculty guide approved
            change_type="UPDATE_APPROVED",
            previous_state="budget: 400000.0",
            new_state="budget: 450000.0 (Approved by Prof. Saritha Murali)",
            timestamp=datetime.utcnow() - timedelta(days=1)
        )
        db.add(log2)
        db.commit()

        return {"status": "success", "message": "PreGuard DB initialized and seeded successfully with VIT demo university records!"}

    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()
