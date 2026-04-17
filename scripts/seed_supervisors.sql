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
