-- ============================================
-- SEED DATA for development/testing
-- ============================================

USE datatrain;

-- Regions
INSERT INTO country_region (region_name) VALUES
('East Asia'), ('South Asia'), ('Southeast Asia'), ('Middle East'), ('Europe'), ('Africa'), ('Americas');

-- Countries
INSERT INTO country (country_name, region_id) VALUES
('China', 1), ('Japan', 1), ('South Korea', 1),
('India', 2), ('Pakistan', 2), ('Bangladesh', 2),
('Malaysia', 3), ('Indonesia', 3), ('Thailand', 3), ('Vietnam', 3),
('Saudi Arabia', 4), ('Iran', 4),
('United Kingdom', 5), ('Germany', 5),
('Nigeria', 6), ('Kenya', 6),
('United States', 7), ('Brazil', 7);

-- Faculties
INSERT INTO faculty (faculty_description) VALUES
('Faculty of AI and Engineering'),
('Faculty of Business and Management'),
('Faculty of Science'),
('Faculty of Social Sciences and Humanities');

-- Programs
INSERT INTO program (program_short_desc, program_description, faculty_id) VALUES
('Ph.D. (Eng)', 'Doctor of Philosophy (Engineering)', 1),
('M.Sc. (CS)', 'Master of Science (Computer Science)', 1),
('Ph.D. (Bus)', 'Doctor of Philosophy (Business)', 2),
('M.B.A.', 'Master of Business Administration', 2),
('Ph.D. (Sci)', 'Doctor of Philosophy (Science)', 3),
('M.Sc. (Math)', 'Master of Science (Mathematics)', 3),
('Ph.D. (SS)', 'Doctor of Philosophy (Social Science)', 4),
('M.A. (Edu)', 'Master of Arts (Education)', 4);

-- Disciplines
INSERT INTO discipline (discipline_name, discipline_group) VALUES
('Computer Science', 'STEM'), ('Electrical Engineering', 'STEM'),
('Mechanical Engineering', 'STEM'), ('Data Science', 'STEM'),
('Finance', 'Business'), ('Marketing', 'Business'),
('Physics', 'STEM'), ('Chemistry', 'STEM'),
('Education', 'Social Science'), ('Psychology', 'Social Science');

-- Funding types
INSERT INTO funding_type (funding_name) VALUES
('Full Scholarship'), ('Partial Scholarship'), ('Self-funded'),
('Teaching Assistant'), ('Research Assistant'), ('Employer-sponsored');

-- Campus
INSERT INTO campus (campus_name) VALUES
('Main Campus'), ('City Campus'), ('Online');

-- Sample Supervisors (password: "password123" hashed with bcrypt)
INSERT INTO supervisor (staff_id, name, email, faculty_id, role, password_hash) VALUES
('ADM001', 'Dr. Admin User', 'admin@university.edu', 1, 'Both',
    '$2b$12$LJ3m4ys3Gz8Kvf0fRsRXB.JpGpx/A6WfFkYzS.3VqYCxLDzFqzfO6'),
('MU081217', 'Dr. Ahmad Rahman', 'ahmad@university.edu', 1, 'Supervisor',
    '$2b$12$LJ3m4ys3Gz8Kvf0fRsRXB.JpGpx/A6WfFkYzS.3VqYCxLDzFqzfO6'),
('MU092301', 'Dr. Sarah Chen', 'sarah.chen@university.edu', 1, 'Supervisor',
    '$2b$12$LJ3m4ys3Gz8Kvf0fRsRXB.JpGpx/A6WfFkYzS.3VqYCxLDzFqzfO6'),
('MU103456', 'Prof. James Wilson', 'j.wilson@university.edu', 2, 'Supervisor',
    '$2b$12$LJ3m4ys3Gz8Kvf0fRsRXB.JpGpx/A6WfFkYzS.3VqYCxLDzFqzfO6');

-- Sample Students
INSERT INTO student (student_id_number, student_name, email, campus_id, gender, date_of_birth, country_id, marital_status, num_children, youngest_child_age, program_id, degree_type, discipline_id, enrollment_date, entry_gpa, is_cross_discipline, study_method, funding_id, has_external_work, weekly_work_hours, in_research_group, family_support) VALUES
('PGS2022001', 'Ali bin Hassan', 'ali.hassan@student.edu', 1, 'Male', '1995-03-15', 7, 'Married', 1, 2.5, 1, 'PhD', 1, '2022-03-01', 3.65, FALSE, 'Full-time', 1, FALSE, 0, TRUE, 4),
('PGS2022002', 'Wei Lin Zhang', 'weilin.z@student.edu', 1, 'Female', '1996-08-20', 1, 'Single', 0, NULL, 1, 'PhD', 4, '2022-03-01', 3.80, TRUE, 'Full-time', 5, FALSE, 0, TRUE, 3),
('PGS2022003', 'Priya Sharma', 'priya.s@student.edu', 1, 'Female', '1994-12-10', 4, 'Married', 2, 1.0, 2, 'Master', 1, '2022-09-01', 3.50, FALSE, 'Part-time', 3, TRUE, 20, FALSE, 5),
('PGS2023001', 'John Smith', 'john.smith@student.edu', 1, 'Male', '1997-06-25', 13, 'Single', 0, NULL, 1, 'PhD', 2, '2023-03-01', 3.45, FALSE, 'Full-time', 1, FALSE, 0, TRUE, 3),
('PGS2023002', 'Siti Nurhaliza', 'siti.n@student.edu', 2, 'Female', '1998-01-30', 7, 'Single', 0, NULL, 3, 'PhD', 5, '2023-03-01', 3.70, FALSE, 'Full-time', 2, FALSE, 0, FALSE, 4),
('PGS2023003', 'Rajesh Kumar', 'rajesh.k@student.edu', 1, 'Male', '1993-04-18', 4, 'Married', 1, 3.0, 5, 'PhD', 7, '2023-09-01', 3.55, FALSE, 'Part-time', 6, TRUE, 15, TRUE, 2),
('PGS2024001', 'Amy Tan', 'amy.tan@student.edu', 1, 'Female', '1999-09-05', 7, 'Single', 0, NULL, 2, 'Master', 1, '2024-03-01', 3.90, FALSE, 'Full-time', 4, FALSE, 0, TRUE, 5),
('PGS2024002', 'Mohammed Al-Farsi', 'mohammed.af@student.edu', 1, 'Male', '1996-11-12', 11, 'Married', 0, NULL, 1, 'PhD', 3, '2024-03-01', 3.40, TRUE, 'Full-time', 1, FALSE, 0, FALSE, 3);

-- Student-Supervisor assignments
INSERT INTO student_supervisor (student_id, supervisor_id, role, assigned_date) VALUES
(1, 2, 'Main', '2022-03-01'), (1, 3, 'Co', '2022-03-01'),
(2, 3, 'Main', '2022-03-01'),
(3, 2, 'Main', '2022-09-01'),
(4, 2, 'Main', '2023-03-01'), (4, 3, 'Co', '2023-03-01'),
(5, 4, 'Main', '2023-03-01'),
(6, 3, 'Main', '2023-09-01'),
(7, 2, 'Main', '2024-03-01'),
(8, 3, 'Main', '2024-03-01');

-- Student Milestones (with realistic dates - some approaching, some overdue)
INSERT INTO student_milestone (student_id, milestone_id, expected_date, actual_date, status) VALUES
-- Ali (PhD, enrolled 2022-03) - progressing but delayed on publication
(1, 1, '2022-12-01', '2023-01-15', 'Completed'),
(1, 3, '2024-03-01', NULL, 'Overdue'),
(1, 4, '2024-09-01', NULL, 'Pending'),
(1, 5, '2025-06-01', NULL, 'Pending'),

-- Wei Lin (PhD, enrolled 2022-03) - on track
(2, 1, '2022-12-01', '2022-11-20', 'Completed'),
(2, 3, '2024-03-01', '2024-02-15', 'Completed'),
(2, 4, '2024-09-01', NULL, 'Pending'),
(2, 5, '2025-06-01', NULL, 'Pending'),

-- Priya (Master PT, enrolled 2022-09) - almost done
(3, 1, '2023-06-01', '2023-05-20', 'Completed'),
(3, 3, '2024-03-01', '2024-04-10', 'Completed'),
(3, 4, '2024-06-01', '2024-07-05', 'Completed'),
(3, 5, '2025-01-01', NULL, 'Overdue'),

-- John (PhD, enrolled 2023-03) - RPD coming up soon!
(4, 1, '2026-04-25', NULL, 'Pending'),
(4, 3, '2025-03-01', NULL, 'Pending'),

-- Siti (PhD, enrolled 2023-03)
(5, 1, '2023-12-01', '2024-02-10', 'Completed'),
(5, 3, '2026-04-20', NULL, 'Pending'),

-- Rajesh (PhD PT, enrolled 2023-09) - at risk
(6, 1, '2024-09-01', NULL, 'Overdue'),

-- Amy (Master FT, enrolled 2024-03)
(7, 1, '2024-09-01', '2024-08-28', 'Completed'),
(7, 3, '2026-06-01', NULL, 'Pending'),
(7, 4, '2026-05-01', NULL, 'Pending'),

-- Mohammed (PhD, enrolled 2024-03)
(8, 1, '2026-05-01', NULL, 'Pending');

-- PPM Records
INSERT INTO ppm_record (student_id, ppm_year, ppm_cycle, result, verify_status, verified_by_id, verified_by_name) VALUES
(1, 2022, 2, 'S', 'Y', 'MU081217', 'Dr. Ahmad Rahman'),
(1, 2023, 1, 'S', 'Y', 'MU081217', 'Dr. Ahmad Rahman'),
(1, 2023, 2, 'US', 'Y', 'MU081217', 'Dr. Ahmad Rahman'),
(1, 2024, 1, 'US', 'Y', 'MU081217', 'Dr. Ahmad Rahman'),
(2, 2022, 2, 'S', 'Y', 'MU092301', 'Dr. Sarah Chen'),
(2, 2023, 1, 'S', 'Y', 'MU092301', 'Dr. Sarah Chen'),
(2, 2023, 2, 'S', 'Y', 'MU092301', 'Dr. Sarah Chen'),
(2, 2024, 1, 'S', 'Y', 'MU092301', 'Dr. Sarah Chen'),
(4, 2023, 2, 'S', 'Y', 'MU081217', 'Dr. Ahmad Rahman'),
(4, 2024, 1, 'US', 'Y', 'MU081217', 'Dr. Ahmad Rahman'),
(6, 2024, 1, 'US', 'Y', 'MU092301', 'Dr. Sarah Chen'),
(6, 2024, 2, 'US', 'Y', 'MU092301', 'Dr. Sarah Chen');

-- Graduation Outcomes
INSERT INTO graduation_outcome (student_id, expected_end_date, actual_end_date, is_delayed, final_status) VALUES
(1, '2025-09-01', NULL, FALSE, 'Ongoing'),
(2, '2025-09-01', NULL, FALSE, 'Ongoing'),
(3, '2025-03-01', NULL, FALSE, 'Ongoing'),
(4, '2026-09-01', NULL, FALSE, 'Ongoing'),
(5, '2026-09-01', NULL, FALSE, 'Ongoing'),
(6, '2027-03-01', NULL, FALSE, 'Ongoing'),
(7, '2026-03-01', NULL, FALSE, 'Ongoing'),
(8, '2027-09-01', NULL, FALSE, 'Ongoing');

-- Examiners
INSERT INTO examiner (examiner_name, institution, is_external) VALUES
('Prof. Tan Ah Kow', 'University of Malaya', TRUE),
('Dr. Lee Wei Ming', 'NUS', TRUE),
('Prof. Yamamoto', 'University of Tokyo', TRUE);
