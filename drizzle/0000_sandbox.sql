CREATE TABLE sandbox_workspaces (
  owner TEXT PRIMARY KEY NOT NULL,
  data TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1
);
