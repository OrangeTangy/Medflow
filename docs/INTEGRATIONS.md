# Enterprise integrations

Use WPA2/WPA3 Enterprise 802.1X, preferably EAP-TLS with per-device certificates. Enroll the certificate/device identity and associated doctor through `POST /api/devices`. Configure the controller identifier through `PATCH /api/networks/{id}`. SSIDs are display mappings; shared passwords and MAC addresses are never sufficient identity.

The provided RADIUS adapter accepts normalized JSON attributes from a trusted accounting relay. It is **not** a UDP RADIUS server. Terminate RADIUS Accounting securely on your FreeRADIUS/vendor infrastructure, validate the authenticator/shared secret there, then forward accounting messages over authenticated TLS to this API. Validate behavior on actual Cisco/Aruba/UniFi equipment before claiming support. Vendor API/webhook adapters can implement `ProviderAdapter.normalize` and register in `ADAPTERS`.

Required RADIUS JSON fields:

```json
{
  "Event-Id": "controller-01:session-123:interim:1792671300",
  "EAP-Identity": "certificate-subject-or-approved-idp-reference",
  "Device-Certificate-Id": "enrolled-certificate-fingerprint",
  "NAS-Identifier": "main-hospital-controller",
  "Acct-Session-Id": "session-123",
  "Acct-Status-Type": "Interim-Update",
  "Event-Timestamp": "2026-10-22T12:15:00Z"
}
```

POST to `/api/integrations/radius/events`. Sign the **exact** JSON bytes: `hex(HMAC-SHA256(INTEGRATION_SECRET, unix_timestamp + '.' + raw_body))`. Send headers `X-Medflow-Timestamp` and `X-Medflow-Signature`. The signature timestamp must be within five minutes of receipt; the source event time may be older within the configured 30-day acceptance window. For delayed accounting, re-sign at relay delivery while preserving the original source event ID/time. Retries use the same source event ID and are idempotent.

The normalized adapter accepts `source_event_id`, `identity_reference`, `device_identifier`, `controller_identifier`, `accounting_session_id`, `event_type` (`start`, `stop`, `interim`, `outage`), and an offset-bearing `event_timestamp`. One configured integration organization is supported per API ingestion instance. Deploy separate relay/ingestion configurations for independent organizations; never accept organization selection from the event body.

Send interims substantially more frequently than `PRESENCE_STALE_SECONDS` (recommended five minutes for a fifteen-minute threshold). Preserve accounting session IDs across AP roaming when the vendor supports it. Validate stop delivery, AP changes, controller restarts, multi-device overlap, certificate revocation, delayed auth, and simultaneous conflicting buildings.

## Transcription adapter

Enable only after provider approval, agreements, and PHI applicability review. Set `TRANSCRIPTION_APPROVED=true`, an HTTPS `TRANSCRIPTION_ENDPOINT`, provider key, private S3 bucket, and KMS key. The worker POSTs multipart `audio`; the adapter must return `{"text":"exact provider transcript"}`. A hospital-managed adapter can wrap an approved medical transcription SDK, including required residency and vocabulary configuration. No generic browser cloud speech service is enabled.

Audio upload is capped at 25 MB. Pause/resume and playback work in the browser. Split larger recordings into separate reports; streaming long-form upload/chunk assembly is not implemented. With retention zero, the worker deletes the temporary object after successful transcription; failed jobs are removed by retention maintenance and a private-bucket lifecycle rule. Reports retain original and edited text; the original cannot be overwritten by a doctor edit.

## Optional AI organization

Set approved HTTPS `SUMMARY_ENDPOINT` and key only after review. The adapter returns `items` containing category and exact `start`/`end` character offsets into the submitted final transcript. The backend constructs the displayed text from these source spans, so provider output cannot introduce an invented activity. Every summary stores the source SHA-256 and AI marker. Doctor edits are stored separately; transcript changes clear the prior summary.
