CREATE TABLE graduation_outcome (
    outcome_id          INT PRIMARY KEY AUTO_INCREMENT,
    student_id          INT NOT NULL UNIQUE,

    expected_end_date   DATE NOT NULL,
    actual_end_date     DATE NULL,
    -- NULL if still ongoing or dropped out

    time_to_degree_months INT GENERATED ALWAYS AS (
        TIMESTAMPDIFF(MONTH,
            (SELECT enrollment_date FROM student s WHERE s.student_id = graduation_outcome.student_id),
            actual_end_date
        )
    ) STORED,

    is_delayed          BOOLEAN NOT NULL DEFAULT FALSE,
    -- TRUE if actual_end_date > expected_end_date

    final_status ENUM(
        'Graduated On-time',
        'Graduated Delayed',
        'Dropped Out',
        'Ongoing'
    ) NOT NULL,

    FOREIGN KEY (student_id) REFERENCES student(student_id)
);

-- =====================
-- 7. USEFUL VIEWS
-- =====================

-- Flat view for clustering export
CREATE VIEW v_clustering_features AS
SELECT
    s.student_id,
    s.degree_type,
    s.gender,
    s.age_at_enrollment,
    cr.region_name          AS country_region,
    s.marital_status,
    s.num_children,
    s.youngest_child_age,
    d.discipline_group,
    s.entry_gpa,
    s.is_cross_discipline,
    s.study_method,
    ft.funding_name         AS funding_type,
    s.has_external_work,
    s.weekly_work_hours,
    s.in_research_group,
    s.family_support,
    -- Milestone delay indicators
    DATEDIFF(sm_rpd.actual_date, sm_rpd.expected_date) AS rpd_delay_days,
    DATEDIFF(sm_pub.actual_date, sm_pub.expected_date) AS publication_delay_days,
    DATEDIFF(sm_ts.actual_date, sm_ts.expected_date)   AS thesis_seminar_delay_days,
    -- PPM performance
    ppm.cumulative_us,
    ppm.ppm_status,
    -- Examiner avg scores (aggregated if multiple examiners)
    AVG(er.score_avg)       AS examiner_avg_score,
    -- Validation labels (NOT for training)
    go.is_delayed,
    go.final_status,
    go.time_to_degree_months
FROM student s
LEFT JOIN country c             ON s.country_id = c.country_id
LEFT JOIN country_region cr     ON c.region_id = cr.region_id
LEFT JOIN discipline d          ON s.discipline_id = d.discipline_id
LEFT JOIN funding_type ft       ON s.funding_id = ft.funding_id
LEFT JOIN student_milestone sm_rpd ON s.student_id = sm_rpd.student_id AND sm_rpd.milestone_id = 1
LEFT JOIN student_milestone sm_pub ON s.student_id = sm_pub.student_id AND sm_pub.milestone_id = 3
LEFT JOIN student_milestone sm_ts  ON s.student_id = sm_ts.student_id  AND sm_ts.milestone_id = 4
LEFT JOIN v_ppm_us_count ppm    ON s.student_id = ppm.student_id
LEFT JOIN examiner_report er    ON s.student_id = er.student_id
LEFT JOIN graduation_outcome go ON s.student_id = go.student_id
GROUP BY s.student_id;

-- =====================
-- 8. SUPERVISOR / USER SYSTEM
-- =====================

CREATE TABLE supervisor (
    supervisor_id       INT PRIMARY KEY AUTO_INCREMENT,
    staff_id            VARCHAR(50) NOT NULL UNIQUE,
    -- e.g., "MU081217"
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
    FOREIGN KEY (student_id)    REFERENCES student(student_id),
    FOREIGN KEY (supervisor_id) REFERENCES supervisor(supervisor_id)
);

-- =====================
-- 9. EMAIL LOG
-- =====================

CREATE TABLE email_log (
    log_id              INT PRIMARY KEY AUTO_INCREMENT,
    student_id          INT NOT NULL,
    recipient_type      ENUM('Student', 'Supervisor', 'Admin') NOT NULL,
    recipient_email     VARCHAR(200) NOT NULL,
    subject             VARCHAR(500) NOT NULL,
    body                TEXT NOT NULL,
    trigger_type        ENUM('Auto', 'Manual') NOT NULL,
    -- Auto = scheduled reminder, Manual = sent via chatbox
    urgency_level       ENUM('Normal', 'Urgent', 'Critical') NOT NULL DEFAULT 'Normal',
    milestone_id        INT NULL,
    sent_at             DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id)   REFERENCES student(student_id),
    FOREIGN KEY (milestone_id) REFERENCES milestone(milestone_id)
);

-- =====================
-- 10. CHAT HISTORY
-- =====================

CREATE TABLE chat_history (
    chat_id             INT PRIMARY KEY AUTO_INCREMENT,
    supervisor_id       INT NOT NULL,
    session_id          VARCHAR(100) NOT NULL,
    -- Group messages into conversations
    message             TEXT NOT NULL,
    role                ENUM('user', 'assistant') NOT NULL,
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (supervisor_id) REFERENCES supervisor(supervisor_id)
);

-- =====================
-- 11. REMINDER RULES
-- =====================

CREATE TABLE reminder_rule (
    rule_id             INT PRIMARY KEY AUTO_INCREMENT,
    days_before         INT NOT NULL,
    -- 30, 15, 7, 0 (overdue)
    notify_student      BOOLEAN NOT NULL DEFAULT TRUE,
    notify_supervisor   BOOLEAN NOT NULL DEFAULT FALSE,
    notify_admin        BOOLEAN NOT NULL DEFAULT FALSE,
    urgency_level       ENUM('Normal', 'Urgent', 'Critical') NOT NULL,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE
);

-- Pre-populate reminder rules
INSERT INTO reminder_rule (days_before, notify_student, notify_supervisor, notify_admin, urgency_level) VALUES
(30,  TRUE,  FALSE, FALSE, 'Normal'),
(15,  TRUE,  TRUE,  FALSE, 'Urgent'),
(7,   TRUE,  TRUE,  FALSE, 'Critical'),
(0,   TRUE,  TRUE,  TRUE,  'Critical');
-- 0 = overdue (expected_date has passed)

