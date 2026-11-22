"""Least-privilege application role grants shared by local provisioning and tests."""

from psycopg import sql


def grant_runtime(db, role):
    db.execute(
        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
            sql.Identifier(db.info.dbname), sql.Identifier(role)
        )
    )
    db.execute(sql.SQL("GRANT USAGE ON SCHEMA app TO {}").format(sql.Identifier(role)))
    grants = [
        "SELECT,INSERT,DELETE ON app.sessions",
        "UPDATE(expires_at) ON app.sessions",
        "SELECT,UPDATE ON app.login_guard",
        "SELECT,INSERT ON app.routines,app.routine_progress,app.tasks",
        "UPDATE(status,progress,started_at,completed_at,updated_at) ON app.routines",
        "UPDATE ON app.tasks",
        "SELECT,INSERT,UPDATE ON app.planning_goals,app.projects,app.routine_templates,app.calendar_events,app.execution_blocks,app.execution_sessions,app.daily_plans,app.reminder_requests",
        "SELECT,INSERT,DELETE ON app.task_dependencies",
        "SELECT,INSERT ON app.routine_exceptions,app.task_history,app.planning_commands",
        "SELECT,INSERT ON app.note_refs",
        "UPDATE(observed_title,observed_revision,last_verified_at) ON app.note_refs",
        "SELECT,INSERT,DELETE ON app.task_note_links,app.event_note_links,app.event_task_links",
        "SELECT ON app.workspace_changes,app.background_runs,app.operational_edges",
        "SELECT,INSERT,UPDATE,DELETE ON app.chat_conversations,app.chat_messages,app.chat_requests,app.chat_attachments",
        "SELECT,INSERT ON app.receiver_receipts",
        "SELECT,INSERT,UPDATE ON app.calendar_date_items,app.availability_windows",
        "SELECT,INSERT,DELETE ON app.date_item_note_links,app.availability_note_links",
        "UPDATE(source_revision) ON app.task_note_links,app.event_note_links,app.date_item_note_links,app.availability_note_links",
        "SELECT,INSERT,UPDATE ON app.workflow_sources,app.workflow_bindings,app.workflow_reviews,app.background_runs",
        "SELECT,INSERT ON app.workflow_changes",
        "SELECT,INSERT,UPDATE ON app.note_handoffs",
        "UPDATE(external_id) ON app.note_refs",
        "SELECT,INSERT,UPDATE ON app.agent_runs,app.agent_steps,app.agent_proposals,app.agent_note_events,app.agent_write_intents",
        "SELECT,INSERT,UPDATE ON app.agent_executions,app.agent_effects",
        "SELECT,INSERT ON app.yggdras_runs,app.yggdras_feedback,app.notifications",
        "SELECT,INSERT,UPDATE ON app.devices,app.calls,app.call_schedules",
        "SELECT,INSERT,UPDATE ON app.call_preferences,app.call_events,app.call_delivery,app.voice_worker_lease,app.call_commands,app.call_reviews",
        "SELECT,INSERT,UPDATE,DELETE ON app.call_briefs",
        "SELECT,INSERT ON app.item_outcomes",
        "SELECT,INSERT,UPDATE ON app.conductor_runs",
        "SELECT,INSERT ON app.conductor_events",
        "SELECT,INSERT,UPDATE ON app.conductor_policy",
        "SELECT,INSERT,DELETE ON app.routine_important_blocks",
        "SELECT,INSERT,UPDATE ON app.scheduled_jobs,app.scheduled_job_attempts,app.routine_escalations",
        "SELECT,INSERT,UPDATE ON app.daily_routine_settings,app.routine_checkins,app.routine_predictions,app.routine_pool,app.routine_editions,app.routine_hypotheses",
        "SELECT,INSERT ON app.journal_entries",
        "SELECT,INSERT,UPDATE ON app.daily_reviews,app.daily_lessons,app.daily_briefs,app.daily_inputs,app.daily_filing_runs,app.daily_filing_actions",
        "SELECT,INSERT,UPDATE,DELETE ON app.web_push_subscriptions,app.web_push_tokens,app.web_push_deliveries",
        "SELECT,INSERT,UPDATE ON app.routine_voice_bindings",
        "USAGE,SELECT ON ALL SEQUENCES IN SCHEMA app",
    ]
    for grant in grants:
        db.execute(sql.SQL("GRANT " + grant + " TO {}").format(sql.Identifier(role)))
