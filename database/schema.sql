-- SkillSwap database schema (Supabase PostgreSQL)
--
-- You normally do NOT need to run this: the Flask app creates these tables
-- automatically on startup (db.create_all) and adds any new columns to an
-- older database. This file documents the schema and can be pasted into the
-- Supabase SQL Editor if you prefer to create the tables by hand.
--
-- Tables: users, skills, user_skills, match_requests, messages, sessions, reviews

CREATE TABLE IF NOT EXISTS skills (
	id SERIAL NOT NULL, 
	name VARCHAR(80) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (name)
);

CREATE TABLE IF NOT EXISTS users (
	id SERIAL NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	email VARCHAR(150) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	college VARCHAR(150), 
	branch VARCHAR(100), 
	year VARCHAR(30), 
	bio TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	is_public BOOLEAN DEFAULT false NOT NULL, 
	linkedin_url VARCHAR(255), 
	linkedin_sub VARCHAR(100), 
	linkedin_name VARCHAR(150), 
	linkedin_email VARCHAR(150), 
	linkedin_picture VARCHAR(1000), 
	linkedin_status VARCHAR(20) DEFAULT 'unverified' NOT NULL, 
	linkedin_name_score INTEGER, 
	linkedin_email_match BOOLEAN, 
	linkedin_checked_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (email), 
	UNIQUE (linkedin_sub)
);

CREATE TABLE IF NOT EXISTS match_requests (
	id SERIAL NOT NULL, 
	sender_id INTEGER NOT NULL, 
	receiver_id INTEGER NOT NULL, 
	message VARCHAR(500), 
	status VARCHAR(20), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(sender_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(receiver_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS messages (
	id SERIAL NOT NULL, 
	sender_id INTEGER NOT NULL, 
	receiver_id INTEGER NOT NULL, 
	body TEXT NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(sender_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(receiver_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reviews (
	id SERIAL NOT NULL, 
	reviewer_id INTEGER NOT NULL, 
	reviewed_user_id INTEGER NOT NULL, 
	rating INTEGER NOT NULL, 
	comment VARCHAR(500), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_review_pair UNIQUE (reviewer_id, reviewed_user_id), 
	FOREIGN KEY(reviewer_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(reviewed_user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sessions (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	partner_id INTEGER, 
	topic VARCHAR(150) NOT NULL, 
	session_date TIMESTAMP WITHOUT TIME ZONE, 
	duration_minutes INTEGER, 
	status VARCHAR(20), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(partner_id) REFERENCES users (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS user_skills (
	id SERIAL NOT NULL, 
	user_id INTEGER NOT NULL, 
	skill_id INTEGER NOT NULL, 
	skill_type VARCHAR(10) NOT NULL, 
	proficiency VARCHAR(30), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_user_skill UNIQUE (user_id, skill_id, skill_type), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(skill_id) REFERENCES skills (id)
);

-- One LinkedIn account can verify only one SkillSwap account.
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_linkedin_sub ON users (linkedin_sub) WHERE linkedin_sub IS NOT NULL;

-- Helpful indexes for common lookups.
CREATE INDEX IF NOT EXISTS ix_user_skills_user ON user_skills (user_id);
CREATE INDEX IF NOT EXISTS ix_match_requests_receiver ON match_requests (receiver_id, status);
CREATE INDEX IF NOT EXISTS ix_match_requests_sender ON match_requests (sender_id, status);
CREATE INDEX IF NOT EXISTS ix_messages_pair ON messages (sender_id, receiver_id, id);
