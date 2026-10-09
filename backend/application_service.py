try:
    from backend.supabase_client import supabase
except ImportError:
    from supabase_client import supabase



def create_application(
    applicant_id: str,
    scholarship_scheme_id: str,
    academic_score: float,
    previous_score: float,
    attendance: float,
    annual_income: float,
    application_category: str
):
    data = {
        "applicant_id": applicant_id,
        "scholarship_scheme_id": scholarship_scheme_id,
        "academic_score": academic_score,
        "previous_score": previous_score,
        "attendance": attendance,
        "annual_income": annual_income,
        "application_category": application_category,
        "status": "SUBMITTED"
    }

    response = (
        supabase
        .table("applications")
        .insert(data)
        .execute()
    )

    return response


def _enrich_application_records(applications: list) -> list:
    """
    Enrich application records with:
    - Latest AI prediction, ML confidence (probability), and SHAP explanations
    - Confidence-based ML categorization (Likely to Get Approved / Rejected / Moderate)
    - Latest human evaluator decision, reason, and admin comment
    - Latest appeal information
    """
    if not applications:
        return []

    app_ids = [a["id"] for a in applications if isinstance(a, dict) and "id" in a]
    if not app_ids:
        return applications

    def _fetch_in_chunks(table, select_cols, id_list, chunk_size=50):
        records = []
        for i in range(0, len(id_list), chunk_size):
            chunk = id_list[i : i + chunk_size]
            res = (
                supabase
                .table(table)
                .select(select_cols)
                .in_("application_id", chunk)
                .order("created_at", desc=True)
                .execute()
            )
            if res.data:
                records.extend(res.data)
        return records

    preds_by_app = {}
    try:
        preds = _fetch_in_chunks(
            "ai_predictions",
            "application_id, prediction, probability, explanation, top_reasons, model_version, created_at",
            app_ids,
        )
        for p in preds:
            aid = p.get("application_id")
            if aid and aid not in preds_by_app:
                preds_by_app[aid] = p
    except Exception as exc:
        print("Enrichment prediction fetch warning:", exc)

    decisions_by_app = {}
    try:
        decs = _fetch_in_chunks(
            "decisions",
            "application_id, decision, reason, admin_comment, created_at",
            app_ids,
        )
        for d in decs:
            aid = d.get("application_id")
            if aid and aid not in decisions_by_app:
                decisions_by_app[aid] = d
    except Exception as exc:
        print("Enrichment decision fetch warning:", exc)

    appeals_by_app = {}
    try:
        apps_data = _fetch_in_chunks(
            "appeals",
            "id, application_id, reason, status, review_comment, created_at",
            app_ids,
        )
        for a in apps_data:
            aid = a.get("application_id")
            if aid and aid not in appeals_by_app:
                appeals_by_app[aid] = a
    except Exception as exc:
        print("Enrichment appeal fetch warning:", exc)

    risk_by_app = {}
    try:
        from backend.db import get_conn
        conn = get_conn()
        anomaly_rows = conn.execute("SELECT application_id, severity FROM document_anomalies").fetchall()
        conn.close()
        for row in anomaly_rows:
            aid = row["application_id"]
            sev = (row["severity"] or "LOW").upper()
            if sev == "HIGH" or aid not in risk_by_app:
                risk_by_app[aid] = sev
            elif sev == "MEDIUM" and risk_by_app.get(aid) != "HIGH":
                risk_by_app[aid] = sev
    except Exception:
        pass

    for app in applications:
        aid = app.get("id")
        pred = preds_by_app.get(aid)
        dec = decisions_by_app.get(aid)
        appeal = appeals_by_app.get(aid)

        if pred:
            prob = float(pred.get("probability") or 0.0)
            model_dec = pred.get("prediction") or "NEEDS_HUMAN_REVIEW"
            app["ai_prediction"] = pred
            app["model_decision"] = model_dec
            app["confidence"] = prob
            app["top_reasons"] = pred.get("top_reasons") or []
            app["explanation"] = pred.get("explanation") or {}

            # Phase 9: Confidence-based student categorization
            # LIKELY TO GET APPROVED: predicted class = APPROVE, confidence >= 70% (0.70)
            # LIKELY TO GET REJECTED: predicted class = REJECT, confidence >= 70% (0.70)
            # MODERATE / MAY OR MAY NOT GET APPROVED: otherwise
            if model_dec == "APPROVE" and prob >= 0.70:
                app["prediction_category"] = "Likely to Get Approved"
            elif model_dec == "REJECT" and prob >= 0.70:
                app["prediction_category"] = "Likely to Get Rejected"
            else:
                app["prediction_category"] = "Moderate / May or May Not Get Approved"
        else:
            app["ai_prediction"] = None
            app["model_decision"] = None
            app["confidence"] = None
            app["prediction_category"] = "Moderate / May or May Not Get Approved"
            app["ml_status"] = "ML Processing Pending"
            app["top_reasons"] = []
            app["explanation"] = {}

        if dec:
            app["decision"] = dec
            app["final_decision"] = dec.get("decision")
            app["admin_final_decision"] = dec.get("decision")
            app["admin_comment"] = dec.get("admin_comment") or dec.get("reason")
            app["decision_reason"] = dec.get("reason") or dec.get("admin_comment")
        else:
            app["decision"] = None
            app["final_decision"] = None
            app["admin_final_decision"] = None
            app["admin_comment"] = None
            app["decision_reason"] = None

        app["appeal"] = appeal
        app["risk_level"] = risk_by_app.get(aid, "LOW")

    return applications


def get_applications_by_applicant(applicant_id: str):
    response = (
        supabase
        .table("applications")
        .select(
            """
            id,
            application_number,
            scholarship_scheme_id,
            scholarship_schemes (
                scheme_code,
                scheme_name
            ),
            academic_score,
            previous_score,
            attendance,
            annual_income,
            application_category,
            status,
            created_at,
            updated_at
            """
        )
        .eq("applicant_id", applicant_id)
        .order("created_at", desc=True)
        .execute()
    )

    return _enrich_application_records(response.data or [])


def get_all_applications():
    response = (
        supabase
        .table("applications")
        .select(
            """
            id,
            application_number,
            applicant_id,
            scholarship_scheme_id,
            scholarship_schemes (
                scheme_code,
                scheme_name
            ),
            academic_score,
            previous_score,
            attendance,
            annual_income,
            application_category,
            status,
            created_at,
            updated_at
            """
        )
        .order("created_at", desc=True)
        .execute()
    )

    return _enrich_application_records(response.data or [])


def get_application_by_id(application_id: str, applicant_id: str):
    try:
        response = (
            supabase
            .table("applications")
            .select(
                """
                id,
                application_number,
                scholarship_scheme_id,
                scholarship_schemes (
                    scheme_code,
                    scheme_name,
                    description
                ),
                academic_score,
                previous_score,
                attendance,
                annual_income,
                application_category,
                status,
                created_at,
                updated_at
                """
            )
            .eq("id", application_id)
            .eq("applicant_id", applicant_id)
            .single()
            .execute()
        )
        return response.data
    except Exception:
        return None


def get_application_verification_data(application_id: str):
    response = (
        supabase
        .table("applications")
        .select(
            """
            id,
            application_number,
            applicant_id,
            academic_score,
            previous_score,
            attendance,
            annual_income,
            application_category
            """
        )
        .eq("id", application_id)
        .single()
        .execute()
    )

    return response.data


def get_applicant_profile(applicant_id: str):
    try:
        response = (
            supabase
            .table("profiles")
            .select("id, full_name, phone, role")
            .eq("id", applicant_id)
            .single()
            .execute()
        )
        return response.data
    except Exception:
        return None


def update_application_status(application_id: str, status: str):
    """
    Update the lifecycle status of an application.
    Allowed statuses:
    SUBMITTED, DOCUMENT_CHECK, AI_PROCESSING, HUMAN_REVIEW, APPROVED, REJECTED, APPEAL_PENDING
    """
    allowed_statuses = {
        "SUBMITTED",
        "DOCUMENT_CHECK",
        "AI_PROCESSING",
        "HUMAN_REVIEW",
        "APPROVED",
        "REJECTED",
        "APPEAL_PENDING",
    }

    status = status.upper().strip()

    if status not in allowed_statuses:
        raise ValueError(
            f"Invalid application status '{status}'. "
            f"Expected one of: {sorted(allowed_statuses)}"
        )

    response = (
        supabase
        .table("applications")
        .update({"status": status})
        .eq("id", application_id)
        .execute()
    )

    return response.data


def get_application_full_details(application_id: str):
    """
    Fetch comprehensive application data across all related tables:
    - application record + scholarship scheme
    - applicant profile
    - documents
    - AI predictions
    - decisions
    - appeals
    - audit logs
    """
    # 1. Application + scheme
    try:
        app_res = (
            supabase
            .table("applications")
            .select("""
                id,
                application_number,
                applicant_id,
                scholarship_scheme_id,
                scholarship_schemes (
                    id,
                    scheme_code,
                    scheme_name,
                    description,
                    required_documents
                ),
                academic_score,
                previous_score,
                attendance,
                annual_income,
                application_category,
                status,
                created_at,
                updated_at
            """)
            .eq("id", application_id)
            .single()
            .execute()
        )
        application = app_res.data
    except Exception:
        return None

    if not application:
        return None

    # 2. Applicant profile
    profile = get_applicant_profile(application["applicant_id"])

    # 3. Documents
    docs_res = (
        supabase
        .table("documents")
        .select("""
            id,
            document_type,
            file_name,
            storage_path,
            verification_status,
            verification_score,
            extracted_text,
            extracted_data,
            mismatch_details,
            verified_at,
            created_at
        """)
        .eq("application_id", application_id)
        .order("created_at")
        .execute()
    )
    documents = docs_res.data or []

    # 4. AI predictions
    pred_res = (
        supabase
        .table("ai_predictions")
        .select("""
            id,
            model_version,
            prediction,
            probability,
            explanation,
            top_reasons,
            feature_breakdown,
            created_at
        """)
        .eq("application_id", application_id)
        .order("created_at", desc=True)
        .execute()
    )
    predictions = pred_res.data or []
    latest_prediction = predictions[0] if predictions else None

    # 5. Decisions
    dec_res = (
        supabase
        .table("decisions")
        .select("""
            id,
            decision,
            reason,
            decision_type,
            decided_by,
            admin_comment,
            ai_prediction_id,
            created_at
        """)
        .eq("application_id", application_id)
        .order("created_at", desc=True)
        .execute()
    )
    decisions = dec_res.data or []

    # 6. Appeals
    appeal_res = (
        supabase
        .table("appeals")
        .select("""
            id,
            reason,
            status,
            reviewed_by,
            review_comment,
            created_at,
            updated_at
        """)
        .eq("application_id", application_id)
        .order("created_at", desc=True)
        .execute()
    )
    appeals = appeal_res.data or []

    # 7. Audit logs
    audit_res = (
        supabase
        .table("audit_logs")
        .select("""
            id,
            actor_id,
            action,
            old_value,
            new_value,
            reason,
            created_at
        """)
        .eq("application_id", application_id)
        .order("created_at", desc=True)
        .execute()
    )
    audit_logs = audit_res.data or []

    if latest_prediction:
        prob = latest_prediction.get("probability")
        if prob is not None:
            try:
                application["confidence"] = float(prob)
            except (ValueError, TypeError):
                application["confidence"] = None
        application["prediction"] = latest_prediction.get("prediction")

        pred_val = (application.get("prediction") or "").upper()
        conf_val = application.get("confidence") or 0.0
        if pred_val == "APPROVE" and conf_val >= 0.70:
            application["prediction_category"] = "Likely to Get Approved"
        elif pred_val == "REJECT" and conf_val >= 0.70:
            application["prediction_category"] = "Likely to Get Rejected"
        else:
            application["prediction_category"] = "Moderate / May or May Not Get Approved"
    else:
        application["confidence"] = None
        application["prediction"] = None
        application["prediction_category"] = "Moderate / May or May Not Get Approved"
        application["ml_status"] = "ML Processing Pending"

    if decisions:
        latest_dec = decisions[0]
        application["final_decision"] = latest_dec.get("decision")
        application["admin_comment"] = latest_dec.get("admin_comment")
        if (latest_dec.get("decision") or "").upper() in ("REJECT", "REJECTED"):
            application["rejection_reason"] = latest_dec.get("reason") or latest_dec.get("admin_comment")

    # Reconstruct stage-aware metadata from audit logs if available
    stage_data = None
    for log in audit_logs:
        if log.get("action") == "APPLICATION_CREATED" and isinstance(log.get("new_value"), dict):
            stage_data = log["new_value"]
            break

    if stage_data:
        application["academic_stage"] = stage_data.get("academic_stage", "LEGACY_UNSPECIFIED")
        application["qualification_type"] = stage_data.get("qualification_type")
        application["qualifying_score"] = stage_data.get("qualifying_score")
        application["ssc_score"] = stage_data.get("ssc_score")
        application["first_year_score"] = stage_data.get("first_year_score")
        application["second_year_score"] = stage_data.get("second_year_score")
        application["third_year_score"] = stage_data.get("third_year_score")
        application["ug_score"] = stage_data.get("ug_score")
    else:
        # Legacy application created before stage-aware profile
        application["academic_stage"] = "LEGACY_UNSPECIFIED"
        application["qualification_type"] = None
        application["qualifying_score"] = None
        application["ssc_score"] = None
        application["first_year_score"] = None
        application["second_year_score"] = None
        application["third_year_score"] = None
        application["ug_score"] = None

    return {
        "application": application,
        "applicant": profile,
        "documents": documents,
        "ai_prediction": latest_prediction,
        "ai_predictions": predictions,
        "decisions": decisions,
        "appeals": appeals,
        "audit_logs": audit_logs,
    }