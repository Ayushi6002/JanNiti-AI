"""
app.py
--------

Flask backend for the Scholarship AI Decision Explainer.

Endpoints:

    POST /submit-application       -> applicant submits form, gets decision back
    GET  /status/<id>              -> applicant checks their own application
    GET  /admin/applications       -> admin lists all applications (filterable)
    POST /admin/override           -> admin submits a manual decision

Run: python3 app.py   (starts on http://localhost:5000)

NOTE: Document text-extraction/keyword verification (Phase 3) is not
wired in yet. For now, `documents_verified` is passed directly in the
form as VERIFIED / INCOMPLETE / UNCERTAIN, simulating what Phase 3's
verification module will compute automatically from uploaded files.
"""

import sys
from pathlib import Path
from functools import wraps

_ROOT_DIR = Path(__file__).resolve().parent.parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

import io
import mimetypes
from flask import Flask, request, jsonify, g, send_file
from flask_cors import CORS


try:
    from . import db
    from .ml_service import ml_service
    from . import doc_verifier
except ImportError:
    import db
    from ml_service import ml_service
    import doc_verifier

try:
    from backend.decision_service import process_human_decision
    from backend.application_service import (
        create_application,
        update_application_status,
        get_application_by_id,
        get_applications_by_applicant,
        get_all_applications,
        get_application_full_details,
    )
    from backend.supabase_auth import require_supabase_role, get_supabase_current_user
    from backend.supabase_client import supabase
    from backend.document_service import download_document
    from backend.validation import (
        validate_full_name,
        validate_phone_number,
        validate_email,
        validate_academic_score,
        validate_attendance,
        validate_annual_income,
        validate_application_category,
    )
    from backend.appeal_service import (
        create_appeal,
        get_appeals_by_applicant,
        get_all_appeals,
        review_appeal,
    )
    from backend.verification_service import generate_verification_summary
    from backend.eligibility_service import evaluate_application_eligibility
    from backend.pipeline_service import submit_and_process_application
    from backend.passport_service import (
        build_decision_passport,
        ApplicationNotFoundError,
        ForbiddenPassportAccessError,
    )
    from backend.eligibility_simulator_service import (
        simulate_eligibility,
        ForbiddenSimulationAccessError,
        ApplicationNotFoundError as SimulatorAppNotFoundError,
    )
    from backend.anomaly_detection_service import (
        get_application_anomalies,
        ApplicationNotFoundError as AnomalyAppNotFoundError,
        ForbiddenAnomalyAccessError,
    )
    from backend.copilot_service import evaluate_student_eligibility
    from backend.scholarship_predictor_service import (
        predict_scholarships,
        get_predictor_configuration,
    )
except ImportError:
    from decision_service import process_human_decision
    from application_service import (
        create_application,
        update_application_status,
        get_application_by_id,
        get_applications_by_applicant,
        get_all_applications,
        get_application_full_details,
    )
    from supabase_auth import require_supabase_role, get_supabase_current_user
    from supabase_client import supabase
    from document_service import download_document
    from validation import (
        validate_full_name,
        validate_phone_number,
        validate_email,
        validate_academic_score,
        validate_attendance,
        validate_annual_income,
        validate_application_category,
    )
    from appeal_service import (
        create_appeal,
        get_appeals_by_applicant,
        get_all_appeals,
        review_appeal,
    )
    from verification_service import generate_verification_summary
    from eligibility_service import evaluate_application_eligibility
    from pipeline_service import submit_and_process_application
    from passport_service import (
        build_decision_passport,
        ApplicationNotFoundError,
        ForbiddenPassportAccessError,
    )
    from eligibility_simulator_service import (
        simulate_eligibility,
        ForbiddenSimulationAccessError,
        ApplicationNotFoundError as SimulatorAppNotFoundError,
    )
    from anomaly_detection_service import (
        get_application_anomalies,
        ApplicationNotFoundError as AnomalyAppNotFoundError,
        ForbiddenAnomalyAccessError,
    )
    from copilot_service import evaluate_student_eligibility
    from scholarship_predictor_service import (
        predict_scholarships,
        get_predictor_configuration,
    )




app = Flask(__name__)
CORS(app)  # allows the separate HTML/CSS/JS frontend to call this API

db.init_db()


REQUIRED_FIELDS = [
    "academic_score",
    "previous_score",
    "attendance",
    "annual_income",
    "application_category",
    "scholarship_scheme",
    "documents_verified",
]


# Fields needed for the full multipart flow
# (documents_verified is computed from uploaded files instead of being passed in directly)
FULL_FLOW_FORM_FIELDS = [
    "academic_score",
    "previous_score",
    "attendance",
    "annual_income",
    "application_category",
    "scholarship_scheme",
]
SCHOLARSHIP_SCHEME_IDS = {
    "MERIT": "91fc26f7-e746-4dae-862b-ddc1a8c3527c",
    "NEED_BASED": "cc4304cd-d84e-40f7-8085-dbd7c2d21f56",
    "CATEGORY": "42415966-00bc-455f-ad9a-30e884786b67",
}


VALID_ADMIN_DECISIONS = {
    "APPROVE",
    "REJECT",
    "NEEDS_HUMAN_REVIEW"
}


FEATURE_LABELS = {
    "academic_score": "academic performance",
    "previous_score": "previous academic performance",
    "attendance": "attendance record",
    "annual_income": "family income level",
    "application_category": "application category",
    "scholarship_scheme": "scholarship scheme",
    "documents_verified": "document verification status",
}


def _pretty_feature_name(feature_name):
    if feature_name in FEATURE_LABELS:
        return FEATURE_LABELS[feature_name]

    return feature_name.replace("_", " ")


def _reason_sentence(reason):
    feature = _pretty_feature_name(reason.get("feature", ""))
    impact = abs(float(reason.get("impact", 0)))
    direction = reason.get("direction", "increased")

    if direction == "increased":
        return (
            f"{feature} was a positive factor and had a strong "
            f"influence ({impact:.2f}) on the recommendation."
        )

    return (
        f"{feature} reduced the case strength and had a negative "
        f"influence ({impact:.2f}) on the recommendation."
    )


def get_token_from_request():
    auth_header = request.headers.get("Authorization", "")

    if auth_header.startswith("Bearer "):
        return auth_header.split(" ", 1)[1].strip()

    payload = request.get_json(silent=True) or {}

    if isinstance(payload, dict):
        return payload.get("token") or payload.get("session_token")

    return None


def get_current_user(required_role=None):
    token = get_token_from_request()

    session = db.get_session_by_token(token) if token else None

    if not session:
        return None

    user = db.get_user_by_id(session["user_id"])

    if not user:
        return None

    if required_role and user["role"] != required_role:
        return None

    g.current_user = user

    return user


def require_auth(required_role=None):
    def decorator(fn):

        @wraps(fn)
        def wrapper(*args, **kwargs):

            user = get_current_user(required_role=required_role)

            if not user:
                if required_role:
                    return jsonify({
                        "error": f"{required_role.title()} role required"
                    }), 403

                return jsonify({
                    "error": "Authentication required"
                }), 401

            return fn(*args, **kwargs)

        return wrapper

    return decorator


def build_explanation_payload(
    decision,
    confidence,
    top_reasons,
    override_applied=None
):
    reasons = top_reasons or []

    positive_reasons = [
        reason
        for reason in reasons
        if reason.get("direction") == "increased"
    ]

    negative_reasons = [
        reason
        for reason in reasons
        if reason.get("direction") == "decreased"
    ]

    applicant_summary = ""

    if decision == "APPROVE":
        applicant_summary = (
            "Your application is supported by strong academic and "
            "eligibility indicators. The AI found your profile to be "
            "a good fit for this scholarship."
        )

    elif decision == "REJECT":
        applicant_summary = (
            "The application is below the support threshold for this "
            "scholarship. The AI found a weaker profile compared with "
            "the eligibility requirements."
        )

    else:
        applicant_summary = (
            "The application was flagged for manual review because "
            "the result was uncertain. A human reviewer will examine "
            "the case before a final decision is made."
        )

    if override_applied:
        applicant_summary += (
            f" Additional review note: {override_applied}"
        )

    payload = {
        "decision": decision,
        "confidence": round(float(confidence or 0), 3),
        "top_reasons": reasons,

        "readable_reasons": [
            _reason_sentence(r)
            for r in reasons
        ],

        "why_approved": [
            _reason_sentence(r)
            for r in positive_reasons
        ],

        "why_rejected": [
            _reason_sentence(r)
            for r in negative_reasons
        ],

        "feature_breakdown": [
            {
                "feature": _pretty_feature_name(
                    r.get("feature", "")
                ),
                "direction": r.get(
                    "direction",
                    "increased"
                ),
                "impact": round(
                    float(r.get("impact", 0)),
                    3
                ),
            }
            for r in reasons
        ],

        "simple_explanation": applicant_summary,

        "report": {
            "decision": decision,
            "confidence": round(
                float(confidence or 0),
                3
            ),
            "summary": applicant_summary,
            "reasons": [
                _reason_sentence(r)
                for r in reasons
            ],
        },
    }

    return payload


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/auth/signup", methods=["POST"])
def signup():
    data = request.get_json(silent=True) or {}

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    phone = (data.get("phone") or "").strip()

    if not name or not email or len(password) < 6:
        return jsonify({
            "error": (
                "Name, valid email, and password "
                "(6+ chars) are required"
            )
        }), 400

    try:
        user = db.create_user(
            name,
            email,
            password,
            role="student",
            phone=phone
        )

    except ValueError as exc:
        return jsonify({"error": str(exc)}), 409

    token = db.create_session(user["id"])

    return jsonify({
        "message": "Account created successfully",
        "token": token,
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "role": user["role"],
        },
    }), 201


@app.route("/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}

    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({
            "error": "Email and password are required"
        }), 400

    user = db.get_user_by_email(email)

    if not user or not db.verify_password(
        password,
        user["password_hash"]
    ):
        return jsonify({
            "error": "Invalid email or password"
        }), 401

    token = db.create_session(user["id"])

    return jsonify({
        "message": "Logged in successfully",
        "token": token,
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "role": user["role"],
        },
    })


@app.route("/auth/logout", methods=["POST"])
def logout():
    token = get_token_from_request()

    if token:
        db.delete_session(token)

    return jsonify({
        "message": "Logged out successfully"
    })


@app.route("/auth/me", methods=["GET"])
def get_current_user_profile():
    token = get_token_from_request()
    if token:
        supa_user = get_supabase_current_user(token)
        if supa_user:
            profile = supa_user.get("profile") or {}
            return jsonify({
                "id": supa_user["id"],
                "name": profile.get("full_name") or (supa_user.get("email") or "").split("@")[0],
                "email": supa_user.get("email"),
                "role": supa_user.get("role") or "applicant",
                "phone": profile.get("phone") or "",
            }), 200

    user = get_current_user()
    if not user:
        return jsonify({
            "error": "Authentication required"
        }), 401

    return jsonify({
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
    })


@app.route("/auth/reset-request", methods=["POST"])
def reset_request():
    data = request.get_json(silent=True) or {}

    email = (data.get("email") or "").strip().lower()

    if not email:
        return jsonify({
            "error": "Email is required"
        }), 400

    user = db.get_user_by_email(email)

    if not user:
        return jsonify({
            "message": (
                "If an account exists, a reset link has been sent."
            )
        })

    reset_token = __import__("uuid").uuid4().hex

    db.set_reset_token(email, reset_token)

    return jsonify({
        "message": (
            "If an account exists, a reset link has been sent."
        ),
        "reset_token": reset_token,
    })


@app.route("/auth/reset-confirm", methods=["POST"])
def reset_confirm():
    data = request.get_json(silent=True) or {}

    token = (data.get("token") or "").strip()
    new_password = data.get("new_password") or ""

    if not token or len(new_password) < 6:
        return jsonify({
            "error": (
                "Reset token and a new password of "
                "6+ chars are required"
            )
        }), 400

    if db.reset_password_with_token(
        token,
        new_password
    ):
        return jsonify({
            "message": "Password reset successful"
        })

    return jsonify({
        "error": "Invalid or expired reset token"
    }), 400


@app.route("/scholarship-schemes", methods=["GET"])
@app.route("/scholarship/schemes", methods=["GET"])
def get_active_scholarship_schemes():
    """
    Public read-only endpoint returning active scholarship schemes
    and their required documents from Supabase.
    """
    try:
        res = (
            supabase
            .table("scholarship_schemes")
            .select("id, scheme_code, scheme_name, description, required_documents, is_active")
            .eq("is_active", True)
            .order("scheme_name")
            .execute()
        )
        return jsonify({"schemes": res.data or []}), 200
    except Exception as exc:
        print("get_active_scholarship_schemes error:", exc)
        return jsonify({"error": "Failed to fetch scholarship schemes", "details": str(exc)}), 500


@app.route("/submit-application-full", methods=["POST"])
@require_supabase_role("applicant")
def submit_application_full():
    """
    Full application submission flow.

    Accepts multipart/form-data containing applicant information
    and uploaded documents.

    Executes full pipeline:
    create application -> DOCUMENT_CHECK -> upload & process documents
    -> verification summary -> eligibility evaluation
    -> ML prediction (AI_PROCESSING) -> HUMAN_REVIEW
    """
    current_user = g.supabase_user

    try:
        result = submit_and_process_application(
            applicant_id=current_user["id"],
            form_data=request.form.to_dict(),
            files=request.files,
        )
        return jsonify(result), 201

    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    except Exception as exc:
        print("Submit application full error:", exc)
        return jsonify({
            "error": "Failed to submit and process application",
            "details": str(exc),
        }), 500



@app.route("/status/<app_id>", methods=["GET"])
@require_supabase_role("applicant")
def get_status(app_id):
    current_user = g.supabase_user

    try:
        application = get_application_by_id(
            application_id=app_id,
            applicant_id=current_user["id"]
        )
    except Exception as exc:
        print("Supabase application status error:", exc)
        return jsonify({
            "error": "Failed to retrieve application"
        }), 500

    if not application:
        return jsonify({
            "error": "Application not found"
        }), 404

    # Fetch verification summary if documents exist
    verification_summary = None
    try:
        verification_summary = generate_verification_summary(app_id)
    except Exception:
        pass

    # Fetch eligibility if scheme exists
    eligibility_summary = None
    if application.get("scholarship_scheme_id"):
        try:
            eligibility_summary = evaluate_application_eligibility(
                app_id,
                application["scholarship_scheme_id"]
            )
        except Exception:
            pass

    # Fetch latest AI prediction if exists
    ai_prediction = None
    try:
        pred_res = (
            supabase
            .table("ai_predictions")
            .select("id, prediction, probability, explanation, top_reasons, model_version, created_at")
            .eq("application_id", app_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if pred_res.data:
            ai_prediction = pred_res.data[0]
    except Exception:
        pass

    # Fetch latest human decision if exists
    decision = None
    try:
        dec_res = (
            supabase
            .table("decisions")
            .select("id, decision, reason, admin_comment, created_at")
            .eq("application_id", app_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if dec_res.data:
            decision = dec_res.data[0]
    except Exception:
        pass

    # Fetch latest appeal if exists
    appeal = None
    try:
        app_res = (
            supabase
            .table("appeals")
            .select("id, reason, status, review_comment, created_at, updated_at")
            .eq("application_id", app_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if app_res.data:
            appeal = app_res.data[0]
    except Exception:
        pass

    # Fetch anomaly assessment if available
    anomaly_assessment = None
    try:
        anomaly_assessment = get_application_anomalies(app_id, current_user)
    except Exception:
        pass

    confidence = None
    prediction = None
    prediction_category = None
    if ai_prediction:
        prob = ai_prediction.get("probability")
        if prob is not None:
            try:
                confidence = float(prob)
            except (ValueError, TypeError):
                confidence = None
        prediction = ai_prediction.get("prediction")

        pred_val = (prediction or "").upper()
        conf_val = confidence or 0.0
        if pred_val == "APPROVE" and conf_val >= 0.70:
            prediction_category = "Likely to Get Approved"
        elif pred_val == "REJECT" and conf_val >= 0.70:
            prediction_category = "Likely to Get Rejected"
        else:
            prediction_category = "Moderate / May or May Not Get Approved"

    final_decision = None
    rejection_reason = None
    admin_comment = None
    if decision:
        final_decision = decision.get("decision")
        admin_comment = decision.get("admin_comment")
        if (decision.get("decision") or "").upper() in ("REJECT", "REJECTED"):
            rejection_reason = decision.get("reason") or decision.get("admin_comment")

    return jsonify({
        "application_id": application["id"],
        "application_number": application.get("application_number"),
        "status": application.get("status"),
        "scholarship_scheme_id": application.get("scholarship_scheme_id"),
        "scholarship_schemes": application.get("scholarship_schemes"),
        "academic_score": application.get("academic_score"),
        "previous_score": application.get("previous_score"),
        "attendance": application.get("attendance"),
        "annual_income": application.get("annual_income"),
        "application_category": application.get("application_category"),
        "created_at": application.get("created_at"),
        "updated_at": application.get("updated_at"),
        "verification_summary": verification_summary,
        "anomaly_assessment": anomaly_assessment,
        "eligibility_summary": eligibility_summary,
        "ai_prediction": ai_prediction,
        "confidence": confidence,
        "prediction": prediction,
        "prediction_category": prediction_category,
        "decision": decision,
        "final_decision": final_decision,
        "rejection_reason": rejection_reason,
        "admin_comment": admin_comment,
        "appeal": appeal,
    }), 200


@app.route("/student/applications/<app_id>", methods=["GET"])
@require_supabase_role("applicant")
def student_application_detail(app_id):
    """
    Detailed application view for the student applicant.
    """
    return get_status(app_id)


@app.route("/student/applications/<app_id>/verification", methods=["GET"])
@require_supabase_role("applicant")
def student_application_verification(app_id):
    """
    Document verification summary for the student applicant.
    """
    current_user = g.supabase_user
    application = get_application_by_id(app_id, current_user["id"])
    if not application:
        return jsonify({"error": "Application not found"}), 404

    try:
        summary = generate_verification_summary(app_id)
        return jsonify(summary), 200
    except Exception as exc:
        return jsonify({"error": "Failed to get verification summary", "details": str(exc)}), 500


@app.route("/student/applications/<app_id>/decision", methods=["GET"])
@require_supabase_role("applicant")
def student_application_decision(app_id):
    """
    Human decision view for the student applicant.
    """
    current_user = g.supabase_user
    application = get_application_by_id(app_id, current_user["id"])
    if not application:
        return jsonify({"error": "Application not found"}), 404

    dec_res = (
        supabase
        .table("decisions")
        .select("id, decision, reason, admin_comment, created_at")
        .eq("application_id", app_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    decision = dec_res.data[0] if dec_res.data else None

    return jsonify({
        "application_id": app_id,
        "status": application.get("status"),
        "decision": decision,
    }), 200


@app.route("/student/applications/<app_id>/decision-passport", methods=["GET"])
@require_supabase_role()
def student_application_decision_passport(app_id):
    """
    Retrieve the AI Decision Passport for an application.
    Authorized for the owning applicant or an administrator.
    """
    current_user = g.supabase_user
    try:
        passport = build_decision_passport(app_id, current_user)
        return jsonify(passport), 200
    except ApplicationNotFoundError:
        return jsonify({"error": "Application not found"}), 404
    except ForbiddenPassportAccessError as exc:
        return jsonify({"error": str(exc)}), 403
    except Exception as exc:
        print("Decision passport error:", exc)
        return jsonify({
            "error": "Failed to generate decision passport",
            "details": str(exc),
        }), 500


@app.route("/student/applications/<app_id>/eligibility/simulate", methods=["POST"])
@require_supabase_role()
def student_application_eligibility_simulate(app_id):
    """
    Run an in-memory What-If Eligibility Simulation for an application.
    Authorized for the owning applicant or an administrator.
    Never modifies persistent database rows, documents, predictions, or decisions.
    """
    current_user = g.supabase_user
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    if "overrides" in data:
        overrides = data.get("overrides")
        if overrides is not None and not isinstance(overrides, dict):
            return jsonify({"error": "'overrides' must be a JSON object"}), 400
    else:
        overrides = {k: v for k, v in data.items() if k != "application_id"}

    try:
        result = simulate_eligibility(app_id, current_user, overrides)
        return jsonify(result), 200
    except (ApplicationNotFoundError, SimulatorAppNotFoundError):
        return jsonify({"error": "Application not found"}), 404
    except ForbiddenSimulationAccessError as exc:
        return jsonify({"error": str(exc)}), 403
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        print("Eligibility simulation error:", exc)
        return jsonify({
            "error": "Failed to run eligibility simulation",
            "details": str(exc),
        }), 500


@app.route("/student/applications/<app_id>/anomalies", methods=["GET"])
@require_supabase_role()
def student_application_anomalies(app_id):
    """
    Retrieve sanitized document fraud/anomaly assessment for an application.
    Authorized for the owning applicant or an administrator.
    Strictly advisory.
    """
    current_user = g.supabase_user
    try:
        anomalies = get_application_anomalies(app_id, current_user)
        return jsonify(anomalies), 200
    except (ApplicationNotFoundError, SimulatorAppNotFoundError, AnomalyAppNotFoundError):
        return jsonify({"error": "Application not found"}), 404
    except ForbiddenAnomalyAccessError as exc:
        return jsonify({"error": str(exc)}), 403
    except Exception as exc:
        print("Student anomaly retrieval error:", exc)
        return jsonify({
            "error": "Failed to retrieve anomaly assessment",
            "details": str(exc),
        }), 500


@app.route("/student/copilot/eligibility", methods=["GET", "POST"])
@require_supabase_role("applicant")
def student_copilot_eligibility():
    """
    AI Scholarship Eligibility Copilot:
    Evaluates currently active scholarship schemes against configured database rules
    for the authenticated student. Strictly read-only, non-decisional.
    Supports candidate values for pre-submission checks via POST without persisting.
    """
    current_user = g.supabase_user
    candidate_data = None
    if request.method == "POST":
        candidate_data = request.get_json(silent=True) or {}
        if not isinstance(candidate_data, dict):
            return jsonify({"error": "Request body must be a JSON object"}), 400

    try:
        report = evaluate_student_eligibility(
            applicant_id=current_user["id"],
            candidate_data=candidate_data,
        )
        return jsonify(report), 200
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        print("Copilot eligibility evaluation error:", exc)
        return jsonify({
            "error": "Failed to evaluate scholarship eligibility",
            "details": str(exc),
        }), 500


@app.route("/model-status", methods=["GET"])
def get_model_status():
    """
    Public read-only operational endpoint reporting the active model version,
    resolved artifact paths, feature list, and target classes from the live process.
    """
    from backend.ml_service import ml_service
    return jsonify({
        "active_version": ml_service.active_version,
        "model_artifact": getattr(ml_service, "model_path", None),
        "encoders_artifact": getattr(ml_service, "encoders_path", None),
        "feature_count": len(ml_service.feature_cols),
        "feature_cols": ml_service.feature_cols,
        "categorical_cols": ml_service.categorical_cols,
        "classes": ml_service.classes,
        "approve_idx": ml_service.approve_idx,
    }), 200


@app.route("/scholarship/predictor-config", methods=["GET"])
def scholarship_predictor_config():
    """
    Public read-only endpoint returning the dynamic configuration
    for the Scholarship Predictor form, including authoritative active
    schemes and required document checkboxes.
    """
    try:
        config = get_predictor_configuration()
        return jsonify(config), 200
    except Exception as exc:
        return jsonify({
            "error": "Failed to fetch predictor configuration",
            "details": str(exc),
        }), 500


@app.route("/scholarship/predict", methods=["POST"])
@app.route("/student/scholarship/predict", methods=["POST"])
def scholarship_predict():
    """
    Predict scholarship eligibility and ML classification.
    Public read-only endpoint: does NOT require login, does NOT create applications,
    modify decisions, or persist ML predictions.
    If an Authorization header is provided with a valid token, applicant_id is extracted optionally.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    applicant_id = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        try:
            from backend.supabase_auth import verify_supabase_token
            payload = verify_supabase_token(token)
            if payload:
                applicant_id = payload.get("sub")
        except Exception:
            pass

    try:
        result = predict_scholarships(profile_data=data, applicant_id=applicant_id)
        return jsonify(result), 200
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        print("Scholarship prediction error:", exc)
        return jsonify({
            "error": "Failed to generate scholarship prediction",
            "details": str(exc),
        }), 500


@app.route("/scholarship/explain", methods=["POST"])
def scholarship_explain():
    """
    Interactive SHAP Explainability endpoint for JanNiti AI (Phase 1C).
    Public, read-only endpoint returning TreeSHAP factor breakdown for ML prediction.
    Zero persistent database modifications.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    try:
        from backend.explainable_ai_service import generate_shap_explanation
        explanation = generate_shap_explanation(data)
        return jsonify(explanation), 200
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        print("SHAP explanation error:", exc)
        return jsonify({
            "status": "unavailable",
            "error": "AI prediction is available, but detailed explanation could not be generated.",
            "details": str(exc),
        }), 500


@app.route("/student/applications", methods=["GET"])
@require_supabase_role("applicant")
def student_applications():
    current_user = g.supabase_user

    try:
        applications = get_applications_by_applicant(
            current_user["id"]
        )

        return jsonify({
            "count": len(applications),
            "applications": applications
        }), 200

    except Exception as exc:
        print("Supabase student applications error:", exc)

        return jsonify({
            "error": "Failed to fetch applications"
        }), 500

@app.route("/student/appeals", methods=["GET"])
@require_supabase_role("applicant")
def student_appeals():
    current_user = g.supabase_user

    try:
        appeals = get_appeals_by_applicant(current_user["id"])

        return jsonify({
            "count": len(appeals),
            "appeals": appeals,
        }), 200

    except Exception as exc:
        return jsonify({
            "error": "Failed to fetch appeals",
            "details": str(exc),
        }), 500


@app.route("/student/appeals", methods=["POST"])
@require_supabase_role("applicant")
def student_create_appeal():
    """
    Submit a scholarship appeal for a finalized application.
    """
    current_user = g.supabase_user
    data = request.get_json(silent=True) or {}

    application_id = data.get("application_id")
    reason = (data.get("reason") or "").strip()

    if not application_id or not reason:
        return jsonify({
            "error": "application_id and reason are required"
        }), 400

    try:
        result = create_appeal(
            application_id=application_id,
            applicant_id=current_user["id"],
            reason=reason,
        )
        return jsonify({
            "message": "Appeal submitted successfully",
            "appeal": result,
        }), 201

    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    except Exception as exc:
        print("Create appeal error:", exc)
        return jsonify({
            "error": "Failed to create appeal",
            "details": str(exc),
        }), 500


# ---------------------------------------------------------
# STUDENT PROFILE ENDPOINTS
# ---------------------------------------------------------

@app.route("/student/profile", methods=["GET"])
@require_supabase_role("applicant")
def student_get_profile():
    current_user = g.supabase_user
    profile = current_user.get("profile") or current_user
    return jsonify({
        "id": current_user["id"],
        "email": current_user.get("email"),
        "full_name": profile.get("full_name") or "",
        "phone": profile.get("phone") or "",
        "role": profile.get("role") or "applicant",
        "created_at": profile.get("created_at"),
        "updated_at": profile.get("updated_at"),
    }), 200


@app.route("/student/profile", methods=["POST", "PUT"])
@require_supabase_role("applicant")
def student_update_profile():
    current_user = g.supabase_user
    user_id = current_user["id"]
    data = request.get_json(silent=True) or {}

    full_name = data.get("full_name")
    phone = data.get("phone")

    update_payload = {}
    if full_name is not None:
        is_valid, valid_name, err = validate_full_name(full_name)
        if not is_valid:
            return jsonify({"error": err}), 400
        update_payload["full_name"] = valid_name

    if phone is not None and str(phone).strip():
        is_valid, valid_phone, err = validate_phone_number(phone)
        if not is_valid:
            return jsonify({"error": err}), 400
        update_payload["phone"] = valid_phone

    if not update_payload:
        return jsonify({"error": "No valid fields provided to update"}), 400

    try:
        res = (
            supabase
            .table("profiles")
            .update(update_payload)
            .eq("id", user_id)
            .execute()
        )
        updated = res.data[0] if (res.data and len(res.data) > 0) else update_payload
        updated["email"] = current_user.get("email")
        return jsonify({
            "message": "Profile updated successfully",
            "profile": updated
        }), 200
    except Exception as exc:
        print("Update profile error:", exc)
        return jsonify({
            "error": "Failed to update profile",
            "details": str(exc),
        }), 500


# ---------------------------------------------------------
# DOCUMENT SERVING (VIEW / DOWNLOAD) HELPERS & ROUTES
# ---------------------------------------------------------

def _serve_document(app_id: str, doc_id: str, as_attachment: bool = False):
    try:
        doc_res = (
            supabase
            .table("documents")
            .select("id, application_id, document_type, file_name, storage_path")
            .eq("id", doc_id)
            .eq("application_id", app_id)
            .execute()
        )
        if not doc_res.data:
            return jsonify({"error": "Document not found"}), 404
        doc = doc_res.data[0]

        storage_path = doc.get("storage_path")
        if not storage_path:
            return jsonify({"error": "Document file path is missing"}), 404

        file_bytes = download_document(storage_path)

        filename = doc.get("file_name") or f"{doc.get('document_type', 'document')}.pdf"
        mime_type, _ = mimetypes.guess_type(filename)
        if not mime_type:
            mime_type = "application/pdf" if filename.lower().endswith(".pdf") else "application/octet-stream"

        return send_file(
            io.BytesIO(file_bytes),
            mimetype=mime_type,
            as_attachment=as_attachment,
            download_name=filename,
        )
    except Exception as exc:
        print("Serve document error:", exc)
        return jsonify({
            "error": "Failed to retrieve document from storage",
            "details": str(exc),
        }), 500


@app.route("/student/applications/<app_id>/documents/<doc_id>/view", methods=["GET"])
@require_supabase_role("applicant")
def student_view_document(app_id, doc_id):
    current_user = g.supabase_user
    application = get_application_by_id(app_id, current_user["id"])
    if not application:
        return jsonify({"error": "Application not found or unauthorized"}), 404
    return _serve_document(app_id, doc_id, as_attachment=False)


@app.route("/student/applications/<app_id>/documents/<doc_id>/download", methods=["GET"])
@require_supabase_role("applicant")
def student_download_document(app_id, doc_id):
    current_user = g.supabase_user
    application = get_application_by_id(app_id, current_user["id"])
    if not application:
        return jsonify({"error": "Application not found or unauthorized"}), 404
    return _serve_document(app_id, doc_id, as_attachment=True)


@app.route("/admin/applications/<app_id>/documents/<doc_id>/view", methods=["GET"])
@require_supabase_role("admin")
def admin_view_document(app_id, doc_id):
    return _serve_document(app_id, doc_id, as_attachment=False)


@app.route("/admin/applications/<app_id>/documents/<doc_id>/download", methods=["GET"])
@require_supabase_role("admin")
def admin_download_document(app_id, doc_id):
    return _serve_document(app_id, doc_id, as_attachment=True)



@app.route("/admin/applications", methods=["GET"])
@require_supabase_role("admin")
def admin_list_applications():
    try:
        applications = get_all_applications()

        return jsonify({
            "count": len(applications),
            "applications": applications
        }), 200

    except Exception as exc:
        print("Supabase admin applications error:", exc)
        return jsonify({
            "error": "Failed to fetch applications"
        }), 500


@app.route("/admin/applications/<app_id>", methods=["GET"])
@require_supabase_role("admin")
def admin_get_application(app_id):
    """
    Retrieve comprehensive details for an application for admin evaluation:
    application, applicant, documents, verification_summary, eligibility,
    ai_prediction, decisions, appeals, audit_logs.
    """
    try:
        details = get_application_full_details(app_id)
        if not details:
            return jsonify({"error": "Application not found"}), 404

        try:
            details["verification_summary"] = generate_verification_summary(app_id)
        except Exception:
            details["verification_summary"] = None

        if details["application"].get("scholarship_scheme_id"):
            try:
                details["eligibility"] = evaluate_application_eligibility(
                    app_id,
                    details["application"]["scholarship_scheme_id"]
                )
            except Exception:
                details["eligibility"] = None

        return jsonify(details), 200

    except Exception as exc:
        print("Admin get application error:", exc)
        return jsonify({
            "error": "Failed to retrieve application details",
            "details": str(exc),
        }), 500


@app.route("/admin/applications/<app_id>/decision-passport", methods=["GET"])
@require_supabase_role("admin")
def admin_application_decision_passport(app_id):
    """
    Retrieve the AI Decision Passport for an application (admin view).
    """
    current_user = g.supabase_user
    try:
        passport = build_decision_passport(app_id, current_user)
        return jsonify(passport), 200
    except ApplicationNotFoundError:
        return jsonify({"error": "Application not found"}), 404
    except ForbiddenPassportAccessError as exc:
        return jsonify({"error": str(exc)}), 403
    except Exception as exc:
        print("Admin decision passport error:", exc)
        return jsonify({
            "error": "Failed to generate decision passport",
            "details": str(exc),
        }), 500


@app.route("/admin/applications/<app_id>/eligibility/simulate", methods=["POST"])
@require_supabase_role("admin")
def admin_application_eligibility_simulate(app_id):
    """
    Run an in-memory What-If Eligibility Simulation for an application (admin view).
    Never modifies persistent database rows, documents, predictions, or decisions.
    """
    current_user = g.supabase_user
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": "Request body must be a JSON object"}), 400

    if "overrides" in data:
        overrides = data.get("overrides")
        if overrides is not None and not isinstance(overrides, dict):
            return jsonify({"error": "'overrides' must be a JSON object"}), 400
    else:
        overrides = {k: v for k, v in data.items() if k != "application_id"}

    try:
        result = simulate_eligibility(app_id, current_user, overrides)
        return jsonify(result), 200
    except (ApplicationNotFoundError, SimulatorAppNotFoundError):
        return jsonify({"error": "Application not found"}), 404
    except ForbiddenSimulationAccessError as exc:
        return jsonify({"error": str(exc)}), 403
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        print("Admin eligibility simulation error:", exc)
        return jsonify({
            "error": "Failed to run eligibility simulation",
            "details": str(exc),
        }), 500


@app.route("/admin/applications/<app_id>/anomalies", methods=["GET"])
@require_supabase_role("admin")
def admin_application_anomalies(app_id):
    """
    Retrieve detailed document fraud/anomaly assessment for an application (admin view).
    Authorized for administrators.
    Includes persisted records and comprehensive details.
    """
    current_user = g.supabase_user
    try:
        anomalies = get_application_anomalies(app_id, current_user)
        return jsonify(anomalies), 200
    except (ApplicationNotFoundError, SimulatorAppNotFoundError, AnomalyAppNotFoundError):
        return jsonify({"error": "Application not found"}), 404
    except ForbiddenAnomalyAccessError as exc:
        return jsonify({"error": str(exc)}), 403
    except Exception as exc:
        print("Admin anomaly retrieval error:", exc)
        return jsonify({
            "error": "Failed to retrieve anomaly assessment",
            "details": str(exc),
        }), 500


@app.route("/admin/override", methods=["POST"])
@require_supabase_role("admin")
def admin_override():
    data = request.get_json(silent=True)

    if not data:
        return jsonify({
            "error": "Request body must be JSON"
        }), 400

    application_id = data.get("application_id")
    admin_decision = data.get("admin_decision")
    admin_comment = data.get("admin_comment", "")

    if not application_id or not admin_decision:
        return jsonify({
            "error": "application_id and admin_decision are required"
        }), 400

    admin_decision = str(admin_decision).strip().upper()

    decision_map = {
        "APPROVE": "APPROVED",
        "APPROVED": "APPROVED",
        "REJECT": "REJECTED",
        "REJECTED": "REJECTED",
    }

    decision = decision_map.get(admin_decision)

    if not decision:
        return jsonify({
            "error": (
                "admin_decision must be one of "
                "APPROVE, APPROVED, REJECT, REJECTED"
            )
        }), 400

    current_user = g.supabase_user

    try:
        result = process_human_decision(
            application_id=application_id,
            decision=decision,
            reason=admin_comment,
            decided_by=current_user["id"],
            admin_comment=admin_comment,
        )

        return jsonify({
            "message": "Admin decision recorded successfully",
            "application_id": application_id,
            "decision": decision,
            "decided_by": current_user["id"],
            "result": result,
        }), 200

    except ValueError as exc:
        return jsonify({
            "error": str(exc)
        }), 400

    except Exception as exc:
        print("Supabase admin override error:", exc)
        return jsonify({
            "error": "Failed to record admin decision"
        }), 500

# ---------------------------------------------------------
# NEW SUPABASE HUMAN DECISION ENDPOINT
# ---------------------------------------------------------

@app.route("/admin/decision", methods=["POST"])
@require_supabase_role("admin")
def admin_decision():
    """
    Record a human evaluator decision using the Supabase workflow.
    """

    data = request.get_json(silent=True) or {}

    application_id = data.get("application_id")
    decision = data.get("decision")
    reason = (data.get("reason") or "").strip()
    ai_prediction_id = data.get("ai_prediction_id")
    admin_comment = data.get("admin_comment")

    if not application_id or not decision or not reason:
        return jsonify({
            "error": (
                "application_id, decision, and reason "
                "are required"
            )
        }), 400

    decision = decision.upper().strip()

    if decision not in {"APPROVED", "REJECTED"}:
        return jsonify({
            "error": (
                "decision must be APPROVED or REJECTED"
            )
        }), 400

    current_user = g.supabase_user

    try:
        result = process_human_decision(
            application_id=application_id,
            decision=decision,
            reason=reason,
            ai_prediction_id=ai_prediction_id,
            decided_by=current_user["id"],
            admin_comment=admin_comment,
        )

        return jsonify({
            "message": (
                "Human decision recorded successfully"
            ),
            "result": result,
        }), 200

    except ValueError as exc:
        return jsonify({
            "error": str(exc)
        }), 400

    except Exception as exc:
        return jsonify({
            "error": "Failed to process human decision",
            "details": str(exc),
        }), 500


@app.route("/admin/appeals", methods=["GET"])
@require_supabase_role("admin")
def admin_appeals():
    """
    Return all scholarship appeals for the authenticated admin.
    Uses Supabase instead of the legacy SQLite database.
    """

    try:
        appeals = get_all_appeals()

        return jsonify({
            "count": len(appeals),
            "appeals": appeals,
        }), 200

    except Exception as exc:
        return jsonify({
            "error": "Failed to fetch appeals",
            "details": str(exc),
        }), 500

@app.route("/admin/appeals/<appeal_id>/review", methods=["POST"])
@require_supabase_role("admin")
def admin_review_appeal(appeal_id):
    """
    Review a scholarship appeal as an authenticated admin.
    Allowed final statuses:
    - RESOLVED
    - REJECTED
    """

    current_user = g.supabase_user

    data = request.get_json(silent=True) or {}

    status = (data.get("status") or "").strip().upper()
    review_comment = (data.get("review_comment") or "").strip()

    if not status:
        return jsonify({
            "error": "status is required"
        }), 400

    if status not in {"RESOLVED", "REJECTED"}:
        return jsonify({
            "error": "status must be either RESOLVED or REJECTED"
        }), 400

    if not review_comment:
        return jsonify({
            "error": "review_comment is required"
        }), 400

    try:
        appeal = review_appeal(
            appeal_id=appeal_id,
            reviewed_by=current_user["id"],
            status=status,
            review_comment=review_comment,
        )

        return jsonify({
            "message": "Appeal reviewed successfully",
            "appeal": appeal,
        }), 200

    except ValueError as exc:
        return jsonify({
            "error": str(exc)
        }), 400

    except Exception as exc:
        return jsonify({
            "error": "Failed to review appeal",
            "details": str(exc),
        }), 500
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)