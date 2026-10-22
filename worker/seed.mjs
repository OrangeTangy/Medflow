// Fictional data is created only inside the owner-private integration sandbox.
export function seed(owner) {
  const now = new Date(),
    day = new Date(now);
  day.setUTCHours(12, 0, 0, 0);
  const iso = (d) => new Date(d).toISOString();
  const locations = [
    {
      id: "main",
      name: "Main Hospital",
      building: "Building A · Main campus",
      timezone: "America/New_York",
      ssid: "Hospital_Main",
      active: true,
      capacity: 32,
      color: "#188e82",
    },
    {
      id: "office",
      name: "Physician Office",
      building: "Building B · Medical offices",
      timezone: "America/New_York",
      ssid: "Doctors_Office",
      active: true,
      capacity: 18,
      color: "#5689aa",
    },
    {
      id: "clinic",
      name: "North Clinic",
      building: "Building C · North campus",
      timezone: "America/New_York",
      ssid: "Clinic_North",
      active: true,
      capacity: 14,
      color: "#bccdd6",
    },
  ];
  const names = [
    "Jane Smith",
    "John Lee",
    "Emily Chen",
    "Michael Wilson",
    "Sarah Patel",
    "David Kim",
    "Olivia Martin",
    "James Anderson",
    "Sophia Nguyen",
    "Robert Davis",
    "Isabella Garcia",
    "William Brown",
    "Mia Robinson",
    "Benjamin Clark",
    "Charlotte Lewis",
    "Lucas Walker",
    "Amelia Hall",
    "Henry Young",
    "Evelyn Allen",
    "Alexander King",
    "Harper Wright",
    "Daniel Scott",
    "Abigail Green",
    "Matthew Adams",
    "Ella Baker",
    "Joseph Nelson",
    "Scarlett Hill",
    "Samuel Mitchell",
    "Grace Carter",
    "Sebastian Roberts",
    "Chloe Phillips",
    "Jack Evans",
    "Victoria Turner",
    "Owen Parker",
    "Lily Collins",
    "Theodore Morris",
    "Hannah Stewart",
    "Leo Sanchez",
    "Zoey Rivera",
    "Nathan Cooper",
    "Nora Richardson",
    "Isaac Cox",
    "Riley Howard",
    "Gabriel Ward",
    "Aria Torres",
    "Julian Peterson",
    "Layla Gray",
    "Anthony Ramirez",
  ];
  const departments = [
    "Cardiology",
    "Neurology",
    "Surgery",
    "Internal Medicine",
    "Pediatrics",
    "Radiology",
  ];
  const palette = [
    "#e3edeb",
    "#e6e8f4",
    "#f3e9e2",
    "#e7edf5",
    "#efe6f0",
    "#e5eddf",
  ];
  const doctors = names.map((name, i) => ({
    id: "doctor-" + i,
    full_name: "Dr. " + name,
    email: name.toLowerCase().replace(" ", ".") + "@stcatherine.example",
    department: departments[i % 6],
    location: i % 7 === 6 ? null : locations[i % 3].name,
    location_id: i % 7 === 6 ? null : locations[i % 3].id,
    status: i % 7 === 6 ? "Absent" : i % 8 === 5 ? "Last seen" : "Present",
    hours: 0,
    first_arrival: null,
    last_seen: iso(now),
    initials: name
      .split(" ")
      .map((x) => x[0])
      .join(""),
    color: palette[i % 6],
    identity_reference: "sandbox-certificate:" + i,
  }));
  const sessions = [];
  for (let offset = -13; offset <= 0; offset++)
    for (let i = 0; i < doctors.length; i++) {
      const date = new Date(day);
      date.setUTCDate(date.getUTCDate() + offset);
      if (date.getUTCDay() === 0 || date.getUTCDay() === 6) continue;
      if (i % 7 === 6 && offset === 0) continue;
      const start = new Date(date);
      start.setUTCMinutes((i * 13 + offset * 3 + 60) % 55);
      const duration = (5.3 + (i % 7) * 0.37 + (offset % 3) * 0.2) * 3600;
      const end = new Date(+start + duration * 1000);
      const loc = locations[i % 3];
      sessions.push({
        id: `seed-${offset}-${i}`,
        doctor_id: doctors[i].id,
        location_id: loc.id,
        location: loc.name,
        started_at: iso(start),
        ended_at: iso(end),
        duration_seconds: Math.round(duration),
        confidence_status: "simulated",
        source: "simulator",
        session_status: "closed",
      });
    }
  const reports = [
    {
      doctor_id: "doctor-0",
      category: "Patient Care",
      edited_transcript:
        "Completed morning rounds and coordinated afternoon consultations with the cardiology team.",
    },
    {
      doctor_id: "doctor-2",
      category: "Surgery / Procedures",
      edited_transcript:
        "Completed the scheduled procedures and attended the surgical team handover meeting.",
    },
    {
      doctor_id: "doctor-1",
      category: "Consultations",
      edited_transcript:
        "Conducted outpatient consultations at the physician office and reviewed the department schedule.",
    },
    {
      doctor_id: "doctor-4",
      category: "Teaching",
      edited_transcript:
        "Led the afternoon resident teaching session and prepared learning materials for next week.",
    },
    {
      doctor_id: "doctor-5",
      category: "Administrative Duties",
      edited_transcript:
        "Reviewed the departmental workflow and completed the weekly administrative report.",
    },
    {
      doctor_id: "doctor-0",
      category: "Meetings",
      edited_transcript:
        "Attended the department planning meeting and helped coordinate next month’s rotation.",
    },
  ].map((r, i) => ({
    ...r,
    id: "report-" + i,
    original_transcript: r.edited_transcript,
    location_id: doctors.find((d) => d.id === r.doctor_id).location_id,
    created_at: iso(+now - (i * 23 + 8) * 60000),
    updated_at: iso(now),
    review_status: i < 4 ? "pending" : "reviewed",
    tags: [],
  }));
  return {
    owner,
    organization_id: owner,
    admin: {
      id: "admin",
      full_name: "Alex Morgan",
      email: "alex.morgan@stcatherine.example",
      department: "Administration",
    },
    doctors,
    locations,
    sessions,
    reports,
    corrections: [
      {
        id: "correction-0",
        doctor_id: "doctor-2",
        reason:
          "My WiFi connection ended early during a scheduled department meeting. Please correct the departure time.",
        requested_changes: {
          started_at: iso(day),
          ended_at: iso(+day + 8 * 3600000),
          location_id: "clinic",
        },
        approval_status: "pending",
        created_at: iso(now),
      },
    ],
    events: [],
    audit: [],
    settings: { notifications: true, doctor_exports_enabled: true },
    version: 1,
    created_at: iso(now),
  };
}
