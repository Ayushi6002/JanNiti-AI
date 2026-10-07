from backend.supabase_client import supabase


def log_audit(
    application_id: str,
    action: str,
    old_value=None,
    new_value=None,
    reason: str | None = None,
    actor_id: str | None = None,
    entity_type: str = "application",
    entity_id: str | None = None,
):
    """
    Create an audit log entry for an application action.
    """

    data = {
        "application_id": application_id,
        "actor_id": actor_id,
        "action": action,
        "old_value": old_value,
        "new_value": new_value,
        "reason": reason,
        "entity_type": entity_type,
        "entity_id": entity_id or application_id,
    }

    response = (
        supabase
        .table("audit_logs")
        .insert(data)
        .execute()
    )

    return response.data