# Release acceptance and honest limits

The code has automated coverage for authorization, RLS, interval calculations, DST, exports, duplicate handling, and isolated sandbox behavior. Those tests do not justify calling an unconnected installation production ready.

Before a live rollout, the hospital’s named IT/security/privacy/HR reviewers must explicitly review and approve:

- Employee monitoring purpose, workforce notice/consent where applicable, local employment/monitoring law, access policy, retention/deletion, correction rights, and whether HIPAA or other health-data regulations apply.
- IdP membership provisioning, enforced MFA claims, offboarding/session revocation, origin/TLS configuration, secrets rotation, database grants/RLS, and tenant separation under penetration testing.
- Vendor equipment accounting behavior: EAP-TLS identity mapping, interims, AP roaming, missing starts/stops, power loss, clock skew, delayed/out-of-order events, and multiple devices in separate buildings. Compare physical test observations with derived timelines.
- Transcription/AI provider approval, residency, subprocessors, business associate/data processing agreements when applicable, vocabulary accuracy, audio retention, and report content restrictions.
- Expected event rate/retention data volume, worker backlog recovery, connection pools, database indexes, SSE fan-out, replay cost, disaster recovery exercise, RPO/RTO, and incident alerts.

Known implementation boundaries:

| Area | Current behavior / remaining validation |
| --- | --- |
| Hospital connectivity | No live hardware connected; RADIUS relay + normalized adapter supplied. Vendor SDK adapters require actual equipment. |
| Scale | Multiple API/workers supported; full retained-history replay needs checkpoints/partitioning for large histories. No thousands-user load benchmark performed. |
| Audio | Browser record/pause/resume/playback; uploads ≤25 MB; approved provider adapter required; streaming chunk assembly not included. |
| Identity | OIDC PKCE/MFA implemented; SAML via approved OIDC federation broker. No IdP tenant configured here. |
| Analytics | Daily records, weekly charts, location distribution, date selection, individual timelines, CSV/PDF. Dedicated monthly/annual heatmaps, average-arrival statistics, and rich arbitrary-range reporting remain extensions. |
| Presence | Network evidence and uncertainty; no proof of personal presence or work. Grace bridging is visibly inferred. |
| Administration | Doctor add/disable, department search, location/network mapping, correction and report review, audit access. Enterprise invitation/email delivery and employee consent acknowledgment collection require organizational integrations. |
| Notifications | In-app updates/SSE and stored preferences. Email delivery is not configured. |
| Recovery | Disposable PostgreSQL migration tested. A managed-cloud backup/restore exercise needs the deployed environment. |
| Hosting | Sites deployment is owner-private fictional sandbox. Production FastAPI/PostgreSQL/AWS stack is supplied as source/configuration, not deployed to a hospital. |

Encryption, authentication, and this checklist do not establish HIPAA compliance. Document the deployment’s actual controls, agreements, evidence, and reviewers before changing its status.
