-- ============================================
-- DATATRAIN: Graduate Student Clustering Database
-- Purpose: Collect student data for clustering analysis
--          to identify delayed graduation patterns
-- ============================================

-- =====================
-- 1. LOOKUP TABLES
-- =====================

CREATE TABLE country_region (
    region_id       INT PRIMARY KEY AUTO_INCREMENT,
    region_name     VARCHAR(50) NOT NULL UNIQUE
    -- e.g., East Asia, South Asia, Southeast Asia, Middle East, Europe, Africa, Americas
);

CREATE TABLE country (
    country_id      INT PRIMARY KEY AUTO_INCREMENT,
    country_name    VARCHAR(100) NOT NULL UNIQUE,
    region_id       INT NOT NULL,
    FOREIGN KEY (region_id) REFERENCES country_region(region_id)
);

CREATE TABLE faculty (
    faculty_id          INT PRIMARY KEY AUTO_INCREMENT,
    faculty_description VARCHAR(200) NOT NULL UNIQUE
    -- e.g., "Faculty of AI and Engineering", "Faculty of Business"
);

CREATE TABLE program (
    program_id              INT PRIMARY KEY AUTO_INCREMENT,
    program_short_desc      VARCHAR(50) NOT NULL,
    -- e.g., "Ph.D. (Eng)", "M.Sc. (CS)"
    program_description     VARCHAR(200) NOT NULL,
    -- e.g., "Doctor of Philosophy (Engineering)", "Master of Science (Computer Science)"
    faculty_id              INT NOT NULL,
    FOREIGN KEY (faculty_id) REFERENCES faculty(faculty_id)
);

CREATE TABLE discipline (
    discipline_id   INT PRIMARY KEY AUTO_INCREMENT,
    discipline_name VARCHAR(100) NOT NULL UNIQUE,
    discipline_group VARCHAR(50) NOT NULL
    -- discipline_group: STEM, Social Science, Humanities, Business, etc.
);

CREATE TABLE funding_type (
    funding_id      INT PRIMARY KEY AUTO_INCREMENT,
    funding_name    VARCHAR(100) NOT NULL UNIQUE
    -- e.g., Full Scholarship, Partial Scholarship, Self-funded, TA, RA, Employer-sponsored
);

CREATE TABLE campus (
    campus_id       INT PRIMARY KEY AUTO_INCREMENT,
    campus_name     VARCHAR(200) NOT NULL UNIQUE
);

-- =====================
-- 2. CORE: STUDENT
-- =====================

CREATE TABLE student (
    student_id          INT PRIMARY KEY AUTO_INCREMENT,
    student_id_number   VARCHAR(50) NOT NULL UNIQUE,
    -- University student ID, e.g., "250PA247R8"
    student_name        VARCHAR(200) NOT NULL,
    email               VARCHAR(200) NULL,
    campus_id           INT NOT NULL,

    -- Term / intake info (from university system)
    campus_code         VARCHAR(20) NULL,
    -- e.g., "247R1" — the specific block/room code from CAMPUS_ID column
    admit_term          INT NULL,
    -- Intake term code, e.g., 2500 = Jan 2025 intake
    admit_term_begin_date DATE NULL,
    -- First day of the intake term, e.g., 2025-01-01
    expected_grad_term  INT NULL,
    -- Expected graduation term code, e.g., 3000 = 2030
    program_status      VARCHAR(50) NULL DEFAULT 'Active in Program',
    -- e.g., "Active in Program", "Completed", "Withdrawn"

    -- Demographic
    gender              ENUM('Male', 'Female', 'Other') NULL,
    date_of_birth       DATE NULL,
    country_id          INT NULL,
    marital_status      ENUM('Single', 'Married', 'Divorced', 'Widowed') NULL,
    num_children        INT NOT NULL DEFAULT 0,
    youngest_child_age  DECIMAL(3,1) NULL,
    -- NULL if num_children = 0

    -- Academic Background
    program_id          INT NOT NULL,
    degree_type         ENUM('Master', 'PhD') NOT NULL,
    discipline_id       INT NULL,
    enrollment_date     DATE NOT NULL,
    entry_gpa           DECIMAL(4,2) NULL,
    -- GPA scale varies by country, standardize during preprocessing
    is_cross_discipline BOOLEAN NOT NULL DEFAULT FALSE,
    study_method        ENUM('Full-time', 'Part-time') NOT NULL,

    -- Financial
    funding_id          INT NULL,
    has_external_work   BOOLEAN NOT NULL DEFAULT FALSE,
    weekly_work_hours   DECIMAL(4,1) NOT NULL DEFAULT 0,

    -- Social Support
    in_research_group   BOOLEAN NOT NULL DEFAULT FALSE,
    family_support      TINYINT NULL CHECK (family_support BETWEEN 1 AND 5),
    -- Likert scale: 1=Very Low, 2=Low, 3=Moderate, 4=High, 5=Very High

    -- Computed (for clustering) — only when date_of_birth is available
    age_at_enrollment   INT GENERATED ALWAYS AS (
        CASE WHEN date_of_birth IS NOT NULL
             THEN TIMESTAMPDIFF(YEAR, date_of_birth, enrollment_date)
             ELSE NULL END
    ) STORED,

    FOREIGN KEY (campus_id)        REFERENCES campus(campus_id),
    FOREIGN KEY (program_id)       REFERENCES program(program_id),
    FOREIGN KEY (country_id)       REFERENCES country(country_id),
    FOREIGN KEY (discipline_id)    REFERENCES discipline(discipline_id),
    FOREIGN KEY (funding_id)       REFERENCES funding_type(funding_id)
);

-- =====================
-- 3. MILESTONE TRACKING
-- =====================

CREATE TABLE milestone (
    milestone_id        INT PRIMARY KEY,
    milestone_name      VARCHAR(100) NOT NULL UNIQUE,
    milestone_order     INT NOT NULL,
    -- Recommended timeline (months from enrollment)
    master_ft_norm      INT NULL,
    master_ft_max       INT NULL,
    master_pt_norm      INT NULL,
    master_pt_max       INT NULL,
    phd_ft_norm         INT NULL,
    phd_ft_max          INT NULL,
    phd_pt_norm         INT NULL,
    phd_pt_max          INT NULL
);

-- Pre-populate milestone definitions
INSERT INTO milestone VALUES
(1, 'Research Proposal Defence (RPD)',    1, 6,  9,  9,  12, 9,  12, 12, 15),
(2, 'Postgraduate Progress Monitoring (PPM)', 2, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
(3, 'Publication Requirement',            3, 15, 15, 15, 15, 24, 24, 24, 24),
(4, 'Thesis Seminar',                     4, 18, 20, 18, 20, 30, 32, 30, 32),
(5, 'Thesis Submission for Examination',  5, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
(6, 'BOE Viva Voce',                      6, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL),
(7, 'Final Thesis Submission',            7, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL);

CREATE TABLE student_milestone (
    id                  INT PRIMARY KEY AUTO_INCREMENT,
    student_id          INT NOT NULL,
    milestone_id        INT NOT NULL,
    earliest_start_date DATE NULL,
    -- Earliest allowed start date (only used by Thesis Seminar milestone)
    expected_date       DATE NULL,
    actual_date         DATE NULL,
    status              ENUM('Pending', 'Completed', 'Overdue') NOT NULL DEFAULT 'Pending',
    remarks             TEXT NULL,

    UNIQUE KEY (student_id, milestone_id),
    FOREIGN KEY (student_id)   REFERENCES student(student_id),
    FOREIGN KEY (milestone_id) REFERENCES milestone(milestone_id)
);

-- =====================
-- 4. PPM RECORDS
-- =====================

CREATE TABLE ppm_record (
    ppm_id              INT PRIMARY KEY AUTO_INCREMENT,
    student_id          INT NOT NULL,
    ppm_year            YEAR NOT NULL,
    ppm_cycle           TINYINT NOT NULL,
    -- 1 = First Half (Jun/Sep), 2 = Second Half (Dec/Mar)
    result              ENUM('S', 'US') NULL,
    -- S = Satisfactory, US = Unsatisfactory
    verify_status       ENUM('Y', 'N') NOT NULL DEFAULT 'N',
    verify_date         DATE NULL,
    verified_by_id      VARCHAR(50) NULL,
    -- Supervisor/Verifier staff ID, e.g., "MU081217"
    verified_by_name    VARCHAR(200) NULL,
    remarks             TEXT NULL,

    UNIQUE KEY (student_id, ppm_year, ppm_cycle),
    FOREIGN KEY (student_id) REFERENCES student(student_id)
);

-- Cumulative US count view (3 cumulative US = terminated)
CREATE VIEW v_ppm_us_count AS
SELECT
    student_id,
    SUM(CASE WHEN result = 'US' THEN 1 ELSE 0 END) AS cumulative_us,
    COUNT(*) AS total_ppm,
    CASE
        WHEN SUM(CASE WHEN result = 'US' THEN 1 ELSE 0 END) >= 3 THEN 'TERMINATED'
        WHEN SUM(CASE WHEN result = 'US' THEN 1 ELSE 0 END) >= 2 THEN 'AT RISK'
        ELSE 'OK'
    END AS ppm_status
FROM ppm_record
GROUP BY student_id;

-- =====================
-- 5. EXAMINER REPORT
-- =====================

CREATE TABLE examiner (
    examiner_id         INT PRIMARY KEY AUTO_INCREMENT,
    examiner_name       VARCHAR(200) NOT NULL,
    institution         VARCHAR(200) NULL,
    is_external         BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE examiner_report (
    report_id           INT PRIMARY KEY AUTO_INCREMENT,
    student_id          INT NOT NULL,
    examiner_id         INT NOT NULL,
    report_date         DATE NOT NULL,

    -- 10 rating dimensions (1-5 scale, matching the docx templates)
    -- Both Master & PhD share the same 10 dimensions
    score_motivation        TINYINT NOT NULL CHECK (score_motivation BETWEEN 1 AND 5),
    score_objectives        TINYINT NOT NULL CHECK (score_objectives BETWEEN 1 AND 5),
    score_literature        TINYINT NOT NULL CHECK (score_literature BETWEEN 1 AND 5),
    score_methodology       TINYINT NOT NULL CHECK (score_methodology BETWEEN 1 AND 5),
    score_data_collection   TINYINT NOT NULL CHECK (score_data_collection BETWEEN 1 AND 5),
    score_analysis          TINYINT NOT NULL CHECK (score_analysis BETWEEN 1 AND 5),
    score_contribution      TINYINT NOT NULL CHECK (score_contribution BETWEEN 1 AND 5),
    score_references        TINYINT NOT NULL CHECK (score_references BETWEEN 1 AND 5),
    score_rigour            TINYINT NOT NULL CHECK (score_rigour BETWEEN 1 AND 5),
    score_general           TINYINT NOT NULL CHECK (score_general BETWEEN 1 AND 5),

    -- Average score (computed)
    score_avg DECIMAL(3,2) GENERATED ALWAYS AS (
        (score_motivation + score_objectives + score_literature +
         score_methodology + score_data_collection + score_analysis +
         score_contribution + score_references + score_rigour + score_general) / 10.0
    ) STORED,

    -- Recommendation outcome
    recommendation ENUM(
        'Accepted',
        'Minor Modifications',
        'Major Corrections',
        'Re-examination',
        'Rejected'
    ) NOT NULL,

    -- PhD-specific: sub-option if rejected
    rejection_suboption ENUM(
        'Award Master',
        'Resubmit as Master',
        'No Degree'
    ) NULL,
    -- Only applicable when degree_type = PhD AND recommendation = Rejected

    FOREIGN KEY (student_id)  REFERENCES student(student_id),
    FOREIGN KEY (examiner_id) REFERENCES examiner(examiner_id)
);

-- =====================
-- 6. GRADUATION OUTCOME
-- (Validation labels - NOT used in clustering training)
-- =====================

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

-- =====================
-- 12. ML RISK PREDICTION
-- =====================

CREATE TABLE student_risk_prediction (
    prediction_id       INT PRIMARY KEY AUTO_INCREMENT,
    student_id          INT NOT NULL UNIQUE,
    risk_score          DECIMAL(5,2) NOT NULL,
    -- 0 = lowest risk, 100 = highest risk
    risk_label          ENUM('Low', 'Medium', 'High') NOT NULL,
    cluster_id          INT NOT NULL,
    -- K-Means cluster (0, 1, 2)
    key_risk_factors    TEXT NULL,
    -- JSON array of human-readable risk reasons
    predicted_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (student_id) REFERENCES student(student_id)
);
