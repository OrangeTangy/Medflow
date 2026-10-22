# Operations, retention, and recovery

## Backup and restore

Enable encrypted RDS point-in-time recovery (at least 14 days), daily snapshots, cross-account backup vault controls, and alerting on failed backups. Use organization policy to set actual retention; do not silently delete workforce records based on a developer default. Keep encrypted object backups aligned with retention and legal holds.

Restore practice, at least quarterly:

1. Restore a snapshot/PITR to a separate private staging instance, with outbound notifications disabled.
2. Reapply runtime role grants and use isolated secrets; never point the restored app at production WiFi relays.
3. Run migrations and the PostgreSQL integration suite on a separate disposable test database, then verify restored organization/user/report counts, event uniqueness, audit continuity, and attendance totals against a known backup marker.
4. Verify that a doctor cannot read a peer or another organization using raw SQL under the non-owner role; verify cross-tenant foreign keys and overlap constraints.
5. Reconcile a known event sample twice and compare results. Test S3 retrieval and expired-audio deletion. Record RPO/RTO and sign off the restoration evidence before considering recovery tested.

The repository’s test execution validates a disposable PostgreSQL migration and access constraints. A cloud backup restore has not been performed without a real deployment and backup environment.

## Retention

Audio retention defaults to zero: successful transcription deletes temporary audio; hourly retention maintenance removes expired objects/rows. Configure an S3 lifecycle rule as a second enforcement layer. Transcription job results expire after the organization’s `transcription_job_retention_days` setting (default 30). Patient information must not be entered into this operational system unless all approved processing safeguards and agreements are in place.

Attendance, network events, reports, and audits require an organization-approved retention schedule and legal-hold policy. They are not deleted automatically by this foundation. Implement reviewed archival/deletion jobs and a cross-service deletion verification process once the policy is selected. Network replay currently requires retained evidence or a durable checkpoint. Do not delete source evidence before agreeing how historical attendance can be reproduced.

## Incident response

Disable compromised accounts/certificates in the IdP, application, and WiFi enrollment; revoke opaque app sessions; rotate integration HMAC and provider secrets through the secret manager. Preserve audit/network evidence in restricted immutable storage. Isolate affected processing services, measure the disclosure scope, and follow the organization’s notification/incident process. An IdP logout alone does not revoke an already issued app session; disabling the application user blocks access immediately. A session lasts at most eight hours.

## Uncertainty and outages

Never convert stale network evidence to physically verified attendance. Missed stops are bounded by the stale threshold and marked uncertain. Explain inferred periods and corrections to employees. Use manual check-ins when tracking fails and preserve their unverified source. Approval of a correction acknowledges an administrative amendment, not new network evidence.

Run one Celery scheduler and multiple workers as required. Database jobs survive Redis outages; health checks fail while rate limiting cannot be enforced. Retry processing errors are visible in `/api/integration-health`; failed jobs after five attempts require operator investigation. Do not log raw provider errors containing recordings/transcripts. Set bounded provider timeouts and avoid enabling third-party request body capture.
