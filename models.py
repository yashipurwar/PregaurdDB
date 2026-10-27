from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Text, Boolean, DateTime, ForeignKey, CheckConstraint, UniqueConstraint
)
from sqlalchemy.orm import relationship
from backend.database import Base

# ==========================================
# 1. SIMULATED UNIVERSITY DOMAIN TABLES
# ==========================================

class Department(Base):
    __tablename__ = "departments"

    dept_id = Column(String(10), primary_key=True)
    dept_name = Column(String(100), nullable=False)
    building = Column(String(50))
    budget = Column(Float, default=100000.0)

    faculty_members = relationship("Faculty", back_populates="department")
    courses = relationship("Course", back_populates="department")


class Faculty(Base):
    __tablename__ = "faculty"

    faculty_id = Column(String(10), primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    dept_id = Column(String(10), ForeignKey("departments.dept_id"), nullable=False)
    title = Column(String(50), default="Assistant Professor")

    department = relationship("Department", back_populates="faculty_members")


class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (
        CheckConstraint("credits > 0 AND credits <= 6", name="chk_course_credits"),
    )

    course_id = Column(String(10), primary_key=True)
    title = Column(String(100), nullable=False)
    credits = Column(Integer, nullable=False)
    dept_id = Column(String(10), ForeignKey("departments.dept_id"), nullable=False)
    status = Column(String(20), default="ACTIVE")

    department = relationship("Department", back_populates="courses")
    enrollments = relationship("Enrollment", back_populates="course")


class Student(Base):
    __tablename__ = "students"
    __table_args__ = (
        CheckConstraint("gpa >= 0.0 AND gpa <= 4.0", name="chk_student_gpa"),
    )

    student_id = Column(String(10), primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    gpa = Column(Float, default=3.5)
    enrolled_date = Column(String(20), default=datetime.utcnow().strftime("%Y-%m-%d"))
    status = Column(String(20), default="ACTIVE")

    enrollments = relationship("Enrollment", back_populates="student")


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("student_id", "course_id", "semester", name="uq_student_course_semester"),
    )

    enrollment_id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(String(10), ForeignKey("students.student_id"), nullable=False)
    course_id = Column(String(10), ForeignKey("courses.course_id"), nullable=False)
    semester = Column(String(20), nullable=False)
    grade = Column(String(5), default="IP")  # In Progress
    status = Column(String(20), default="ENROLLED")

    student = relationship("Student", back_populates="enrollments")
    course = relationship("Course", back_populates="enrollments")


class EligibilityRule(Base):
    __tablename__ = "eligibility_rules"

    rule_id = Column(String(20), primary_key=True)
    rule_name = Column(String(100), nullable=False)
    min_credits = Column(Integer, nullable=False)
    description = Column(Text)
    status = Column(String(20), default="ACTIVE")


# ==========================================
# 2. PREGUARD DB 16 CORE FRAMEWORK ENTITIES
# ==========================================

# 1. User
class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password = Column(String(255), default="pbkdf2:sha256:preguard")
    role_id = Column(Integer, ForeignKey("roles.role_id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    role = relationship("Role", back_populates="users")
    change_requests = relationship("Change_Request", back_populates="user")
    change_logs = relationship("Change_Log", back_populates="user")


# 2. Role
class Role(Base):
    __tablename__ = "roles"

    role_id = Column(Integer, primary_key=True, autoincrement=True)
    role_name = Column(String(50), nullable=False)
    description = Column(Text)

    users = relationship("User", back_populates="role")


# 3. Database_Schema
class Database_Schema(Base):
    __tablename__ = "database_schemas"

    schema_id = Column(Integer, primary_key=True, autoincrement=True)
    database_name = Column(String(100), nullable=False)
    version = Column(String(20), default="1.0.0")
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    tables = relationship("Table_Meta", back_populates="database_schema")


# 4. Table (Table_Meta)
class Table_Meta(Base):
    __tablename__ = "tables_meta"

    table_id = Column(Integer, primary_key=True, autoincrement=True)
    schema_id = Column(Integer, ForeignKey("database_schemas.schema_id"), nullable=False)
    table_name = Column(String(100), nullable=False)
    description = Column(Text)

    database_schema = relationship("Database_Schema", back_populates="tables")
    columns = relationship("Column_Meta", back_populates="table_meta")
    constraints = relationship("Constraint_Meta", back_populates="table_meta")


# 5. Column (Column_Meta)
class Column_Meta(Base):
    __tablename__ = "columns_meta"

    column_id = Column(Integer, primary_key=True, autoincrement=True)
    table_id = Column(Integer, ForeignKey("tables_meta.table_id"), nullable=False)
    column_name = Column(String(100), nullable=False)
    data_type = Column(String(50), nullable=False)
    is_nullable = Column(Boolean, default=True)
    default_value = Column(Text, nullable=True)

    table_meta = relationship("Table_Meta", back_populates="columns")


# 6. Constraint (Constraint_Meta)
class Constraint_Meta(Base):
    __tablename__ = "constraints_meta"

    constraint_id = Column(Integer, primary_key=True, autoincrement=True)
    table_id = Column(Integer, ForeignKey("tables_meta.table_id"), nullable=False)
    constraint_type = Column(String(50), nullable=False)  # PRIMARY KEY, FOREIGN KEY, CHECK, UNIQUE, NOT NULL, REGISTERED_VIEW, REGISTERED_TRIGGER, REGISTERED_RULE
    constraint_name = Column(String(100), nullable=False)
    details = Column(Text)

    table_meta = relationship("Table_Meta", back_populates="constraints")


# 7. Change_Request
class Change_Request(Base):
    __tablename__ = "change_requests"

    request_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    change_type = Column(String(50), nullable=False)  # INSERT, UPDATE, DELETE, SCHEMA_CHANGE
    target_table = Column(String(100), nullable=True)
    target_record_id = Column(String(100), nullable=True)
    target_column = Column(String(100), nullable=True)
    original_value = Column(Text, nullable=True)
    proposed_value = Column(Text, nullable=True)
    sql_statement = Column(Text, nullable=True)
    description = Column(Text)
    status = Column(String(20), default="PENDING_APPROVAL")  # DRAFT, ANALYZED, PENDING_APPROVAL, APPROVED, REJECTED, COMMITTED
    rejection_reason = Column(Text, nullable=True)
    selected_strategy = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="change_requests")
    impact_analysis = relationship("Impact_Analysis", back_populates="change_request", uselist=False)
    change_logs = relationship("Change_Log", back_populates="change_request")


# 8. Impact_Analysis
class Impact_Analysis(Base):
    __tablename__ = "impact_analyses"

    analysis_id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(Integer, ForeignKey("change_requests.request_id"), nullable=False)
    affected_tables = Column(Text)  # JSON or comma-separated
    affected_columns = Column(Text)
    affected_records = Column(Text)
    dependency_impact = Column(Text)
    constraint_violations = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    change_request = relationship("Change_Request", back_populates="impact_analysis")
    whatif_simulation = relationship("WhatIf_Simulation", back_populates="impact_analysis", uselist=False)
    risk_assessment = relationship("Risk_Assessment", back_populates="impact_analysis", uselist=False)
    strategies = relationship("Strategy", back_populates="impact_analysis")


# 9. WhatIf_Simulation
class WhatIf_Simulation(Base):
    __tablename__ = "whatif_simulations"

    simulation_id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_id = Column(Integer, ForeignKey("impact_analyses.analysis_id"), nullable=False)
    operation_type = Column(String(50), nullable=False)
    simulated_data_impact = Column(Text)
    simulated_constraint_impact = Column(Text)
    simulated_dependencies = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    impact_analysis = relationship("Impact_Analysis", back_populates="whatif_simulation")
    simulation_data_records = relationship("Simulation_Data", back_populates="simulation")


# 10. Simulation_Data
class Simulation_Data(Base):
    __tablename__ = "simulation_data"

    data_id = Column(Integer, primary_key=True, autoincrement=True)
    simulation_id = Column(Integer, ForeignKey("whatif_simulations.simulation_id"), nullable=False)
    table_name = Column(String(100), nullable=False)
    record_id = Column(String(100))
    old_value = Column(Text)
    new_value = Column(Text)
    impact_type = Column(String(50))  # DIRECT_MODIFIED, INDIRECT_CALCULATED, RULE_VIOLATED, INTEGRITY_BROKEN

    simulation = relationship("WhatIf_Simulation", back_populates="simulation_data_records")


# 11. Risk_Assessment
class Risk_Assessment(Base):
    __tablename__ = "risk_assessments"

    risk_id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_id = Column(Integer, ForeignKey("impact_analyses.analysis_id"), nullable=False)
    risk_score = Column(Float, nullable=False)  # 0.0 - 100.0
    risk_level = Column(String(20), nullable=False)  # Low, Medium, High, Critical
    risk_factors = Column(Text)  # JSON with {dependency, constraint, biz_rule, data_impact, complexity, explanation}
    created_at = Column(DateTime, default=datetime.utcnow)

    impact_analysis = relationship("Impact_Analysis", back_populates="risk_assessment")


# 12. Strategy
class Strategy(Base):
    __tablename__ = "strategies"

    strategy_id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_id = Column(Integer, ForeignKey("impact_analyses.analysis_id"), nullable=False)
    strategy_type = Column(String(50), nullable=False)  # Strategy A: Direct Update, Strategy B: Update Rules First, Strategy C: Versioned Course
    description = Column(Text)
    estimated_cost = Column(Float, default=0.0)
    estimated_time = Column(Integer, default=1)  # In hours
    risk_score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    impact_analysis = relationship("Impact_Analysis", back_populates="strategies")
    recommendations = relationship("Recommendation", back_populates="strategy")


# 13. Recommendation
class Recommendation(Base):
    __tablename__ = "recommendations"

    recommendation_id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(Integer, ForeignKey("strategies.strategy_id"), nullable=False)
    recommended_strategy = Column(String(50), nullable=False)
    reason = Column(Text)
    expected_outcome = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    strategy = relationship("Strategy", back_populates="recommendations")


# 14. Change_Log
class Change_Log(Base):
    __tablename__ = "change_logs"

    log_id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(Integer, ForeignKey("change_requests.request_id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    change_type = Column(String(50), nullable=False)
    previous_state = Column(Text)
    new_state = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)

    change_request = relationship("Change_Request", back_populates="change_logs")
    user = relationship("User", back_populates="change_logs")


# 15. Relational_Schema
class Relational_Schema(Base):
    __tablename__ = "relational_schemas"

    schema_id = Column(Integer, primary_key=True, autoincrement=True)
    database_name = Column(String(100), nullable=False)
    version = Column(String(20), default="1.0.0")
    description = Column(Text)

    physical_designs = relationship("Physical_Design", back_populates="relational_schema")


# 16. Physical_Design
class Physical_Design(Base):
    __tablename__ = "physical_designs"

    design_id = Column(Integer, primary_key=True, autoincrement=True)
    schema_id = Column(Integer, ForeignKey("relational_schemas.schema_id"), nullable=False)
    storage_details = Column(Text)
    index_details = Column(Text)
    partitioning_details = Column(Text)

    relational_schema = relationship("Relational_Schema", back_populates="physical_designs")
