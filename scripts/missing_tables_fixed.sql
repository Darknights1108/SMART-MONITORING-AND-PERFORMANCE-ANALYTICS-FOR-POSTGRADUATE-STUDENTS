CREATE TABLE IF NOT EXISTS graduation_outcome (
    outcome_id          INT PRIMARY KEY AUTO_INCREMENT,
    student_id          INT NOT NULL UNIQUE,
    expected_end_date   DATE NOT NULL,
    actual_end_date     DATE NULL,
    time_to_degree_months INT NULL,
    is_delayed          BOOLEAN NOT NULL DEFAULT FALSE,
    final_status ENUM(
        'Graduated On-time',
        'Graduated Delayed',
        'Dropped Out',
        'Ongoing'
    ) NOT NULL,
    FOREIGN KEY (student_id) REFERENCES student(student_id)
);

CREATE TABLE IF NOT EXISTS supervisor (
    supervisor_id       INT PRIMARY KEY AUTO_INCREMENT,
    staff_id            VARCHAR(20) NOT NULL UNIQUE,
    name                VARCHAR(100) NOT NULL,
    email               VARCHAR(150) NOT NULL UNIQUE,
    role                ENUM('Supervisor', 'Admin', 'Both') NOT NULL DEFAULT 'Supervisor',
    password_hash       VARCHAR(255) NOT NULL,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS student_supervisor (
    id                  INT PRIMARY KEY AUTO_INCREMENT,
    student_id          INT NOT NULL,
    supervisor_id       INT NOT NULL,
    role                ENUM('Main', 'Co') NOT NULL DEFAULT 'Main',
    assigned_date       DATE NOT NULL,
    UNIQUE KEY (student_id, supervisor_id),
    FOREIGN KEY (student_id) REFERENCES student(student_id),
    FOREIGN KEY (supervisor_id) REFERENCES supervisor(supervisor_id)
);

CREATE TABLE IF NOT EXISTS email_log (
    log_id              INT PRIMARY KEY AUTO_INCREMENT,
    student_id          INT NULL,
    recipient_type      ENUM('Student', 'Supervisor', 'Admin') NOT NULL,
    recipient_email     VARCHAR(150) NOT NULL,
    subject             VARCHAR(255) NOT NULL,
    body                TEXT NOT NULL,
    sent_at             DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    trigger_type        ENUM('Auto', 'Manual') NOT NULL DEFAULT 'Auto',
    urgency_level       ENUM('Normal', 'Urgent', 'Critical') NOT NULL DEFAULT 'Normal',
    FOREIGN KEY (student_id) REFERENCES student(student_id)
);

CREATE TABLE IF NOT EXISTS chat_history (
    chat_id             INT PRIMARY KEY AUTO_INCREMENT,
    supervisor_id       INT NOT NULL,
    session_id          VARCHAR(64) NOT NULL,
    role                ENUM('user', 'assistant') NOT NULL,
    message             TEXT NOT NULL,
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (supervisor_id) REFERENCES supervisor(supervisor_id)
);

CREATE TABLE IF NOT EXISTS reminder_rule (
    rule_id             INT PRIMARY KEY AUTO_INCREMENT,
    days_before         INT NOT NULL,
    notify_student      BOOLEAN NOT NULL DEFAULT TRUE,
    notify_supervisor   BOOLEAN NOT NULL DEFAULT FALSE,
    notify_admin        BOOLEAN NOT NULL DEFAULT FALSE,
    urgency_level       ENUM('Normal', 'Urgent', 'Critical') NOT NULL DEFAULT 'Normal',
    is_active           BOOLEAN NOT NULL DEFAULT TRUE
);

INSERT IGNORE INTO reminder_rule (days_before, notify_student, notify_supervisor, notify_admin, urgency_level) VALUES
(30, TRUE,  FALSE, FALSE, 'Normal'),
(14, TRUE,  TRUE,  FALSE, 'Normal'),
(7,  TRUE,  TRUE,  FALSE, 'Urgent'),
(0,  TRUE,  TRUE,  TRUE,  'Critical');
