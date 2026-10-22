"use client";
import { useState, useEffect, useRef, useMemo } from "react";
import {
  Activity,
  LayoutDashboard,
  Users,
  Clock3,
  Mic,
  MapPin,
  ChartNoAxesCombined,
  Settings,
  ChevronDown,
  ChevronRight,
  ChevronLeft,
  ArrowUpRight,
  ArrowDownToLine,
  Search,
  Bell,
  Plus,
  Check,
  CheckCheck,
  Wifi,
  ShieldCheck,
  HelpCircle,
  LogOut,
  Building2,
  CalendarDays,
  ArrowRight,
  MoreHorizontal,
  FileText,
  X,
  Menu,
  Loader2,
  Pause,
  Play,
  Square,
  Volume2,
  Radio,
  TriangleAlert,
  CheckCircle2,
  SlidersHorizontal,
  RefreshCw,
  Laptop,
  Mail,
  ExternalLink,
  Download,
  Filter,
} from "lucide-react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  PieChart,
  Pie,
  Cell,
  AreaChart,
  Area,
} from "recharts";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";

type Doctor = {
  id: string;
  full_name: string;
  email: string;
  department: string;
  location: string | null;
  location_id: string | null;
  status: string;
  hours: number;
  first_arrival: string | null;
  last_seen: string | null;
  initials: string;
  color: string;
};
type Location = {
  id: string;
  name: string;
  building: string;
  timezone: string;
  ssid: string;
  active: boolean;
  count: number;
  capacity: number;
  color: string;
};
type Report = {
  id: string;
  doctor_id: string;
  doctor_name: string;
  original_transcript: string;
  edited_transcript: string;
  category: string;
  location_id: string | null;
  created_at: string;
  review_status: string;
  tags: string[];
  summary?: {
    ai_generated: boolean;
    items: { text: string; category: string; start: number; end: number }[];
    reviewed: boolean;
  };
};
type Session = {
  id: string;
  doctor_id: string;
  location_id: string;
  location: string;
  started_at: string;
  ended_at: string | null;
  duration_seconds: number;
  confidence_status: string;
  source: string;
};
type Correction = {
  id: string;
  doctor_id: string;
  doctor_name: string;
  reason: string;
  approval_status: string;
  requested_changes: Record<string, string>;
  created_at: string;
};
type Data = {
  mode: string;
  role: string;
  user: { id: string; full_name: string; email: string; department: string };
  doctors: Doctor[];
  locations: Location[];
  reports: Report[];
  sessions: Session[];
  corrections: Correction[];
  audit: any[];
  weekly: any[];
  metrics: {
    total: number;
    present: number;
    hours: number;
    reports: number;
    pending: number;
    exceptions: number;
  };
  updated_at: string;
  settings: any;
};
const API = process.env.NEXT_PUBLIC_API_URL || "";
async function request(path: string, method = "GET", body?: unknown) {
  const r = await fetch(API + "/api" + path, {
    method,
    credentials: "include",
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    const e = await r
      .json()
      .catch(() => ({ detail: "Unable to complete request" }));
    throw Error(
      typeof e.detail === "string"
        ? e.detail
        : e.error || "Unable to complete request",
    );
  }
  return r.headers.get("content-type")?.includes("json") ? r.json() : r;
}
const navs = [
  { name: "Overview", icon: LayoutDashboard },
  { name: "Doctors", icon: Users },
  { name: "Attendance", icon: Clock3 },
  { name: "Activity reports", icon: Mic },
  { name: "Locations & networks", icon: MapPin },
  { name: "Reports & analytics", icon: ChartNoAxesCombined },
];
const colors = ["#188e82", "#5689aa", "#bccdd6", "#b4dad4"];
const dateLabel = (
  s: string | null,
  opts: Intl.DateTimeFormatOptions = { hour: "2-digit", minute: "2-digit" },
) =>
  s
    ? new Intl.DateTimeFormat("en-US", {
        ...opts,
        timeZone: "America/New_York",
      }).format(new Date(s))
    : "—";
const hours = (n: number) => {
  const minutes = Math.max(0, Math.round(n * 60));
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
};
function Avatar({
  doctor,
  small = false,
}: {
  doctor: { full_name: string; color?: string; initials?: string };
  small?: boolean;
}) {
  return (
    <span
      className={"avatar " + (small ? "avatar-sm" : "")}
      style={{ background: doctor.color || "#e3edef" }}
    >
      {doctor.initials ||
        doctor.full_name
          .replace("Dr. ", "")
          .split(" ")
          .map((s) => s[0])
          .slice(0, 2)
          .join("")}
    </span>
  );
}
function Badge({ status }: { status: string }) {
  return (
    <span
      className={
        "badge " +
        (status === "Present" || status === "approved" || status === "reviewed"
          ? "badge-green"
          : status === "Last seen" || status === "pending"
            ? "badge-amber"
            : "badge-gray")
      }
    >
      <i />
      {status === "Present"
        ? "Device detected"
        : status === "Absent"
          ? "No signal"
          : status.replaceAll("_", " ")}
    </span>
  );
}

export default function App() {
  const [data, setData] = useState<Data | null>(null),
    [page, setPage] = useState("Overview"),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [toast, setToast] = useState(""),
    [search, setSearch] = useState(""),
    [department, setDepartment] = useState("All departments"),
    [facility, setFacility] = useState("All locations"),
    [period, setPeriod] = useState("This week"),
    [mobile, setMobile] = useState(false),
    [modal, setModal] = useState(""),
    [selected, setSelected] = useState<Doctor | null>(null),
    [selectedReport, setSelectedReport] = useState<Report | null>(null),
    [notifications, setNotifications] = useState(false),
    [calendarDate, setCalendarDate] = useState(
      new Date().toISOString().slice(0, 10),
    ),
    [busy, setBusy] = useState(false);
  const [recording, setRecording] = useState(false),
    [paused, setPaused] = useState(false),
    [seconds, setSeconds] = useState(0),
    [audioURL, setAudioURL] = useState(""),
    [audioBlob, setAudioBlob] = useState<Blob | null>(null),
    [transcript, setTranscript] = useState(""),
    [original, setOriginal] = useState(""),
    [category, setCategory] = useState("Patient Care"),
    [recordError, setRecordError] = useState("");
  const recorder = useRef<MediaRecorder | null>(null),
    stream = useRef<MediaStream | null>(null),
    chunks = useRef<Blob[]>([]),
    searchRef = useRef<HTMLInputElement>(null);
  const admin = data?.role === "admin";
  const refreshRef = useRef<() => Promise<void>>(async () => {});
  async function refresh() {
    try {
      setData(
        await request(
          "/dashboard?date=" +
            calendarDate +
            "&period=" +
            encodeURIComponent(period),
        ),
      );
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  refreshRef.current = refresh;
  useEffect(() => {
    refresh();
    const interval = setInterval(() => refreshRef.current(), 20000);
    if ("serviceWorker" in navigator)
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    const key = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener("keydown", key);
    return () => {
      clearInterval(interval);
      window.removeEventListener("keydown", key);
      stream.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);
  useEffect(() => {
    if (data?.mode !== "production") return;
    const source = new EventSource(API + "/api/events", {
      withCredentials: true,
    });
    source.onmessage = (event) => {
      try {
        if (JSON.parse(event.data).type !== "heartbeat") refreshRef.current();
      } catch {}
    };
    return () => source.close();
  }, [data?.mode, data?.role]);
  useEffect(() => {
    if (toast) {
      const t = setTimeout(() => setToast(""), 4500);
      return () => clearTimeout(t);
    }
  }, [toast]);
  useEffect(() => {
    if (recording && !paused) {
      const t = setInterval(() => setSeconds((v) => v + 1), 1000);
      return () => clearInterval(t);
    }
  }, [recording, paused]);
  useEffect(
    () => () => {
      if (audioURL) URL.revokeObjectURL(audioURL);
    },
    [audioURL],
  );
  const filtered = useMemo(
    () =>
      data?.doctors.filter(
        (d) =>
          (d.full_name + " " + d.department + " " + d.email)
            .toLowerCase()
            .includes(search.toLowerCase()) &&
          (department === "All departments" || d.department === department) &&
          (facility === "All locations" || d.location === facility),
      ) || [],
    [data, search, department, facility],
  );
  const reports = useMemo(
    () =>
      data?.reports.filter((r) =>
        (r.doctor_name + " " + r.edited_transcript + " " + r.category)
          .toLowerCase()
          .includes(search.toLowerCase()),
      ) || [],
    [data, search],
  );
  const ownDoctor =
    data?.doctors.find((d) => d.id === data.user.id) || data?.doctors[0];
  async function mutate(
    path: string,
    body: unknown,
    message: string,
    method = "POST",
  ) {
    setBusy(true);
    try {
      await request(path, method, body);
      await refresh();
      setToast(message);
      setModal("");
    } catch (e) {
      setToast((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function context(role: string) {
    setLoading(true);
    try {
      await request("/sandbox/context", "POST", { role });
      setPage("Overview");
      setSearch("");
      setSelected(null);
      await refresh();
    } catch (e) {
      setToast((e as Error).message);
      setLoading(false);
    }
  }
  async function exportReport(format = "csv") {
    setBusy(true);
    try {
      const r = await fetch(
        API +
          `/api/export?format=${format}&department=${encodeURIComponent(department)}&facility=${encodeURIComponent(facility)}&date=${calendarDate}`,
        { credentials: "include" },
      );
      if (!r.ok) throw Error("Export failed");
      const blob = await r.blob();
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `medflow-attendance-${calendarDate}.${format}`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(link.href), 1000);
      setToast("Report exported. Access recorded in the audit log.");
    } catch (e) {
      setToast((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function startRecording() {
    setRecordError("");
    try {
      if (!navigator.mediaDevices?.getUserMedia)
        throw Error(
          "Microphone recording is unavailable in this browser. You can write your activity below.",
        );
      stream.current = await navigator.mediaDevices.getUserMedia({
        audio: true,
      });
      const mime = ["audio/webm", "audio/mp4", "audio/ogg"].find((t) =>
        MediaRecorder.isTypeSupported(t),
      );
      recorder.current = new MediaRecorder(
        stream.current,
        mime ? { mimeType: mime } : undefined,
      );
      chunks.current = [];
      recorder.current.ondataavailable = (e) => {
        if (e.data.size) chunks.current.push(e.data);
      };
      recorder.current.onstop = () => {
        const blob = new Blob(chunks.current, {
          type: recorder.current?.mimeType || "audio/webm",
        });
        setAudioBlob(blob);
        setAudioURL(URL.createObjectURL(blob));
        stream.current?.getTracks().forEach((t) => t.stop());
        setRecording(false);
      };
      recorder.current.start(1000);
      setSeconds(0);
      setRecording(true);
      setPaused(false);
    } catch (e) {
      setRecordError((e as Error).message);
    }
  }
  async function transcribe() {
    if (!audioBlob) return;
    setBusy(true);
    setRecordError("");
    try {
      const form = new FormData();
      form.append("audio", audioBlob, "activity.webm");
      const r = await fetch(API + "/api/transcriptions", {
        method: "POST",
        credentials: "include",
        body: form,
      });
      const job = await r.json();
      if (!r.ok) throw Error(job.detail || "Transcription unavailable");
      let result = job;
      for (
        let i = 0;
        i < 60 && ["queued", "processing"].includes(result.status);
        i++
      ) {
        await new Promise((r) => setTimeout(r, 2000));
        result = await request("/transcriptions/" + job.id);
      }
      if (result.status !== "completed")
        throw Error(
          result.error ||
            "Transcription is still processing. Please try again.",
        );
      setTranscript(result.transcript);
      setOriginal(result.transcript);
    } catch (e) {
      setRecordError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const nav = (name: string) => {
    setPage(name);
    setMobile(false);
    setSearch("");
    setSelected(null);
  };
  if (loading && !data)
    return (
      <div className="loading-screen">
        <div className="brand-mark">
          <Activity />
        </div>
        <h1>Medflow</h1>
        <p>{error || "Preparing your workspace…"}</p>
        {error ? (
          <Button onClick={refresh}>Try again</Button>
        ) : (
          <Loader2 className="spin" size={20} />
        )}
      </div>
    );
  if (!data)
    return (
      <div className="loading-screen">
        <ShieldCheck size={38} />
        <h1>Your secure workspace</h1>
        <p>{error}</p>
        <a
          className="btn btn-primary"
          href="/signin-with-chatgpt?return_to=/"
          target="_top"
        >
          Sign in to Medflow
        </a>
      </div>
    );
  const today = new Intl.DateTimeFormat("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "America/New_York",
  }).format(new Date());
  const title = selected
    ? selected.full_name
    : page === "Overview"
      ? admin
        ? "Workspace overview"
        : "My overview"
      : page;
  const weekly = data.weekly;
  function DoctorTable({ compact = false }: { compact?: boolean }) {
    return (
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Doctor</th>
              <th>Department</th>
              <th>Current location</th>
              <th>First arrival</th>
              <th>Hours today</th>
              <th>Status</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {filtered.slice(0, compact ? 6 : 100).map((d) => (
              <tr
                key={d.id}
                onClick={() => {
                  setSelected(d);
                  setPage("Doctors");
                }}
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    setSelected(d);
                    setPage("Doctors");
                  }
                }}
              >
                <td>
                  <div className="person">
                    <Avatar doctor={d} />
                    <div>
                      <strong>{d.full_name}</strong>
                      <span>{d.email}</span>
                    </div>
                  </div>
                </td>
                <td>{d.department}</td>
                <td>
                  <span className="location-cell">
                    {d.location ? <MapPin size={13} /> : null}
                    {d.location || "—"}
                  </span>
                </td>
                <td>{dateLabel(d.first_arrival)}</td>
                <td className="tabular">
                  <strong>{hours(d.hours)}</strong>
                </td>
                <td>
                  <Badge status={d.status} />
                </td>
                <td>
                  <ChevronRight size={15} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div className="empty">
            <Search />
            <h3>No doctors found</h3>
            <p>Try another name, department, or location.</p>
            <Button
              variant="outline"
              onClick={() => {
                setSearch("");
                setDepartment("All departments");
                setFacility("All locations");
              }}
            >
              Clear filters
            </Button>
          </div>
        )}
      </div>
    );
  }
  function Timeline({ sessions }: { sessions: Session[] }) {
    return (
      <div className="timeline-list">
        {sessions.length ? (
          sessions.map((s) => (
            <div className="timeline-item" key={s.id}>
              <span
                className={
                  "timeline-dot " + (s.source === "manual" ? "manual" : "")
                }
              />
              <div className="timeline-time">
                {dateLabel(s.started_at)}
                <span>{s.ended_at ? dateLabel(s.ended_at) : "Ongoing"}</span>
              </div>
              <div className="timeline-description">
                <strong>{s.location}</strong>
                <span>
                  {s.source === "manual"
                    ? "Manual check-in · unverified"
                    : "Authenticated network signal"}{" "}
                  · {s.confidence_status}
                </span>
              </div>
              <span className="timeline-duration">
                {hours(s.duration_seconds / 3600)}
              </span>
            </div>
          ))
        ) : (
          <div className="empty">
            <Clock3 />
            <p>No attendance sessions for this date.</p>
          </div>
        )}
      </div>
    );
  }
  function ReportCards({ limit = 100 }: { limit?: number }) {
    return (
      <div className="reports-list">
        {reports.slice(0, limit).map((r) => (
          <button
            className="report-row"
            key={r.id}
            onClick={() => {
              setSelectedReport(r);
              setTranscript(r.edited_transcript);
              setOriginal(r.original_transcript);
              setCategory(r.category);
              setModal("report");
            }}
          >
            <span className="report-icon">
              <FileText size={17} />
            </span>
            <div>
              <div className="report-row-title">
                <strong>{r.doctor_name}</strong>
                <time>{dateLabel(r.created_at)}</time>
              </div>
              <p>{r.edited_transcript}</p>
              <span className="category">{r.category}</span>
              <span className="report-state">
                {r.review_status === "reviewed" ? (
                  <CheckCheck size={12} />
                ) : (
                  <Clock3 size={12} />
                )}{" "}
                {r.review_status === "reviewed"
                  ? "Reviewed"
                  : "Awaiting review"}
              </span>
            </div>
            <ChevronRight size={15} />
          </button>
        ))}
        {!reports.length && (
          <div className="empty">
            <FileText />
            <p>No activity reports yet.</p>
          </div>
        )}
      </div>
    );
  }
  return (
    <div className="app-shell">
      {mobile && (
        <div className="sidebar-scrim" onClick={() => setMobile(false)} />
      )}
      <aside className={"sidebar " + (mobile ? "sidebar-open" : "")}>
        <a className="brand" href="/" aria-label="Medflow home">
          <span className="brand-mark">
            <Activity size={25} />
          </span>
          <span>
            medflow<span className="brand-period">.</span>
          </span>
        </a>
        <button className="organization" onClick={() => setModal("workspace")}>
          <span className="org-icon">
            <Building2 size={18} />
          </span>
          <span>
            <strong>St. Catherine Medical</strong>
            <small>Hospital workspace</small>
          </span>
          <ChevronDown size={14} />
        </button>
        <div className="nav-label">WORKSPACE</div>
        <nav>
          {navs
            .filter(
              (n) =>
                admin || !["Doctors", "Locations & networks"].includes(n.name),
            )
            .map((n) => (
              <button
                key={n.name}
                className={"nav-item " + (page === n.name ? "active" : "")}
                onClick={() => nav(n.name)}
              >
                <n.icon size={18} />
                <span>
                  {!admin && n.name === "Attendance" ? "My attendance" : n.name}
                </span>
                {n.name === "Activity reports" &&
                  admin &&
                  data.metrics.pending > 0 && <b>{data.metrics.pending}</b>}
              </button>
            ))}
        </nav>
        <div className="sidebar-bottom">
          <button className="nav-item" onClick={() => nav("Settings")}>
            <Settings size={18} />
            <span>Settings</span>
          </button>
          <button className="nav-item" onClick={() => setModal("help")}>
            <HelpCircle size={18} />
            <span>Help & resources</span>
            <ArrowUpRight size={14} />
          </button>
          <div className="system-status">
            <span className="live-dot" />
            <span>All systems operational</span>
            <button
              aria-label="View integration status"
              onClick={() => nav("Locations & networks")}
            >
              <ArrowUpRight size={13} />
            </button>
          </div>
          <button className="account" onClick={() => nav("Settings")}>
            <Avatar
              doctor={{ full_name: data.user.full_name, color: "#dce5e5" }}
            />
            <span>
              <strong>{data.user.full_name}</strong>
              <small>
                {admin ? "Workspace administrator" : data.user.department}
              </small>
            </span>
            <ChevronDown size={14} />
          </button>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="mobile-menu"
              onClick={() => setMobile(true)}
              aria-label="Open navigation"
            >
              <Menu size={22} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={13} />
            <strong>{selected ? "Doctor profile" : page}</strong>
          </div>
          <div className="topbar-actions">
            <div className="global-search">
              <Search size={16} />
              <input
                ref={searchRef}
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  if (page === "Overview" && e.target.value)
                    setPage(admin ? "Doctors" : "Activity reports");
                }}
                placeholder={
                  admin ? "Search your workspace…" : "Search my reports…"
                }
                aria-label="Search workspace"
              />
              <kbd>⌘ K</kbd>
            </div>
            <span className="topbar-divider" />
            <button
              className="notification-btn"
              onClick={() => setNotifications(!notifications)}
              aria-label="Notifications"
            >
              <Bell size={19} />
              <i />
            </button>
            <Avatar small doctor={{ full_name: data.user.full_name }} />
          </div>
          {notifications && (
            <div className="notification-panel">
              <strong>Workspace notifications</strong>
              <p>{data.metrics.pending} activity reports awaiting review.</p>
              <p>
                {data.metrics.exceptions} attendance corrections need attention.
              </p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  nav(admin ? "Attendance" : "Activity reports");
                  setNotifications(false);
                }}
              >
                View updates <ArrowRight size={14} />
              </Button>
            </div>
          )}
        </header>
        <main>
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                {admin ? "HOSPITAL WORKFORCE" : "YOUR WORKSPACE"}
              </div>
              <h1>
                {selected && (
                  <button
                    className="back"
                    onClick={() => setSelected(null)}
                    aria-label="Back to doctors"
                  >
                    <ChevronLeft size={24} />
                  </button>
                )}
                {title}
                <span className="heading-dot" />
              </h1>
              <p>
                {selected
                  ? `${selected.department} · ${selected.email}`
                  : page === "Overview"
                    ? admin
                      ? "A clear picture of your people, presence, and daily activity."
                      : "Your presence, your time, and the work that matters."
                    : "Everything you need, securely in one place."}
              </p>
            </div>
            <div className="heading-actions">
              <span className="date-label">
                <CalendarDays size={15} />
                {today}
              </span>
              <Button
                variant="outline"
                onClick={() => exportReport()}
                disabled={busy}
              >
                <ArrowDownToLine size={15} />
                Export report
              </Button>
            </div>
          </div>
          {error && (
            <div className="error-banner">
              <TriangleAlert size={17} />
              {error}
              <button onClick={refresh}>Retry</button>
            </div>
          )}
          {data.mode === "sandbox" && (
            <div className="sandbox-line">
              <span>
                <span className="sandbox-dot" />
                Integration sandbox{" "}
                <span className="sandbox-detail">
                  · Sample hospital data, isolated to your account
                </span>
              </span>
              <button onClick={() => context(admin ? "doctor" : "admin")}>
                {admin ? "Explore doctor view" : "Return to administrator"}
                <ArrowRight size={13} />
              </button>
            </div>
          )}
          {page === "Overview" && !selected && (
            <>
              <div className="stats-grid">
                {(admin
                  ? [
                      {
                        label: "Registered doctors",
                        value: data.metrics.total.toString(),
                        icon: Users,
                        change: "Across 6 departments",
                        tag: "Your team",
                        tone: "blue",
                      },
                      {
                        label: "Currently on site",
                        value: data.metrics.present.toString(),
                        icon: Wifi,
                        change: `${Math.round((data.metrics.present / Math.max(1, data.metrics.total)) * 100)}% of registered doctors`,
                        tag: "Live presence",
                        tone: "green",
                      },
                      {
                        label: "Detected hours today",
                        value: data.metrics.hours.toLocaleString("en-US", {
                          maximumFractionDigits: 1,
                        }),
                        suffix: "hrs",
                        icon: Clock3,
                        change: "From authenticated network events",
                        tag: "Today",
                        tone: "purple",
                      },
                      {
                        label: "Reports awaiting review",
                        value: data.metrics.pending.toString(),
                        icon: FileText,
                        change: `${data.metrics.reports} activity reports submitted`,
                        tag: "Needs attention",
                        tone: "orange",
                      },
                    ]
                  : [
                      {
                        label: "Current location",
                        value: ownDoctor?.location || "No signal",
                        icon: MapPin,
                        change: "Latest authenticated device location",
                        tag: "Live presence",
                        tone: "green",
                      },
                      {
                        label: "Presence status",
                        value: ownDoctor?.status || "Unknown",
                        icon: Wifi,
                        change: "Device detection, not verified work",
                        tag: "Network",
                        tone: "blue",
                      },
                      {
                        label: "Today's total",
                        value: hours(ownDoctor?.hours || 0),
                        icon: Clock3,
                        change: "Detected presence across locations",
                        tag: "Today",
                        tone: "purple",
                      },
                      {
                        label: "Hours this week",
                        value: hours(
                          data.weekly.reduce((a, d) => a + (d.own || 0), 0),
                        ),
                        icon: ChartNoAxesCombined,
                        change: "Your recorded presence this week",
                        tag: "This week",
                        tone: "orange",
                      },
                    ]
                ).map((s) => (
                  <section className="stat-card" key={s.label}>
                    <div className="stat-top">
                      <span>{s.label}</span>
                      <span className={"stat-icon " + s.tone}>
                        <s.icon size={18} />
                      </span>
                    </div>
                    <div
                      className={
                        "stat-value " +
                        (!admin && s.value.length > 15 ? "smaller" : "")
                      }
                    >
                      {s.value}
                      {"suffix" in s && <small>{s.suffix}</small>}
                    </div>
                    <div className="stat-footer">
                      <span className={s.tone === "green" ? "positive" : ""}>
                        {s.tone === "green" && <span className="tiny-dot" />}
                        {s.change}
                      </span>
                    </div>
                  </section>
                ))}
              </div>
              <div className="charts-grid">
                <section className="panel attendance-chart">
                  <div className="panel-heading">
                    <div>
                      <h2>
                        {admin ? "Presence over time" : "My presence over time"}
                      </h2>
                      <p>
                        Detected hours across your{" "}
                        {admin ? "facilities" : "week"}
                      </p>
                    </div>
                    <select
                      className="select compact"
                      value={period}
                      onChange={(e) => {
                        setPeriod(e.target.value);
                        request(
                          "/dashboard?date=" +
                            calendarDate +
                            "&period=" +
                            encodeURIComponent(e.target.value),
                        )
                          .then(setData)
                          .catch((e) => setToast(e.message));
                      }}
                      aria-label="Chart period"
                    >
                      <option>This week</option>
                      <option>Last week</option>
                    </select>
                  </div>
                  <div className="chart-legend">
                    <span>
                      <i style={{ background: colors[0] }} />
                      Main Hospital
                    </span>
                    <span>
                      <i style={{ background: colors[1] }} />
                      Physician Office
                    </span>
                    <span>
                      <i style={{ background: colors[2] }} />
                      North Clinic
                    </span>
                  </div>
                  <div className="bar-chart">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart
                        data={weekly}
                        barSize={26}
                        margin={{ top: 15, left: -18, right: 8, bottom: 0 }}
                      >
                        <CartesianGrid
                          strokeDasharray="3 4"
                          vertical={false}
                          stroke="#e7edef"
                        />
                        <XAxis
                          dataKey="day"
                          axisLine={false}
                          tickLine={false}
                          tick={{ fill: "#849199", fontSize: 11 }}
                          dy={8}
                        />
                        <YAxis
                          axisLine={false}
                          tickLine={false}
                          tick={{ fill: "#849199", fontSize: 10 }}
                          tickFormatter={(v) => `${v}h`}
                        />
                        <Tooltip
                          cursor={{ fill: "#f1f6f5" }}
                          contentStyle={{
                            border: "1px solid #e4eaea",
                            borderRadius: 10,
                            fontSize: 12,
                          }}
                        />
                        {admin ? (
                          <>
                            <Bar
                              isAnimationActive={false}
                              dataKey="main"
                              name="Main Hospital"
                              stackId="a"
                              fill={colors[0]}
                            />
                            <Bar
                              isAnimationActive={false}
                              dataKey="office"
                              name="Physician Office"
                              stackId="a"
                              fill={colors[1]}
                            />
                            <Bar
                              isAnimationActive={false}
                              dataKey="clinic"
                              name="North Clinic"
                              stackId="a"
                              fill={colors[2]}
                              radius={[4, 4, 0, 0]}
                            />
                          </>
                        ) : (
                          <Bar
                            isAnimationActive={false}
                            dataKey="own"
                            name="My presence (hours)"
                            fill={colors[0]}
                            radius={[4, 4, 0, 0]}
                          />
                        )}
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="chart-footer">
                    <span>
                      <ShieldCheck size={13} /> Based on network-detected
                      presence
                    </span>
                    <button onClick={() => nav("Reports & analytics")}>
                      View analytics <ArrowRight size={13} />
                    </button>
                  </div>
                </section>
                <section className="panel facilities-panel">
                  <div className="panel-heading">
                    <div>
                      <h2>
                        {admin ? "Live facility presence" : "Time by location"}
                      </h2>
                      <p>
                        {admin
                          ? "Connected doctors by location"
                          : "Your detected presence today"}
                      </p>
                    </div>
                    <span className="live-label">
                      <i />
                      Live
                    </span>
                  </div>
                  <div className="facilities-list">
                    {data.locations
                      .filter((l) => l.active)
                      .slice(0, 3)
                      .map((l, i) => {
                        const n = admin
                          ? l.count
                          : data.sessions
                              .filter((s) => s.location_id === l.id)
                              .reduce(
                                (a, s) => a + s.duration_seconds / 3600,
                                0,
                              );
                        return (
                          <div className="facility-summary" key={l.id}>
                            <div className="facility-title">
                              <span className={"facility-icon facility-" + i}>
                                <Building2 size={17} />
                              </span>
                              <div>
                                <strong>{l.name}</strong>
                                <small>{l.building}</small>
                              </div>
                              <span className="facility-number">
                                {admin ? n : hours(n)}
                                {admin && <small>doctors</small>}
                              </span>
                            </div>
                            <div className="progress">
                              <span
                                style={{
                                  width: `${Math.max(4, Math.min(100, admin ? (n / l.capacity) * 100 : (n / 8) * 100))}%`,
                                  background: colors[i],
                                }}
                              />
                            </div>
                          </div>
                        );
                      })}
                  </div>
                  <button
                    className="panel-link"
                    onClick={() =>
                      nav(admin ? "Locations & networks" : "Attendance")
                    }
                  >
                    {admin ? "Manage locations" : "View my attendance"}
                    <ArrowRight size={14} />
                  </button>
                </section>
              </div>
              {!admin && (
                <section className="voice-banner">
                  <span className="voice-icon">
                    <Mic size={25} />
                  </span>
                  <div>
                    <h2>A few words about your day.</h2>
                    <p>
                      Record an activity, review your transcript, and keep your
                      work in view.
                    </p>
                  </div>
                  <Button
                    onClick={() => {
                      setSelectedReport(null);
                      setTranscript("");
                      setOriginal("");
                      setAudioBlob(null);
                      setAudioURL("");
                      setModal("record");
                    }}
                  >
                    <Mic size={15} />
                    Record today’s activity
                  </Button>
                </section>
              )}
              <div className="bottom-grid">
                <section className="panel doctors-panel">
                  <div className="panel-heading">
                    <div>
                      <h2>
                        {admin ? "Doctor presence" : "Today’s attendance"}
                      </h2>
                      <p>
                        {admin
                          ? "Your team, at a glance"
                          : "Your journey through the day"}
                      </p>
                    </div>
                    <button
                      className="text-link"
                      onClick={() => nav(admin ? "Doctors" : "Attendance")}
                    >
                      View all
                      <ArrowRight size={14} />
                    </button>
                  </div>
                  {admin ? (
                    <>
                      <div className="table-toolbar">
                        <div className="inline-search">
                          <Search size={15} />
                          <input
                            placeholder="Search doctors…"
                            value={search}
                            onChange={(e) => setSearch(e.target.value)}
                            aria-label="Search doctors"
                          />
                        </div>
                        <select
                          className="select compact"
                          value={department}
                          onChange={(e) => setDepartment(e.target.value)}
                          aria-label="Filter department"
                        >
                          <option>All departments</option>
                          {Array.from(
                            new Set(data.doctors.map((d) => d.department)),
                          ).map((d) => (
                            <option key={d}>{d}</option>
                          ))}
                        </select>
                        <button
                          className="icon-button"
                          aria-label="More doctor filters"
                          onClick={() => nav("Doctors")}
                        >
                          <SlidersHorizontal size={16} />
                        </button>
                      </div>
                      <DoctorTable compact />
                    </>
                  ) : (
                    <Timeline sessions={data.sessions} />
                  )}
                  <div className="table-bottom">
                    <span>
                      {admin
                        ? `Showing ${Math.min(6, filtered.length)} of ${filtered.length} doctors`
                        : "All timestamps shown in facility timezone"}
                    </span>
                    <span className="updated">
                      <span className="tiny-dot" />
                      Updated {dateLabel(data.updated_at)}
                    </span>
                  </div>
                </section>
                <section className="panel activity-panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Recent activity</h2>
                      <p>
                        {admin
                          ? "The latest from your team"
                          : "Your daily activity reports"}
                      </p>
                    </div>
                    <span className="small-icon">
                      <Activity size={17} />
                    </span>
                  </div>
                  <ReportCards limit={3} />
                  <button
                    className="panel-link"
                    onClick={() => nav("Activity reports")}
                  >
                    View all activity reports
                    <ArrowRight size={14} />
                  </button>
                </section>
              </div>
              <div className="evidence-note">
                <ShieldCheck size={15} />
                <span>
                  Presence tells part of the story. A connected device indicates
                  network presence, not verified clinical work.
                </span>
                <button onClick={() => setModal("privacy")}>
                  How tracking works
                  <ArrowUpRight size={12} />
                </button>
              </div>
            </>
          )}
          {page === "Doctors" && !selected && (
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>
                    Doctor directory{" "}
                    <span className="count-pill">{data.doctors.length}</span>
                  </h2>
                  <p>
                    Manage your hospital’s workforce and view individual
                    records.
                  </p>
                </div>
                <Button onClick={() => setModal("doctor")}>
                  <Plus size={16} />
                  Add doctor
                </Button>
              </div>
              <div className="table-toolbar">
                <div className="inline-search">
                  <Search size={16} />
                  <input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search name, email, or department…"
                    aria-label="Search doctors"
                  />
                </div>
                <select
                  className="select"
                  value={department}
                  onChange={(e) => setDepartment(e.target.value)}
                >
                  <option>All departments</option>
                  {Array.from(
                    new Set(data.doctors.map((d) => d.department)),
                  ).map((d) => (
                    <option key={d}>{d}</option>
                  ))}
                </select>
                <select
                  className="select"
                  value={facility}
                  onChange={(e) => setFacility(e.target.value)}
                >
                  <option>All locations</option>
                  {data.locations.map((l) => (
                    <option key={l.id}>{l.name}</option>
                  ))}
                </select>
              </div>
              <DoctorTable />
              <div className="table-bottom">
                {filtered.length} doctors · Access limited to your organization
              </div>
            </section>
          )}
          {selected && (
            <>
              <div className="profile-hero panel">
                <Avatar doctor={selected} />
                <div>
                  <h2>{selected.full_name}</h2>
                  <p>
                    {selected.department} · {selected.email}
                  </p>
                </div>
                <Badge status={selected.status} />
                {admin && (
                  <Button
                    variant="outline"
                    onClick={() =>
                      mutate(
                        "/users/" + selected.id,
                        {
                          status:
                            selected.status === "Disabled"
                              ? "active"
                              : "disabled",
                        },
                        "Account status updated",
                        "PATCH",
                      )
                    }
                  >
                    {selected.status === "Disabled"
                      ? "Enable account"
                      : "Disable account"}
                  </Button>
                )}
              </div>
              <div className="detail-grid">
                <section className="panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Attendance timeline</h2>
                      <p>Original network evidence retained separately</p>
                    </div>
                  </div>
                  <Timeline
                    sessions={data.sessions.filter(
                      (s) => s.doctor_id === selected.id,
                    )}
                  />
                </section>
                <section className="panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Activity reports</h2>
                      <p>Operational activities reported by this doctor</p>
                    </div>
                  </div>
                  <div className="reports-list">
                    {data.reports
                      .filter((r) => r.doctor_id === selected.id)
                      .map((r) => (
                        <button
                          key={r.id}
                          className="report-row"
                          onClick={() => {
                            setSelectedReport(r);
                            setTranscript(r.edited_transcript);
                            setCategory(r.category);
                            setModal("report");
                          }}
                        >
                          <FileText size={18} />
                          <div>
                            <strong>{r.category}</strong>
                            <p>{r.edited_transcript}</p>
                            <small>
                              {dateLabel(r.created_at, {
                                month: "short",
                                day: "numeric",
                                hour: "numeric",
                                minute: "numeric",
                              })}
                            </small>
                          </div>
                          <ChevronRight size={16} />
                        </button>
                      ))}
                  </div>
                </section>
              </div>
            </>
          )}
          {page === "Attendance" && (
            <>
              <div className="attendance-controls">
                <div className="segmented">
                  <span className="active">Daily timeline</span>
                  <button onClick={() => nav("Reports & analytics")}>
                    Attendance analytics
                  </button>
                </div>
                <input
                  type="date"
                  className="select"
                  value={calendarDate}
                  onChange={(e) => {
                    setCalendarDate(e.target.value);
                    request("/dashboard?date=" + e.target.value)
                      .then(setData)
                      .catch((e) => setToast(e.message));
                  }}
                />
                {!admin && (
                  <>
                    <Button
                      variant="outline"
                      onClick={() => setModal("correction")}
                    >
                      Request correction
                    </Button>
                    <Button onClick={() => setModal("checkin")}>
                      <MapPin size={15} />
                      Manual check-in
                    </Button>
                  </>
                )}
              </div>
              <section className="panel">
                <div className="panel-heading">
                  <div>
                    <h2>
                      {admin
                        ? "Staff attendance timeline"
                        : "My attendance timeline"}
                    </h2>
                    <p>
                      Facility time · overlapping device sessions are counted
                      once
                    </p>
                  </div>
                  <span className="legend-badge">
                    <i />
                    Detected presence
                  </span>
                </div>
                {admin ? (
                  <div className="attendance-doctor-list">
                    {data.doctors.slice(0, 12).map((d) => (
                      <div className="attendance-doctor" key={d.id}>
                        <div className="person">
                          <Avatar small doctor={d} />
                          <strong>{d.full_name}</strong>
                        </div>
                        <div className="visual-track">
                          {data.sessions
                            .filter((s) => s.doctor_id === d.id)
                            .map((s) => (
                              <span
                                key={s.id}
                                title={`${s.location}: ${dateLabel(s.started_at)} – ${dateLabel(s.ended_at)}`}
                                style={{
                                  left: `${Math.max(0, ((new Date(s.started_at).getUTCHours() + new Date(s.started_at).getUTCMinutes() / 60 - 10) / 14) * 100)}%`,
                                  width: `${Math.max(1, (s.duration_seconds / 3600 / 14) * 100)}%`,
                                  background:
                                    colors[
                                      data.locations.findIndex(
                                        (l) => l.id === s.location_id,
                                      ) % 3
                                    ],
                                }}
                              />
                            ))}
                        </div>
                        <span>{hours(d.hours)}</span>
                      </div>
                    ))}
                    <div className="track-axis">
                      <span>6 AM</span>
                      <span>9 AM</span>
                      <span>12 PM</span>
                      <span>3 PM</span>
                      <span>6 PM</span>
                      <span>8 PM</span>
                    </div>
                  </div>
                ) : (
                  <Timeline sessions={data.sessions} />
                )}
              </section>
              <section className="panel corrections-panel">
                <div className="panel-heading">
                  <div>
                    <h2>Attendance corrections</h2>
                    <p>
                      {admin
                        ? "Review requested changes with a full audit trail."
                        : "Request a correction when the network evidence is incomplete."}
                    </p>
                  </div>
                </div>
                {data.corrections.length ? (
                  data.corrections.map((c) => (
                    <div className="correction-row" key={c.id}>
                      <span className="report-icon">
                        <TriangleAlert size={17} />
                      </span>
                      <div>
                        <strong>{c.doctor_name}</strong>
                        <p>{c.reason}</p>
                        <small>{JSON.stringify(c.requested_changes)}</small>
                      </div>
                      <Badge status={c.approval_status} />
                      {admin && c.approval_status === "pending" && (
                        <>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() =>
                              mutate(
                                "/corrections/" + c.id + "/review",
                                { decision: "rejected" },
                                "Correction rejected",
                              )
                            }
                          >
                            Reject
                          </Button>
                          <Button
                            size="sm"
                            onClick={() =>
                              mutate(
                                "/corrections/" + c.id + "/review",
                                { decision: "approved" },
                                "Correction approved and attendance updated",
                              )
                            }
                          >
                            <Check size={14} />
                            Approve
                          </Button>
                        </>
                      )}
                    </div>
                  ))
                ) : (
                  <div className="empty">
                    <CheckCircle2 />
                    <h3>All caught up</h3>
                    <p>No attendance corrections to review.</p>
                  </div>
                )}
              </section>
            </>
          )}
          {page === "Activity reports" && (
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>
                    {admin ? "Team activity reports" : "My activity reports"}
                  </h2>
                  <p>Reviewed, editable accounts of daily operational work.</p>
                </div>
                {!admin && (
                  <Button
                    onClick={() => {
                      setSelectedReport(null);
                      setTranscript("");
                      setOriginal("");
                      setAudioURL("");
                      setAudioBlob(null);
                      setModal("record");
                    }}
                  >
                    <Mic size={16} />
                    Record activity
                  </Button>
                )}
              </div>
              <div className="table-toolbar">
                <div className="inline-search">
                  <Search size={16} />
                  <input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search transcripts, categories, or doctors…"
                    aria-label="Search activity reports"
                  />
                </div>
                <span className="muted">{reports.length} reports</span>
              </div>
              <ReportCards />
            </section>
          )}
          {page === "Locations & networks" && admin && (
            <>
              <div className="section-actions">
                <div>
                  <h2>Connected facilities</h2>
                  <p className="muted">
                    Authenticated network identities mapped to physical
                    locations.
                  </p>
                </div>
                <Button onClick={() => setModal("location")}>
                  <Plus size={16} />
                  Add location
                </Button>
              </div>
              <div className="locations-grid">
                {data.locations.map((l, i) => (
                  <section className="panel location-card" key={l.id}>
                    <div className="location-card-top">
                      <span className={"facility-icon facility-" + (i % 3)}>
                        <Building2 size={22} />
                      </span>
                      <Badge status={l.active ? "Present" : "Disabled"} />
                    </div>
                    <h2>{l.name}</h2>
                    <p>{l.building}</p>
                    <div className="location-details">
                      <span>
                        <Wifi size={16} />
                        {l.ssid}
                      </span>
                      <span>
                        <Clock3 size={16} />
                        {l.timezone}
                      </span>
                      <span>
                        <Users size={16} />
                        {l.count} connected doctors
                      </span>
                    </div>
                    <Button
                      variant="outline"
                      onClick={() => {
                        setModal("network:" + l.id);
                      }}
                    >
                      Configure network
                      <ArrowRight size={14} />
                    </Button>
                  </section>
                ))}
              </div>
              <section className="panel integration-panel">
                <div className="panel-heading">
                  <div>
                    <h2>Network integration health</h2>
                    <p>
                      Enterprise identity is required for reliable presence
                      detection.
                    </p>
                  </div>
                  <span className="badge badge-amber">
                    <i />
                    Sandbox provider
                  </span>
                </div>
                <div className="integration-row">
                  <span className="report-icon">
                    <Radio size={22} />
                  </span>
                  <div>
                    <h3>RADIUS accounting adapter</h3>
                    <p>
                      Start, stop, and interim updates · authenticated identity
                      mapping · idempotent event processing
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    onClick={() => setModal("simulator")}
                  >
                    Open event simulator
                    <ArrowUpRight size={14} />
                  </Button>
                </div>
                <div className="info-note">
                  <ShieldCheck size={16} />
                  Live hardware is not connected. The simulator writes clearly
                  identified sample network events.
                </div>
              </section>
            </>
          )}
          {page === "Reports & analytics" && (
            <>
              <div className="attendance-controls">
                <input
                  className="select"
                  type="date"
                  value={calendarDate}
                  onChange={(e) => setCalendarDate(e.target.value)}
                />
                <select
                  className="select"
                  value={facility}
                  onChange={(e) => setFacility(e.target.value)}
                >
                  <option>All locations</option>
                  {data.locations.map((l) => (
                    <option key={l.id}>{l.name}</option>
                  ))}
                </select>
                <Button variant="outline" onClick={() => exportReport()}>
                  CSV export
                  <Download size={15} />
                </Button>
                <Button variant="outline" onClick={() => exportReport("pdf")}>
                  PDF export
                  <Download size={15} />
                </Button>
              </div>
              <div className="detail-grid">
                <section className="panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Presence trend</h2>
                      <p>Weekly detected hours by facility</p>
                    </div>
                  </div>
                  <div className="analytics-chart">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart
                        data={data.weekly}
                        margin={{ left: 0, right: 25, top: 15 }}
                      >
                        <CartesianGrid strokeDasharray="3 3" vertical={false} />
                        <XAxis
                          dataKey="day"
                          axisLine={false}
                          tickLine={false}
                        />
                        <YAxis axisLine={false} tickLine={false} />
                        <Tooltip />
                        {(admin ? ["main", "office", "clinic"] : ["own"]).map(
                          (k, i) => (
                            <Area
                              isAnimationActive={false}
                              key={k}
                              type="monotone"
                              dataKey={k}
                              stackId="1"
                              stroke={colors[i]}
                              fill={colors[i]}
                              fillOpacity={0.15}
                            />
                          ),
                        )}
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </section>
                <section className="panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Location distribution</h2>
                      <p>Today’s detected presence hours</p>
                    </div>
                  </div>
                  <div className="donut-chart">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          isAnimationActive={false}
                          data={data.locations.map((l) => ({
                            name: l.name,
                            value:
                              Math.round(
                                data.sessions
                                  .filter((s) => s.location_id === l.id)
                                  .reduce(
                                    (a, s) => a + s.duration_seconds / 3600,
                                    0,
                                  ) * 10,
                              ) / 10,
                          }))}
                          dataKey="value"
                          innerRadius={68}
                          outerRadius={95}
                          paddingAngle={4}
                          stroke="none"
                        >
                          {data.locations.map((l, i) => (
                            <Cell key={l.id} fill={colors[i % 4]} />
                          ))}
                        </Pie>
                        <Tooltip />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="chart-legend centered">
                    {data.locations.slice(0, 3).map((l, i) => (
                      <span key={l.id}>
                        <i style={{ background: colors[i] }} />
                        {l.name}
                      </span>
                    ))}
                  </div>
                </section>
              </div>
              <section className="panel">
                <div className="panel-heading">
                  <div>
                    <h2>Attendance records</h2>
                    <p>
                      Authorized exports include timezone, evidence source, and
                      confidence.
                    </p>
                  </div>
                </div>
                {admin ? (
                  <DoctorTable />
                ) : (
                  <Timeline sessions={data.sessions} />
                )}
              </section>
            </>
          )}
          {page === "Settings" && (
            <div className="settings-grid">
              <section className="panel settings-section">
                <h2>Profile & account</h2>
                <p>
                  Your identity and access are managed securely by your
                  organization.
                </p>
                <div className="profile-line">
                  <Avatar doctor={{ full_name: data.user.full_name }} />
                  <div>
                    <strong>{data.user.full_name}</strong>
                    <span>{data.user.email}</span>
                  </div>
                  <Badge status={admin ? "Administrator" : "Doctor"} />
                </div>
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    const f = new FormData(e.currentTarget);
                    mutate(
                      "/profile",
                      {
                        full_name: f.get("full_name"),
                        notifications: f.get("notifications") === "on",
                      },
                      "Profile preferences saved",
                      "PATCH",
                    );
                  }}
                >
                  <label>
                    Display name
                    <input
                      name="full_name"
                      defaultValue={data.user.full_name}
                      required
                      maxLength={100}
                    />
                  </label>
                  <label className="checkbox-label">
                    <input
                      name="notifications"
                      type="checkbox"
                      defaultChecked={data.settings.notifications !== false}
                    />
                    Email me attendance exceptions and report updates
                  </label>
                  <Button disabled={busy}>Save preferences</Button>
                </form>
                <a
                  className="signout"
                  href={
                    data.mode === "sandbox"
                      ? "/signout-with-chatgpt?return_to=/"
                      : "/api/auth/logout"
                  }
                  onClick={
                    data.mode !== "sandbox"
                      ? (e) => {
                          e.preventDefault();
                          fetch("/api/auth/logout", {
                            method: "POST",
                            credentials: "include",
                          }).then(() => location.assign("/api/auth/login"));
                        }
                      : undefined
                  }
                  target="_top"
                >
                  <LogOut size={16} />
                  Sign out securely
                </a>
              </section>
              <section className="panel settings-section">
                <h2>Privacy & data handling</h2>
                <p>
                  Operational attendance stays separate from patient records.
                </p>
                <div className="privacy-item">
                  <ShieldCheck />
                  <div>
                    <strong>Minimum necessary information</strong>
                    <p>
                      Keep patient names, identifiers, and clinical details out
                      of daily activity reports.
                    </p>
                  </div>
                </div>
                <div className="privacy-item">
                  <Mic />
                  <div>
                    <strong>Audio retention is off</strong>
                    <p>
                      Sandbox recordings stay in your browser for playback. No
                      audio is sent to an unapproved provider.
                    </p>
                  </div>
                </div>
                <div className="privacy-item">
                  <Laptop />
                  <div>
                    <strong>Enrolled network identities</strong>
                    <p>
                      Device enrollment uses enterprise identity. MAC addresses
                      alone never prove identity.
                    </p>
                  </div>
                </div>
                <Button variant="outline" onClick={() => setModal("privacy")}>
                  View monitoring notice
                  <ExternalLink size={14} />
                </Button>
              </section>
              {admin && (
                <section className="panel audit-panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Security & administrative audit</h2>
                      <p>Organization-scoped access and mutation history</p>
                    </div>
                    <ShieldCheck size={20} />
                  </div>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Timestamp</th>
                          <th>Action</th>
                          <th>Resource</th>
                          <th>Outcome</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.audit.map((a) => (
                          <tr key={a.id}>
                            <td>
                              {dateLabel(a.timestamp, {
                                month: "short",
                                day: "numeric",
                                hour: "numeric",
                                minute: "numeric",
                              })}
                            </td>
                            <td>{a.action}</td>
                            <td>{a.resource_type}</td>
                            <td>
                              <Badge status={a.outcome} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}
            </div>
          )}
          <footer className="workspace-footer">
            <span>© {new Date().getFullYear()} Medflow</span>
            <span>
              Thoughtfully connected. Secure by design.
              <ShieldCheck size={12} />
            </span>
          </footer>
        </main>
      </div>
      <Dialog
        open={!!modal}
        onOpenChange={(open) => {
          if (!open) {
            if (recording) recorder.current?.stop();
            setModal("");
          }
        }}
        title={
          modal === "record"
            ? "Record your daily activity"
            : modal === "report"
              ? "Activity report"
              : modal === "doctor"
                ? "Add a doctor"
                : modal === "location"
                  ? "Add a location"
                  : modal === "correction"
                    ? "Request an attendance correction"
                    : modal === "checkin"
                      ? "Manual check-in"
                      : modal === "simulator"
                        ? "Network event simulator"
                        : modal.startsWith("network:")
                          ? "Network configuration"
                          : modal === "workspace"
                            ? "St. Catherine Medical"
                            : modal === "help"
                              ? "Your Medflow workspace"
                              : "Presence & privacy"
        }
        description={
          ["record", "report"].includes(modal)
            ? "Operational activity only. Please exclude patient names and identifying information."
            : undefined
        }
      >
        {["record", "report"].includes(modal) && (
          <>
            {modal === "record" && (
              <div className="recorder">
                <div
                  className={
                    "mic-orb " + (recording && !paused ? "recording" : "")
                  }
                >
                  <Mic size={30} />
                </div>
                <strong>
                  {recording
                    ? paused
                      ? "Recording paused"
                      : "Listening…"
                    : audioURL
                      ? "Your recording is ready"
                      : "A few words about your day"}
                </strong>
                <span>
                  {recording
                    ? `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`
                    : "Record, review, and save your activity."}
                </span>
                <div className="recorder-actions">
                  {!recording ? (
                    <Button onClick={startRecording}>
                      <Mic size={16} />
                      {audioURL ? "Record again" : "Start recording"}
                    </Button>
                  ) : (
                    <>
                      <Button
                        variant="outline"
                        onClick={() => {
                          if (paused) recorder.current?.resume();
                          else recorder.current?.pause();
                          setPaused(!paused);
                        }}
                      >
                        {paused ? <Play size={15} /> : <Pause size={15} />}{" "}
                        {paused ? "Resume" : "Pause"}
                      </Button>
                      <Button onClick={() => recorder.current?.stop()}>
                        <Square size={14} />
                        Finish recording
                      </Button>
                    </>
                  )}
                </div>
                {audioURL && (
                  <>
                    <audio controls src={audioURL} />
                    <Button
                      variant="outline"
                      onClick={transcribe}
                      disabled={busy}
                    >
                      {busy ? (
                        <Loader2 className="spin" size={15} />
                      ) : (
                        <Volume2 size={15} />
                      )}
                      Transcribe recording
                    </Button>
                  </>
                )}
                {recordError && <p className="record-error">{recordError}</p>}
              </div>
            )}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (!transcript.trim()) return;
                mutate(
                  selectedReport ? "/reports/" + selectedReport.id : "/reports",
                  {
                    original_transcript: original || transcript,
                    edited_transcript: transcript,
                    category,
                    location_id: ownDoctor?.location_id || null,
                  },
                  selectedReport
                    ? "Report updated"
                    : "Your activity report has been saved",
                  selectedReport ? "PATCH" : "POST",
                );
              }}
            >
              <label>
                {modal === "record"
                  ? "Your activity · type or review your transcript"
                  : "Reviewed transcript"}
                <textarea
                  required
                  rows={5}
                  placeholder="Describe your operational activities, meetings, or administrative work…"
                  value={transcript}
                  onChange={(e) => setTranscript(e.target.value)}
                  readOnly={admin && modal === "report"}
                />
              </label>
              <label>
                Activity category
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  disabled={admin && modal === "report"}
                >
                  {[
                    "Patient Care",
                    "Consultations",
                    "Administrative Duties",
                    "Surgery / Procedures",
                    "Meetings",
                    "Research",
                    "Teaching",
                    "Other",
                  ].map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </select>
              </label>
              {selectedReport && (
                <>
                  <small className="muted">
                    Reported by {selectedReport.doctor_name} ·{" "}
                    {dateLabel(selectedReport.created_at, {
                      month: "long",
                      day: "numeric",
                      hour: "numeric",
                      minute: "numeric",
                    })}
                  </small>
                  <details>
                    <summary>Original transcript</summary>
                    <p className="original-text">
                      {selectedReport.original_transcript}
                    </p>
                  </details>
                  {!admin && (
                    <div className="summary-section">
                      <Button
                        type="button"
                        variant="outline"
                        disabled={busy}
                        onClick={async () => {
                          setBusy(true);
                          try {
                            const summary = await request(
                              "/reports/" + selectedReport.id + "/summary",
                              "POST",
                              {},
                            );
                            setSelectedReport({ ...selectedReport, summary });
                            setToast(
                              "AI categories generated from exact transcript excerpts. Review before use.",
                            );
                          } catch (e) {
                            setToast((e as Error).message);
                          } finally {
                            setBusy(false);
                          }
                        }}
                      >
                        <Activity size={14} />
                        Organize with AI
                      </Button>
                      <small className="muted">
                        Approved provider required · source-linked excerpts only
                      </small>
                    </div>
                  )}
                  {selectedReport.summary && (
                    <div className="summary-editor">
                      <h3>AI-generated activity categories</h3>
                      <p className="muted">
                        Review these source excerpts. Your changes are labeled
                        doctor-edited.
                      </p>
                      {selectedReport.summary.items.map((item, i) => (
                        <label key={i}>
                          {item.category}
                          <textarea
                            rows={2}
                            value={item.text}
                            onChange={(e) => {
                              const items = [...selectedReport.summary!.items];
                              items[i] = { ...item, text: e.target.value };
                              setSelectedReport({
                                ...selectedReport,
                                summary: { ...selectedReport.summary!, items },
                              });
                            }}
                            readOnly={admin}
                          />
                        </label>
                      ))}
                      {!admin && (
                        <Button
                          type="button"
                          variant="outline"
                          onClick={() =>
                            mutate(
                              "/reports/" + selectedReport.id + "/summary",
                              { items: selectedReport.summary!.items },
                              "Summary reviewed and saved",
                              "PATCH",
                            )
                          }
                        >
                          Save reviewed summary
                        </Button>
                      )}
                    </div>
                  )}
                </>
              )}
              <div className="modal-actions">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setModal("")}
                >
                  Close
                </Button>
                {admin && selectedReport ? (
                  <Button
                    type="button"
                    disabled={
                      busy || selectedReport.review_status === "reviewed"
                    }
                    onClick={() =>
                      mutate(
                        "/reports/" + selectedReport.id + "/review",
                        {},
                        "Report marked as reviewed",
                      )
                    }
                  >
                    <CheckCheck size={16} />
                    Mark reviewed
                  </Button>
                ) : (
                  <Button disabled={busy || recording || !transcript.trim()}>
                    {busy ? (
                      <Loader2 className="spin" size={15} />
                    ) : (
                      <Check size={15} />
                    )}
                    Save activity
                  </Button>
                )}
              </div>
            </form>
          </>
        )}
        {modal === "doctor" && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              mutate(
                "/users",
                Object.fromEntries(f),
                "Doctor account created. Enroll their enterprise identity before tracking.",
              );
            }}
          >
            <label>
              Full name
              <input
                name="full_name"
                placeholder="Dr. Jane Smith"
                required
                maxLength={100}
              />
            </label>
            <label>
              Work email
              <input
                name="email"
                type="email"
                placeholder="jane.smith@hospital.org"
                required
              />
            </label>
            <label>
              Department
              <select name="department">
                {[
                  "Cardiology",
                  "Neurology",
                  "Surgery",
                  "Pediatrics",
                  "Internal Medicine",
                  "Radiology",
                ].map((d) => (
                  <option key={d}>{d}</option>
                ))}
              </select>
            </label>
            <label>
              OIDC subject / enterprise identity
              <input
                name="identity_reference"
                placeholder="Unique identity from approved provider"
                required
                maxLength={200}
              />
            </label>
            <div className="info-note">
              <ShieldCheck size={16} />
              An account does not imply WiFi presence. Device enrollment is a
              separate, verified step.
            </div>
            <div className="modal-actions">
              <Button disabled={busy}>
                Create doctor account
                <Plus size={15} />
              </Button>
            </div>
          </form>
        )}
        {modal === "location" && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              mutate(
                "/locations",
                Object.fromEntries(new FormData(e.currentTarget)),
                "Location added",
              );
            }}
          >
            <label>
              Location name
              <input
                name="name"
                required
                placeholder="West Wing"
                maxLength={100}
              />
            </label>
            <label>
              Building
              <input
                name="building"
                required
                placeholder="Building D · Floors 1–3"
              />
            </label>
            <label>
              Facility timezone
              <input name="timezone" defaultValue="America/New_York" required />
            </label>
            <label>
              WiFi network SSID
              <input name="ssid" required placeholder="Hospital_West" />
            </label>
            <div className="modal-actions">
              <Button disabled={busy}>Add location</Button>
            </div>
          </form>
        )}
        {modal.startsWith("network:") &&
          (() => {
            const l = data.locations.find((l) => l.id === modal.split(":")[1]);
            return (
              l && (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    mutate(
                      "/locations/" + l.id,
                      Object.fromEntries(new FormData(e.currentTarget)),
                      "Network mapping updated",
                      "PATCH",
                    );
                  }}
                >
                  <label>
                    Location name
                    <input name="name" defaultValue={l.name} required />
                  </label>
                  <label>
                    SSID
                    <input name="ssid" defaultValue={l.ssid} required />
                  </label>
                  <label>
                    Timezone
                    <input name="timezone" defaultValue={l.timezone} required />
                  </label>
                  <label>
                    Network state
                    <select name="active" defaultValue={String(l.active)}>
                      <option value="true">Active</option>
                      <option value="false">Disabled</option>
                    </select>
                  </label>
                  <div className="info-note">
                    <Wifi size={17} />
                    Production adapters accept signed events from approved
                    controllers. An SSID alone never identifies a doctor.
                  </div>
                  <div className="modal-actions">
                    <Button disabled={busy}>Save configuration</Button>
                  </div>
                </form>
              )
            );
          })()}
        {modal === "correction" && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              mutate(
                "/corrections",
                {
                  session_id: f.get("session_id") || null,
                  reason: f.get("reason"),
                  requested_changes: {
                    started_at: new Date(
                      f.get("started_at") as string,
                    ).toISOString(),
                    ended_at: new Date(
                      f.get("ended_at") as string,
                    ).toISOString(),
                    location_id: f.get("location_id"),
                  },
                },
                "Correction submitted for administrator review",
              );
            }}
          >
            <label>
              Attendance session
              <select name="session_id">
                <option value="">Missing session</option>
                {data.sessions.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.location} · {dateLabel(s.started_at)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Facility
              <select name="location_id">
                {data.locations.map((l) => (
                  <option value={l.id} key={l.id}>
                    {l.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="form-grid">
              <label>
                Arrival (your local time)
                <input name="started_at" type="datetime-local" required />
              </label>
              <label>
                Departure (your local time)
                <input name="ended_at" type="datetime-local" required />
              </label>
            </div>
            <label>
              Reason
              <textarea
                name="reason"
                required
                minLength={10}
                rows={3}
                placeholder="Explain the missing or incorrect network event…"
              />
            </label>
            <div className="modal-actions">
              <Button disabled={busy}>Submit for review</Button>
            </div>
          </form>
        )}
        {modal === "checkin" && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              mutate(
                "/checkin",
                Object.fromEntries(new FormData(e.currentTarget)),
                "Manual presence recorded as unverified",
              );
            }}
          >
            <div className="info-note">
              <MapPin size={17} />
              Manual check-ins are labeled unverified and do not become
              network-confirmed presence.
            </div>
            <label>
              Facility
              <select name="location_id">
                {data.locations.map((l) => (
                  <option value={l.id} key={l.id}>
                    {l.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Action
              <select name="action">
                <option value="start">Check in</option>
                <option value="stop">Check out</option>
              </select>
            </label>
            <label>
              Note
              <input
                name="reason"
                required
                minLength={5}
                placeholder="Why is manual check-in needed?"
              />
            </label>
            <div className="modal-actions">
              <Button disabled={busy}>Confirm manual entry</Button>
            </div>
          </form>
        )}
        {modal === "simulator" && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              mutate(
                "/sandbox/events",
                Object.fromEntries(new FormData(e.currentTarget)),
                "Simulated network event processed",
              );
            }}
          >
            <div className="info-note">
              <Radio size={17} />
              Development only. Events remain in this sandbox and are labeled
              simulated.
            </div>
            <label>
              Enrolled doctor
              <select name="doctor_id">
                {data.doctors.map((d) => (
                  <option value={d.id} key={d.id}>
                    {d.full_name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Approved facility
              <select name="location_id">
                {data.locations
                  .filter((l) => l.active)
                  .map((l) => (
                    <option value={l.id} key={l.id}>
                      {l.name}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              RADIUS event
              <select name="event_type">
                <option value="start">Accounting Start</option>
                <option value="interim">Interim Update</option>
                <option value="stop">Accounting Stop</option>
              </select>
            </label>
            <div className="modal-actions">
              <Button disabled={busy}>
                <Radio size={16} />
                Send test event
              </Button>
            </div>
          </form>
        )}
        {["help", "privacy", "workspace"].includes(modal) && (
          <div className="help-content">
            <div className="privacy-item">
              <Wifi />
              <div>
                <h3>Presence from trusted network evidence</h3>
                <p>
                  Authenticated enterprise WiFi events determine when enrolled
                  devices are detected. Grace periods handle brief dropouts.
                  Device presence does not verify that a person performed work.
                </p>
              </div>
            </div>
            <div className="privacy-item">
              <ShieldCheck />
              <div>
                <h3>Your data, within your organization</h3>
                <p>
                  Doctors can access their own records. Administrators can
                  review their organization’s attendance, activity, and
                  correction requests. Sensitive access is audited.
                </p>
              </div>
            </div>
            <div className="privacy-item">
              <Mic />
              <div>
                <h3>Keep daily reports operational</h3>
                <p>
                  Do not include patient names or identifiers. Recordings
                  require an approved transcription provider before upload.
                  Audio retention is disabled by default.
                </p>
              </div>
            </div>
            <div className="info-note">
              This private sandbox contains fictional staff. A live rollout
              requires hospital SSO/MFA, device enrollment, signed network
              integrations, and administrative review of monitoring policies and
              applicable health-data obligations.
            </div>
            <div className="modal-actions">
              <Button onClick={() => setModal("")}>
                Got it
                <Check size={15} />
              </Button>
            </div>
          </div>
        )}
      </Dialog>
      {toast && (
        <div role="status" className="toast">
          <CheckCircle2 size={18} />
          {toast}
          <button
            onClick={() => setToast("")}
            aria-label="Dismiss notification"
          >
            <X size={15} />
          </button>
        </div>
      )}
    </div>
  );
}
