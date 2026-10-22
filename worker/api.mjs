import { seed } from "./seed.mjs";
const json = (value, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
    },
  });
const fail = (message, status = 400) => {
  throw Object.assign(new Error(message), { status });
};
const id = () => crypto.randomUUID();
const now = () => new Date().toISOString();
const dateKey = (s) =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(s));
function audit(state, role, action, resource_type, resource_id = "") {
  state.audit.unshift({
    id: id(),
    actor_id: role === "admin" ? "admin" : "doctor-0",
    action,
    resource_type,
    resource_id,
    timestamp: now(),
    outcome: "success",
  });
  state.audit = state.audit.slice(0, 500);
}
export function snapshot(state, role, date, period = "This week") {
  const today = date || dateKey(now());
  const all = role === "admin";
  const sessions = state.sessions.filter(
    (s) =>
      (all || s.doctor_id === "doctor-0") && dateKey(s.started_at) === today,
  );
  const doctors = state.doctors
    .filter((d) => all || d.id === "doctor-0")
    .map((d) => {
      const own = sessions.filter(
        (s) => s.doctor_id === d.id && s.location_id !== "unknown",
      );
      const seconds = own.reduce((a, s) => a + s.duration_seconds, 0);
      return {
        ...d,
        hours: Math.round(seconds / 36) / 100,
        first_arrival: own.length
          ? own.reduce(
              (a, s) => (s.started_at < a ? s.started_at : a),
              own[0].started_at,
            )
          : null,
      };
    });
  const reports = state.reports
    .filter((r) => all || r.doctor_id === "doctor-0")
    .map((r) => ({
      ...r,
      doctor_name:
        state.doctors.find((d) => d.id === r.doctor_id)?.full_name || "Doctor",
    }));
  const corrections = state.corrections
    .filter((c) => all || c.doctor_id === "doctor-0")
    .map((c) => ({
      ...c,
      doctor_name:
        state.doctors.find((d) => d.id === c.doctor_id)?.full_name || "Doctor",
    }));
  const monday = new Date(today + "T12:00:00Z");
  monday.setUTCDate(
    monday.getUTCDate() -
      ((monday.getUTCDay() + 6) % 7) -
      (period === "Last week" ? 7 : 0),
  );
  const weekly = Array.from({ length: 7 }, (_, i) => {
    const dt = new Date(monday);
    dt.setUTCDate(dt.getUTCDate() + i);
    const ds = state.sessions.filter(
      (s) =>
        (all || s.doctor_id === "doctor-0") &&
        dateKey(s.started_at) === dateKey(dt),
    );
    const total = (loc) =>
      Math.round(
        ds
          .filter((s) => s.location_id === loc)
          .reduce((a, s) => a + s.duration_seconds / 3600, 0) * 10,
      ) / 10;
    return {
      day: dt.toLocaleDateString("en-US", {
        weekday: "short",
        timeZone: "UTC",
      }),
      date: dt.toISOString().slice(0, 10),
      main: total("main"),
      office: total("office"),
      clinic: total("clinic"),
      own:
        Math.round(
          ds.reduce((a, s) => a + s.duration_seconds / 3600, 0) * 100,
        ) / 100,
    };
  });
  const { identity_reference, ...user } = all ? state.admin : state.doctors[0];
  return {
    mode: "sandbox",
    role,
    user,
    doctors,
    locations: state.locations.map((l) => ({
      ...l,
      count: doctors.filter(
        (d) => d.location_id === l.id && d.status === "Present",
      ).length,
    })),
    sessions,
    reports,
    corrections,
    audit: all ? state.audit.slice(0, 100) : [],
    weekly,
    settings: state.settings,
    metrics: {
      total: doctors.length,
      present: doctors.filter((d) => d.status === "Present").length,
      hours: Math.round(doctors.reduce((a, d) => a + d.hours, 0) * 10) / 10,
      reports: reports.length,
      pending: reports.filter((r) => r.review_status === "pending").length,
      exceptions: corrections.filter((c) => c.approval_status === "pending")
        .length,
    },
    updated_at: now(),
  };
}
function allowed(obj, role) {
  if (!obj || (role !== "admin" && obj.doctor_id !== "doctor-0"))
    fail("Record not found", 404);
  return obj;
}
function admin(role) {
  if (role !== "admin") fail("Administrator permission required", 403);
}
function text(value, min = 1, max = 100000) {
  if (
    typeof value !== "string" ||
    value.trim().length < min ||
    value.length > max
  )
    fail("Invalid or missing text field", 422);
  return value.trim();
}
function location(state, lid) {
  const l = state.locations.find((l) => l.id === lid);
  if (!l) fail("Location not found", 404);
  return l;
}
function validTimes(changes) {
  const a = Date.parse(changes.started_at),
    b = Date.parse(changes.ended_at);
  if (!Number.isFinite(a) || !Number.isFinite(b) || b <= a || b - a > 86400000)
    fail("Invalid attendance period: maximum 24 hours", 422);
  return [a, b];
}
function clipOverlaps(state, doctorId, a, b) {
  state.sessions = state.sessions.flatMap((s) => {
    if (s.doctor_id !== doctorId) return [s];
    const x = Date.parse(s.started_at),
      y = Date.parse(s.ended_at || now());
    if (y <= a || x >= b) return [s];
    const pieces = [];
    if (x < a)
      pieces.push({
        ...s,
        id: id(),
        ended_at: new Date(a).toISOString(),
        duration_seconds: Math.floor((a - x) / 1000),
      });
    if (y > b)
      pieces.push({
        ...s,
        id: id(),
        started_at: new Date(b).toISOString(),
        duration_seconds: Math.floor((y - b) / 1000),
      });
    return pieces;
  });
}
const categories = [
  "Patient Care",
  "Consultations",
  "Administrative Duties",
  "Surgery / Procedures",
  "Meetings",
  "Research",
  "Teaching",
  "Other",
];
export async function api(request, env) {
  try {
    const url = new URL(request.url);
    const path = url.pathname.replace(/^\/api/, "");
    const method = request.method;
    const owner = request.headers.get("oai-authenticated-user-id");
    if (!owner)
      return json({ detail: "Sign in to your private Medflow workspace" }, 401);
    if (!env.DB)
      return json({ detail: "Sandbox database binding is unavailable" }, 503);
    const role =
      request.headers
        .get("cookie")
        ?.split(";")
        .map((v) => v.trim())
        .find((v) => v.startsWith("medflow_view="))
        ?.split("=")[1] === "doctor"
        ? "doctor"
        : "admin";
    if (method !== "GET" && method !== "HEAD") {
      if (request.headers.get("origin") !== url.origin)
        fail("Invalid request origin", 403);
      if (Number(request.headers.get("content-length") || 0) > 1048576)
        fail("Request too large", 413);
    }
    let row = await env.DB.prepare(
      "SELECT data, version FROM sandbox_workspaces WHERE owner = ?",
    )
      .bind(owner)
      .first();
    if (!row) {
      const initial = seed(owner);
      await env.DB.prepare(
        "INSERT OR IGNORE INTO sandbox_workspaces (owner,data,version) VALUES (?,?,1)",
      )
        .bind(owner, JSON.stringify(initial))
        .run();
      row = await env.DB.prepare(
        "SELECT data, version FROM sandbox_workspaces WHERE owner = ?",
      )
        .bind(owner)
        .first();
    }
    const state = JSON.parse(row.data);
    let result = {},
      changed = false,
      status = 200,
      headers = {};
    const save = async () => {
      const r = await env.DB.prepare(
        "UPDATE sandbox_workspaces SET data=?,version=version+1 WHERE owner=? AND version=?",
      )
        .bind(JSON.stringify(state), owner, row.version)
        .run();
      if (!r.meta.changes)
        fail("Workspace changed concurrently. Please retry.", 409);
    };
    if (path === "/dashboard" && method === "GET") {
      audit(state, role, "read", "dashboard");
      await save();
      return json(
        snapshot(
          state,
          role,
          url.searchParams.get("date"),
          url.searchParams.get("period") || "This week",
        ),
      );
    }
    if (path === "/sandbox/context" && method === "POST") {
      // Only the authenticated owner can access this private, fictional sandbox.
      // This selector previews permissions; it is never included in the FastAPI production server.
      const b = await request.json();
      if (!["admin", "doctor"].includes(b.role))
        fail("Invalid sandbox view", 422);
      headers = {
        "Set-Cookie": `medflow_view=${b.role}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=28800`,
      };
      result = { role: b.role };
    } else if (/^\/reports\/[^/]+\/summary$/.test(path)) {
      fail(
        "An approved AI summary provider is not connected to this sandbox. Use the production provider adapter.",
        503,
      );
    } else if (path === "/reports" && method === "POST") {
      if (role !== "doctor")
        fail("Use the doctor view to author a report", 403);
      const b = await request.json();
      if (!categories.includes(b.category))
        fail("Invalid activity category", 422);
      if (b.location_id) location(state, b.location_id);
      result = {
        id: id(),
        doctor_id: "doctor-0",
        location_id: b.location_id || null,
        original_transcript: text(b.original_transcript),
        edited_transcript: text(b.edited_transcript),
        category: b.category,
        tags: [],
        created_at: now(),
        updated_at: now(),
        review_status: "pending",
      };
      state.reports.unshift(result);
      audit(state, role, "create", "activity_report", result.id);
      changed = true;
      status = 201;
    } else if (/^\/reports\/[^/]+\/review$/.test(path) && method === "POST") {
      admin(role);
      const r = allowed(
        state.reports.find((r) => r.id === path.split("/")[2]),
        role,
      );
      r.review_status = "reviewed";
      audit(state, role, "review", "activity_report", r.id);
      changed = true;
      result = r;
    } else if (/^\/reports\/[^/]+$/.test(path)) {
      const r = allowed(
        state.reports.find((r) => r.id === path.split("/")[2]),
        role,
      );
      if (method === "GET") {
        audit(state, role, "read", "activity_report", r.id);
        changed = true;
        result = r;
      } else if (method === "PATCH") {
        if (role !== "doctor" || r.doctor_id !== "doctor-0")
          fail("Only the author may edit a transcript", 403);
        const b = await request.json();
        if (!categories.includes(b.category))
          fail("Invalid activity category", 422);
        r.edited_transcript = text(b.edited_transcript);
        r.category = b.category;
        r.updated_at = now();
        r.review_status = "pending";
        audit(state, role, "update", "activity_report", r.id);
        changed = true;
        result = r;
      } else fail("Method not allowed", 405);
    } else if (path === "/users" && method === "POST") {
      admin(role);
      const b = await request.json();
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(b.email || ""))
        fail("A valid email is required", 422);
      if (
        state.doctors.some(
          (d) => d.email.toLowerCase() === b.email.toLowerCase(),
        )
      )
        fail("A doctor with this email already exists", 409);
      const name = text(b.full_name, 2, 100);
      text(b.identity_reference, 1, 250);
      result = {
        id: id(),
        full_name: name,
        email: b.email.toLowerCase(),
        department: text(b.department, 1, 100),
        identity_reference: b.identity_reference,
        location: null,
        location_id: null,
        status: "Absent",
        hours: 0,
        first_arrival: null,
        last_seen: null,
        initials: name
          .replace("Dr. ", "")
          .split(" ")
          .map((v) => v[0])
          .slice(0, 2)
          .join(""),
        color: "#e2ece8",
      };
      state.doctors.push(result);
      audit(state, role, "create", "user", result.id);
      changed = true;
      status = 201;
    } else if (/^\/users\/[^/]+$/.test(path)) {
      const d = state.doctors.find((d) => d.id === path.split("/")[2]);
      if (!d || (role !== "admin" && d.id !== "doctor-0"))
        fail("Record not found", 404);
      if (method === "PATCH") {
        admin(role);
        const b = await request.json();
        if (!["active", "disabled"].includes(b.status))
          fail("Invalid account status", 422);
        d.status = b.status === "disabled" ? "Disabled" : "Absent";
        d.location = null;
        d.location_id = null;
        audit(state, role, "update", "user", d.id);
        changed = true;
      }
      result = d;
    } else if (path === "/locations" && method === "POST") {
      admin(role);
      const b = await request.json();
      try {
        new Intl.DateTimeFormat("en-US", { timeZone: b.timezone }).format(
          new Date(),
        );
      } catch {
        fail("Invalid IANA timezone", 422);
      }
      result = {
        id: id(),
        name: text(b.name, 2, 100),
        building: text(b.building, 1, 150),
        timezone: b.timezone,
        ssid: text(b.ssid, 1, 100),
        active: true,
        capacity: 20,
        color: "#188e82",
      };
      state.locations.push(result);
      audit(state, role, "create", "location", result.id);
      changed = true;
      status = 201;
    } else if (/^\/locations\/[^/]+$/.test(path) && method === "PATCH") {
      admin(role);
      const l = location(state, path.split("/")[2]);
      const b = await request.json();
      try {
        new Intl.DateTimeFormat("en-US", { timeZone: b.timezone }).format(
          new Date(),
        );
      } catch {
        fail("Invalid IANA timezone", 422);
      }
      l.name = text(b.name, 2, 100);
      l.ssid = text(b.ssid, 1, 100);
      l.timezone = b.timezone;
      l.active = b.active === true || b.active === "true";
      if (!l.active)
        for (const d of state.doctors.filter((d) => d.location_id === l.id)) {
          d.location_id = null;
          d.location = null;
          d.status = "Last seen";
        }
      audit(state, role, "update", "location", l.id);
      changed = true;
      result = l;
    } else if (path === "/profile" && method === "PATCH") {
      const b = await request.json();
      (role === "admin" ? state.admin : state.doctors[0]).full_name = text(
        b.full_name,
        2,
        100,
      );
      state.settings.notifications = !!b.notifications;
      audit(state, role, "update", "profile");
      changed = true;
    } else if (path === "/corrections" && method === "POST") {
      if (role !== "doctor") fail("Doctor account required", 403);
      const b = await request.json();
      if (b.session_id)
        allowed(
          state.sessions.find((s) => s.id === b.session_id),
          role,
        );
      validTimes(b.requested_changes);
      location(state, b.requested_changes.location_id);
      result = {
        id: id(),
        doctor_id: "doctor-0",
        session_id: b.session_id || null,
        requested_changes: b.requested_changes,
        reason: text(b.reason, 10, 2000),
        approval_status: "pending",
        created_at: now(),
      };
      state.corrections.unshift(result);
      audit(state, role, "create", "attendance_correction", result.id);
      changed = true;
    } else if (
      /^\/corrections\/[^/]+\/review$/.test(path) &&
      method === "POST"
    ) {
      admin(role);
      const c = state.corrections.find((c) => c.id === path.split("/")[2]);
      if (!c) fail("Correction not found", 404);
      if (c.approval_status !== "pending")
        fail("This correction was already reviewed", 409);
      const b = await request.json();
      if (!["approved", "rejected"].includes(b.decision))
        fail("Invalid decision", 422);
      if (b.decision === "approved") {
        const [a, z] = validTimes(c.requested_changes);
        const l = location(state, c.requested_changes.location_id);
        clipOverlaps(state, c.doctor_id, a, z);
        state.sessions.push({
          id: id(),
          doctor_id: c.doctor_id,
          location_id: l.id,
          location: l.name,
          started_at: new Date(a).toISOString(),
          ended_at: new Date(z).toISOString(),
          duration_seconds: Math.floor((z - a) / 1000),
          confidence_status: "manually_corrected",
          source: "correction",
        });
      }
      c.approval_status = b.decision;
      c.reviewed_by = "admin";
      c.reviewed_at = now();
      audit(state, role, "review:" + b.decision, "attendance_correction", c.id);
      changed = true;
      result = c;
    } else if (path === "/checkin" && method === "POST") {
      if (role !== "doctor") fail("Doctor account required", 403);
      const b = await request.json();
      const l = location(state, b.location_id);
      text(b.reason, 5, 2000);
      const opened = state.sessions.find(
        (s) =>
          s.doctor_id === "doctor-0" && s.source === "manual" && !s.ended_at,
      );
      if (b.action === "start") {
        if (opened) fail("You already have an open check-in", 409);
        state.sessions.push({
          id: id(),
          doctor_id: "doctor-0",
          location_id: l.id,
          location: l.name,
          started_at: now(),
          ended_at: null,
          duration_seconds: 0,
          confidence_status: "unverified",
          source: "manual",
        });
        state.doctors[0].status = "Last seen";
        state.doctors[0].location_id = l.id;
        state.doctors[0].location = l.name;
      } else if (b.action === "stop") {
        if (!opened) fail("No open manual check-in", 409);
        const end = now(),
          a = Date.parse(opened.started_at),
          b = Date.parse(end);
        state.sessions = state.sessions.filter((s) => s.id !== opened.id);
        clipOverlaps(state, "doctor-0", a, b);
        state.sessions.push({
          ...opened,
          ended_at: end,
          duration_seconds: Math.floor((b - a) / 1000),
        });
        state.doctors[0].location_id = null;
        state.doctors[0].location = null;
        state.doctors[0].status = "Last seen";
      } else fail("Invalid check-in action", 422);
      audit(state, role, "manual:" + b.action, "attendance");
      changed = true;
    } else if (path === "/sandbox/events" && method === "POST") {
      admin(role);
      const b = await request.json();
      const d = state.doctors.find((d) => d.id === b.doctor_id);
      const l = location(state, b.location_id);
      if (!d || d.status === "Disabled" || !l.active)
        fail("Active enrolled doctor and location required", 422);
      if (!["start", "stop", "interim"].includes(b.event_type))
        fail("Invalid accounting event", 422);
      const stamp = now();
      const source_event_id = b.source_event_id || id();
      if (state.events.some((e) => e.source_event_id === source_event_id))
        return json({ duplicate: true });
      state.events.push({
        id: id(),
        doctor_id: d.id,
        location_id: l.id,
        event_type: b.event_type,
        source_event_id,
        event_timestamp: stamp,
        received_timestamp: stamp,
        provider: "simulator",
      });
      const opened = state.sessions.find(
        (s) => s.doctor_id === d.id && s.source === "simulator" && !s.ended_at,
      );
      if (b.event_type === "stop") {
        if (opened) {
          opened.ended_at = stamp;
          opened.duration_seconds = Math.max(
            0,
            Math.floor(
              (Date.parse(stamp) - Date.parse(opened.started_at)) / 1000,
            ),
          );
        }
        d.status = "Last seen";
        d.location = null;
        d.location_id = null;
      } else {
        if (opened && opened.location_id !== l.id) {
          opened.ended_at = stamp;
          opened.duration_seconds = Math.max(
            0,
            Math.floor(
              (Date.parse(stamp) - Date.parse(opened.started_at)) / 1000,
            ),
          );
        }
        if (!opened || opened.location_id !== l.id) {
          const a = Date.parse(stamp);
          clipOverlaps(state, d.id, a, a + 1);
          state.sessions.push({
            id: id(),
            doctor_id: d.id,
            location_id: l.id,
            location: l.name,
            started_at: stamp,
            ended_at: null,
            duration_seconds: 0,
            confidence_status: "simulated",
            source: "simulator",
          });
        }
        d.status = "Present";
        d.location_id = l.id;
        d.location = l.name;
      }
      d.last_seen = stamp;
      audit(state, role, "simulate:" + b.event_type, "network_event");
      changed = true;
      result = { status: "processed", source_event_id };
    } else if (path === "/transcriptions" && method === "POST") {
      fail(
        "No approved transcription provider is connected to this sandbox. Your audio stays in this browser. Enter the transcript manually, or configure the production transcription adapter.",
        503,
      );
    } else if (path === "/export" && method === "GET") {
      const d = snapshot(state, role, url.searchParams.get("date"));
      const dept = url.searchParams.get("department"),
        facility = url.searchParams.get("facility");
      const rows = d.doctors.filter(
        (d) =>
          (!dept || dept === "All departments" || d.department === dept) &&
          (!facility ||
            facility === "All locations" ||
            d.location === facility),
      );
      audit(state, role, "export", "attendance");
      await save();
      if (url.searchParams.get("format") === "pdf")
        return pdf(rows, url.searchParams.get("date") || dateKey(now()));
      const escape = (v) => {
        let s = String(v ?? "");
        if (/^[=+@\-\t\r]/.test(s)) s = "'" + s;
        return '"' + s.replaceAll('"', '""') + '"';
      };
      return new Response(
        [
          [
            "Doctor",
            "Department",
            "Location",
            "First arrival (UTC)",
            "Detected hours",
            "Status",
          ],
          ...rows.map((d) => [
            d.full_name,
            d.department,
            d.location || "Unknown",
            d.first_arrival,
            d.hours,
            d.status,
          ]),
        ]
          .map((r) => r.map(escape).join(","))
          .join("\r\n"),
        {
          headers: {
            "Content-Type": "text/csv;charset=utf-8",
            "Content-Disposition":
              'attachment; filename="medflow-attendance.csv"',
            "Cache-Control": "no-store",
          },
        },
      );
    } else if (path === "/attendance" && method === "GET") {
      if (
        role !== "admin" &&
        url.searchParams.has("doctor_id") &&
        url.searchParams.get("doctor_id") !== "doctor-0"
      )
        fail("Only your attendance is accessible", 403);
      result = snapshot(state, role).sessions;
    } else if (path === "/reports" && method === "GET")
      result = snapshot(state, role).reports;
    else if (path === "/audit" && method === "GET") {
      admin(role);
      result = state.audit;
    } else if (path === "/me" && method === "GET")
      result = snapshot(state, role).user;
    else fail("API route not found", 404);
    if (changed) await save();
    const response = json(result, status);
    for (const [k, v] of Object.entries(headers)) response.headers.set(k, v);
    return response;
  } catch (e) {
    return json(
      {
        detail: e.status
          ? e.message
          : "The workspace could not complete this request",
      },
      e.status || 500,
    );
  }
}
function pdf(rows, date) {
  const lines = [
    "Medflow - Attendance report",
    date,
    "Network detection does not verify clinical work.",
    "",
    ...rows.flatMap((d) => [
      d.full_name + " | " + d.department,
      (d.location || "Unknown") + " | " + d.hours + " hours | " + d.status,
      "",
    ]),
  ];
  const pages = [];
  for (let i = 0; i < lines.length; i += 45) pages.push(lines.slice(i, i + 45));
  const objects = [
      "<< /Type /Catalog /Pages 2 0 R >>",
      "",
      "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ],
    refs = [];
  for (const page of pages) {
    const pid = objects.length + 1;
    refs.push(pid + " 0 R");
    objects.push(
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents ${pid + 1} 0 R >>`,
    );
    const stream =
      "BT /F1 10 Tf 45 750 Td 15 TL " +
      page
        .map(
          (l) =>
            "(" +
            l
              .replaceAll("\\", "\\\\")
              .replaceAll("(", "\\(")
              .replaceAll(")", "\\)")
              .replace(/[^\x20-\x7e]/g, "?") +
            ") Tj T*",
        )
        .join(" ") +
      " ET";
    objects.push(
      `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
    );
  }
  objects[1] = `<< /Type /Pages /Count ${pages.length} /Kids [${refs.join(" ")}] >>`;
  let content = "%PDF-1.4\n";
  const offsets = [0];
  for (let i = 0; i < objects.length; i++) {
    offsets.push(content.length);
    content += `${i + 1} 0 obj\n${objects[i]}\nendobj\n`;
  }
  const xref = content.length;
  content +=
    `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n` +
    offsets
      .slice(1)
      .map((n) => String(n).padStart(10, "0") + " 00000 n \n")
      .join("") +
    `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
  return new Response(content, {
    headers: {
      "Content-Type": "application/pdf",
      "Cache-Control": "no-store",
      "Content-Disposition": 'attachment; filename="medflow-attendance.pdf"',
    },
  });
}
