-- Immutable table snapshot for revision 0001.

CREATE TABLE organizations (
	name VARCHAR(150) NOT NULL, 
	settings JSON NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE departments (
	name VARCHAR(100) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (organization_id, name), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
);

CREATE INDEX ix_departments_organization_id ON departments (organization_id);

CREATE TABLE locations (
	name VARCHAR(100) NOT NULL, 
	building VARCHAR(150) NOT NULL, 
	floor VARCHAR(50) NOT NULL, 
	timezone VARCHAR(100) NOT NULL, 
	active BOOLEAN NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
);

CREATE INDEX ix_locations_organization_id ON locations (organization_id);

CREATE TABLE users (
	full_name VARCHAR(100) NOT NULL, 
	email VARCHAR(254) NOT NULL, 
	role VARCHAR(16) NOT NULL, 
	department_id VARCHAR(36), 
	status VARCHAR(16) NOT NULL, 
	preferences JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (organization_id, email), 
	CHECK (role IN ('admin','doctor')), 
	CHECK (status IN ('active','disabled')), 
	FOREIGN KEY(department_id) REFERENCES departments (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
);

CREATE INDEX ix_users_organization_id ON users (organization_id);

CREATE TABLE wifi_networks (
	location_id VARCHAR(36) NOT NULL, 
	ssid VARCHAR(100) NOT NULL, 
	controller_identifier VARCHAR(150) NOT NULL, 
	authentication_configuration JSON NOT NULL, 
	active BOOLEAN NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (organization_id, controller_identifier), 
	FOREIGN KEY(location_id) REFERENCES locations (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
);

CREATE INDEX ix_wifi_networks_organization_id ON wifi_networks (organization_id);

CREATE INDEX ix_wifi_networks_location_id ON wifi_networks (location_id);

CREATE TABLE activity_reports (
	doctor_id VARCHAR(36) NOT NULL, 
	location_id VARCHAR(36), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	original_transcript TEXT NOT NULL, 
	edited_transcript TEXT NOT NULL, 
	category VARCHAR(60) NOT NULL, 
	tags JSON NOT NULL, 
	summary JSON NOT NULL, 
	review_status VARCHAR(16) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(doctor_id) REFERENCES users (id), 
	FOREIGN KEY(location_id) REFERENCES locations (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
);

CREATE INDEX ix_activity_reports_doctor_id ON activity_reports (doctor_id);

CREATE INDEX ix_activity_reports_organization_id ON activity_reports (organization_id);

CREATE TABLE attendance_sessions (
	doctor_id VARCHAR(36) NOT NULL, 
	location_id VARCHAR(36) NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	ended_at TIMESTAMP WITH TIME ZONE, 
	duration_seconds INTEGER NOT NULL, 
	confidence_status VARCHAR(32) NOT NULL, 
	session_status VARCHAR(16) NOT NULL, 
	source VARCHAR(16) NOT NULL, 
	revision INTEGER NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (duration_seconds >= 0), 
	CHECK (ended_at IS NULL OR ended_at >= started_at), 
	FOREIGN KEY(doctor_id) REFERENCES users (id), 
	FOREIGN KEY(location_id) REFERENCES locations (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
);

CREATE INDEX ix_attendance_sessions_organization_id ON attendance_sessions (organization_id);

CREATE INDEX attendance_period ON attendance_sessions (organization_id, doctor_id, started_at);

CREATE INDEX ix_attendance_sessions_doctor_id ON attendance_sessions (doctor_id);

CREATE TABLE audit_logs (
	actor_id VARCHAR(36), 
	action VARCHAR(100) NOT NULL, 
	resource_type VARCHAR(60) NOT NULL, 
	resource_id VARCHAR(100), 
	timestamp TIMESTAMP WITH TIME ZONE NOT NULL, 
	outcome VARCHAR(20) NOT NULL, 
	metadata JSON NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
);

CREATE INDEX ix_audit_logs_organization_id ON audit_logs (organization_id);

CREATE TABLE auth_sessions (
	token_hash VARCHAR(64) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (token_hash), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_auth_sessions_user_id ON auth_sessions (user_id);

CREATE TABLE identity_mappings (
	issuer VARCHAR(250) NOT NULL, 
	subject VARCHAR(250) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (issuer, subject), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_identity_mappings_user_id ON identity_mappings (user_id);

CREATE TABLE processing_jobs (
	doctor_id VARCHAR(36) NOT NULL, 
	kind VARCHAR(40) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	payload JSON NOT NULL, 
	result JSON NOT NULL, 
	error TEXT, 
	attempts INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(doctor_id) REFERENCES users (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
);

CREATE INDEX ix_processing_jobs_organization_id ON processing_jobs (organization_id);

CREATE INDEX ix_processing_jobs_doctor_id ON processing_jobs (doctor_id);

CREATE TABLE registered_devices (
	doctor_id VARCHAR(36) NOT NULL, 
	device_identifier VARCHAR(150) NOT NULL, 
	identity_reference VARCHAR(250) NOT NULL, 
	enrollment_status VARCHAR(16) NOT NULL, 
	last_seen TIMESTAMP WITH TIME ZONE, 
	organization_id VARCHAR(36) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (organization_id, identity_reference, device_identifier), 
	FOREIGN KEY(doctor_id) REFERENCES users (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
);

CREATE INDEX ix_registered_devices_organization_id ON registered_devices (organization_id);

CREATE INDEX ix_registered_devices_doctor_id ON registered_devices (doctor_id);

CREATE TABLE attendance_corrections (
	doctor_id VARCHAR(36) NOT NULL, 
	session_id VARCHAR(36), 
	requested_changes JSON NOT NULL, 
	reason TEXT NOT NULL, 
	approval_status VARCHAR(16) NOT NULL, 
	reviewed_by VARCHAR(36), 
	reviewed_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(doctor_id) REFERENCES users (id), 
	FOREIGN KEY(session_id) REFERENCES attendance_sessions (id) ON DELETE SET NULL, 
	FOREIGN KEY(reviewed_by) REFERENCES users (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
);

CREATE INDEX ix_attendance_corrections_organization_id ON attendance_corrections (organization_id);

CREATE INDEX ix_attendance_corrections_doctor_id ON attendance_corrections (doctor_id);

CREATE TABLE audio_recordings (
	doctor_id VARCHAR(36) NOT NULL, 
	report_id VARCHAR(36), 
	storage_reference VARCHAR(500) NOT NULL, 
	recording_duration INTEGER NOT NULL, 
	retention_expiration TIMESTAMP WITH TIME ZONE NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(doctor_id) REFERENCES users (id), 
	FOREIGN KEY(report_id) REFERENCES activity_reports (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
);

CREATE INDEX ix_audio_recordings_doctor_id ON audio_recordings (doctor_id);

CREATE INDEX ix_audio_recordings_organization_id ON audio_recordings (organization_id);

CREATE TABLE network_events (
	doctor_id VARCHAR(36) NOT NULL, 
	device_id VARCHAR(36) NOT NULL, 
	network_id VARCHAR(36) NOT NULL, 
	location_id VARCHAR(36) NOT NULL, 
	event_type VARCHAR(16) NOT NULL, 
	source_event_id VARCHAR(200) NOT NULL, 
	accounting_session_id VARCHAR(200) NOT NULL, 
	event_timestamp TIMESTAMP WITH TIME ZONE NOT NULL, 
	received_timestamp TIMESTAMP WITH TIME ZONE NOT NULL, 
	raw_metadata_reference JSON NOT NULL, 
	provider VARCHAR(32) NOT NULL, 
	organization_id VARCHAR(36) NOT NULL, 
	id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (organization_id, provider, source_event_id), 
	CHECK (event_type IN ('start','stop','interim','outage')), 
	FOREIGN KEY(doctor_id) REFERENCES users (id), 
	FOREIGN KEY(device_id) REFERENCES registered_devices (id), 
	FOREIGN KEY(network_id) REFERENCES wifi_networks (id), 
	FOREIGN KEY(location_id) REFERENCES locations (id), 
	FOREIGN KEY(organization_id) REFERENCES organizations (id)
);

CREATE INDEX ix_network_events_organization_id ON network_events (organization_id);

CREATE INDEX ix_network_events_doctor_id ON network_events (doctor_id);

CREATE INDEX event_replay ON network_events (organization_id, doctor_id, event_timestamp);
