import test from "node:test";
import assert from "node:assert/strict";
import { api, snapshot } from "../worker/api.mjs";
import { seed } from "../worker/seed.mjs";
class DB {
  constructor() {
    this.rows = new Map();
  }
  prepare(sql) {
    let args = [];
    const self = this;
    return {
      bind(...a) {
        args = a;
        return this;
      },
      async first() {
        return self.rows.get(args[0]) || null;
      },
      async run() {
        if (sql.startsWith("INSERT")) {
          if (!self.rows.has(args[0]))
            self.rows.set(args[0], { data: args[1], version: 1 });
          return { meta: { changes: 1 } };
        }
        const row = self.rows.get(args[1]);
        if (row?.version !== args[2]) return { meta: { changes: 0 } };
        self.rows.set(args[1], { data: args[0], version: row.version + 1 });
        return { meta: { changes: 1 } };
      },
    };
  }
}
const env = { DB: new DB() };
function req(path, method = "GET", body, role = "admin", owner = "owner-a") {
  return new Request("https://medflow.test/api" + path, {
    method,
    headers: {
      "oai-authenticated-user-id": owner,
      origin: "https://medflow.test",
      cookie: "medflow_view=" + role,
      ...(body ? { "content-type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
}
test("missing authenticated visitor is denied", async () =>
  assert.equal(
    (await api(new Request("https://medflow.test/api/dashboard"), env)).status,
    401,
  ));
test("doctor dashboard contains only own records", async () => {
  const d = await (
    await api(req("/dashboard", "GET", undefined, "doctor"), env)
  ).json();
  assert.deepEqual(
    d.doctors.map((d) => d.id),
    ["doctor-0"],
  );
  assert(d.reports.every((r) => r.doctor_id === "doctor-0"));
  assert.equal(d.audit.length, 0);
});
test("doctor cannot retrieve peer transcript by URL", async () =>
  assert.equal(
    (await api(req("/reports/report-1", "GET", undefined, "doctor"), env))
      .status,
    404,
  ));
test("doctor cannot add staff", async () =>
  assert.equal(
    (await api(req("/users", "POST", {}, "doctor"), env)).status,
    403,
  ));
test("reports persist under authenticated doctor identity", async () => {
  const r = await api(
    req(
      "/reports",
      "POST",
      {
        doctor_id: "doctor-20",
        original_transcript: "Dictation",
        edited_transcript: "Daily meeting",
        category: "Meetings",
      },
      "doctor",
    ),
    env,
  );
  assert.equal(r.status, 201);
  const report = await r.json();
  assert.equal(report.doctor_id, "doctor-0");
  const fetched = await (
    await api(req("/reports/" + report.id, "GET", undefined, "doctor"), env)
  ).json();
  assert.equal(fetched.edited_transcript, "Daily meeting");
});
test("workspaces are isolated between owners", async () => {
  const b = await (
    await api(req("/dashboard", "GET", undefined, "admin", "owner-b"), env)
  ).json();
  assert(!b.reports.some((r) => r.edited_transcript === "Daily meeting"));
});
test("cross-origin mutations denied", async () => {
  const r = req("/users", "POST", {});
  r.headers.set("origin", "https://evil.test");
  assert.equal((await api(r, env)).status, 403);
});
test("transcription stays disabled without approved provider", async () =>
  assert.equal(
    (await api(req("/transcriptions", "POST", {}, "doctor"), env)).status,
    503,
  ));
test("exports are scoped to doctor", async () => {
  const result = await (
    await api(req("/export", "GET", undefined, "doctor"), env)
  ).text();
  assert(result.includes("Jane Smith"));
  assert(!result.includes("John Lee"));
});
test("PDF export returns PDF bytes", async () => {
  const r = await api(req("/export?format=pdf"), env);
  assert.equal(r.headers.get("content-type"), "application/pdf");
  assert((await r.text()).startsWith("%PDF-1.4"));
});
test("invalid correction is rejected", async () =>
  assert.equal(
    (
      await api(
        req(
          "/corrections",
          "POST",
          {
            requested_changes: {
              started_at: "bad",
              ended_at: "bad",
              location_id: "main",
            },
            reason: "Missing connection",
          },
          "doctor",
        ),
        env,
      )
    ).status,
    422,
  ));
test("duplicate network source event is idempotent", async () => {
  const body = {
    doctor_id: "doctor-0",
    location_id: "main",
    event_type: "start",
    source_event_id: "one",
  };
  await api(req("/sandbox/events", "POST", body), env);
  const r = await (await api(req("/sandbox/events", "POST", body), env)).json();
  assert.equal(r.duplicate, true);
});
