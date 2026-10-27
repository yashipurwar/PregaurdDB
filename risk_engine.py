from typing import Dict, Any, Optional

DEFAULT_WEIGHTS = {
    "dependency": 0.30,
    "constraint": 0.25,
    "business_rule": 0.20,
    "data_impact": 0.15,
    "complexity": 0.10
}

THRESHOLDS = {
    "Low": (0.0, 25.0),
    "Medium": (25.01, 50.0),
    "High": (50.01, 75.0),
    "Critical": (75.01, 100.0)
}

def calculate_risk_assessment(
    change_type: str,
    target_table: str,
    target_column: Optional[str],
    dependencies_data: Dict[str, Any],
    simulation_result: Dict[str, Any],
    custom_weights: Optional[Dict[str, float]] = None
) -> Dict[str, Any]:
    """
    Computes transparent multi-factor weighted risk score according to Eq. (1) of the report:
    R = w_dep * S_dep + w_con * S_con + w_biz * S_biz + w_data * S_data + w_cx * S_cx
    """
    weights = dict(DEFAULT_WEIGHTS)
    if custom_weights:
        # Validate weights sum to approx 1.0 (100%)
        total_w = sum(custom_weights.values())
        if abs(total_w - 1.0) > 0.01 and abs(total_w - 100.0) > 0.5:
            raise ValueError(f"Risk weights must sum to 100% (or 1.0). Current sum: {total_w}")
        # Normalize if passed as percentages
        if total_w > 2.0:
            weights = {k: v / 100.0 for k, v in custom_weights.items()}
        else:
            weights = dict(custom_weights)

    # 1. Dependency Score (S_dep, 0-100)
    # Measures direct and indirect structural dependencies, foreign keys, and registered views/triggers
    dep_count = dependencies_data.get("total_dependencies_count", 0)
    related_recs = dependencies_data.get("related_records_count", 0)
    has_registered_views = any(d.get("type") == "REGISTERED_VIEW" for d in dependencies_data.get("registered_dependencies", []))

    if change_type == "SCHEMA_CHANGE":
        s_dep = 90.0 if dep_count > 0 else 40.0
    elif related_recs > 0:
        s_dep = min(100.0, 30.0 + (related_recs * 8.0) + (15.0 if has_registered_views else 0.0))
    elif dep_count > 0:
        s_dep = min(100.0, dep_count * 20.0)
    else:
        s_dep = 10.0

    # 2. Constraint Score (S_con, 0-100)
    # Measures likelihood or presence of broken constraints (PK, FK, UNIQUE, CHECK, NOT NULL)
    violations = simulation_result.get("constraint_violations", [])
    if any(v.get("constraint_type") in ["CHECK", "UNIQUE", "FOREIGN KEY", "NOT NULL"] for v in violations):
        s_con = 95.0  # Immediate hard integrity violation
    elif simulation_result.get("simulation_status") == "CONSTRAINT_VIOLATION":
        s_con = 90.0
    elif change_type == "DELETE" and related_recs > 0:
        s_con = 85.0  # Would break referential integrity
    elif change_type == "UPDATE" and target_column == "credits":
        s_con = 30.0  # Constraint checked and valid in domain
    else:
        s_con = 10.0

    # 3. Business Rule Score (S_biz, 0-100)
    # Evaluates downstream effect on registered academic eligibility and threshold rules
    rule_violations = simulation_result.get("rule_violations", [])
    affected_rules = dependencies_data.get("affected_rules", [])

    if len(rule_violations) >= 2:
        s_biz = 85.0  # Multiple students lose standings (e.g. Full-time and Dean's list)
    elif len(rule_violations) == 1:
        s_biz = 75.0
    elif len(affected_rules) > 0 and simulation_result.get("affected_students_count", 0) > 0:
        s_biz = 60.0
    elif len(affected_rules) > 0:
        s_biz = 30.0
    else:
        s_biz = 5.0

    # 4. Data Impact Score (S_data, 0-100)
    # Measures volume and breadth of data modified, deleted, or indirectly altered
    affected_students = simulation_result.get("affected_students_count", 0)
    if change_type == "SCHEMA_CHANGE":
        s_data = 80.0
    elif change_type == "DELETE":
        s_data = min(100.0, 50.0 + related_recs * 10.0)
    elif affected_students > 0:
        s_data = min(100.0, 20.0 + (affected_students * 10.0))
    elif change_type in ["UPDATE", "INSERT"]:
        s_data = 15.0
    else:
        s_data = 10.0

    # 5. Complexity Score (S_cx, 0-100)
    # Intrinsic operational complexity of the operation
    if change_type == "SCHEMA_CHANGE":
        s_cx = 90.0
    elif change_type == "DELETE":
        s_cx = 65.0
    elif change_type == "UPDATE":
        s_cx = 45.0 if target_column == "credits" else 30.0
    elif change_type == "INSERT":
        s_cx = 25.0
    else:
        s_cx = 20.0

    # Compute Weighted Risk Score R
    weighted_dep = weights["dependency"] * s_dep
    weighted_con = weights["constraint"] * s_con
    weighted_biz = weights["business_rule"] * s_biz
    weighted_data = weights["data_impact"] * s_data
    weighted_cx = weights["complexity"] * s_cx

    raw_score = weighted_dep + weighted_con + weighted_biz + weighted_data + weighted_cx
    final_score = round(raw_score, 2)

    # Determine Risk Level
    if final_score <= 25.0:
        risk_level = "Low"
        rec_action = "Safe to proceed. Few or no dependencies are affected and no constraint violations are predicted."
    elif final_score <= 50.0:
        risk_level = "Medium"
        rec_action = "Review recommended before proceeding. Some dependent objects or rules are affected."
    elif final_score <= 75.0:
        risk_level = "High"
        rec_action = "Significant dependency, constraint or rule problems predicted. Modify the strategy."
    else:
        risk_level = "Critical"
        rec_action = "Severe integrity violations or widespread impact are predicted. Block the change or require approval."

    # Construct Plain-Language Rationale
    reasons = []
    if s_con >= 80.0:
        reasons.append("Violates relational integrity constraints (Foreign Key / CHECK / UNIQUE / NOT NULL).")
    if s_biz >= 60.0:
        reasons.append(f"Directly impacts registered business rules ({len(rule_violations)} active student standing violations detected).")
    if s_dep >= 50.0:
        reasons.append(f"High dependency fan-out across {dependencies_data.get('target_table')} and connected tables/views.")
    if affected_students > 0:
        reasons.append(f"Indirectly changes credit calculations for {affected_students} currently enrolled students.")
    if not reasons:
        reasons.append("Standard database operation with localized impact and no constraint or rule conflicts.")

    explanation = " ".join(reasons)

    return {
        "risk_score": final_score,
        "risk_level": risk_level,
        "recommended_action": rec_action,
        "factor_scores": {
            "dependency_score": round(s_dep, 1),
            "constraint_score": round(s_con, 1),
            "business_rule_score": round(s_biz, 1),
            "data_impact_score": round(s_data, 1),
            "complexity_score": round(s_cx, 1)
        },
        "weights": weights,
        "weighted_contributions": {
            "dependency": round(weighted_dep, 2),
            "constraint": round(weighted_con, 2),
            "business_rule": round(weighted_biz, 2),
            "data_impact": round(weighted_data, 2),
            "complexity": round(weighted_cx, 2)
        },
        "explanation": explanation
    }
