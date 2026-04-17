DROP TABLE IF EXISTS chat_history;
DROP TABLE IF EXISTS email_log;
DROP TABLE IF EXISTS student_supervisor;
DROP TABLE IF EXISTS supervisor;

CREATE TABLE supervisor (
    supervisor_id       INT PRIMARY KEY AUTO_INCREMENT,
    staff_id            VARCHAR(50) NOT NULL UNIQUE,
    name                VARCHAR(200) NOT NULL,
    email               VARCHAR(200) NOT NULL,
    faculty_id          INT NOT NULL,
    role                ENUM('Supervisor', 'Admin', 'Both') NOT NULL DEFAULT 'Supervisor',
    password_hash       VARCHAR(255) NOT NULL,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (faculty_id) REFERENCES faculty(faculty_id)
);

CREATE TABLE student_supervisor (
    id                  INT PRIMARY KEY AUTO_INCREMENT,
    student_id          INT NOT NULL,
    supervisor_id       INT NOT NULL,
    role                ENUM('Main', 'Co') NOT NULL DEFAULT 'Main',
    assigned_date       DATE NOT NULL,
    UNIQUE KEY (student_id, supervisor_id),
    FOREIGN KEY (student_id) REFERENCES student(student_id),
    FOREIGN KEY (supervisor_id) REFERENCES supervisor(supervisor_id)
);

CREATE TABLE email_log (
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

CREATE TABLE chat_history (
    chat_id             INT PRIMARY KEY AUTO_INCREMENT,
    supervisor_id       INT NOT NULL,
    session_id          VARCHAR(64) NOT NULL,
    role                ENUM('user', 'assistant') NOT NULL,
    message             TEXT NOT NULL,
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (supervisor_id) REFERENCES supervisor(supervisor_id)
);
