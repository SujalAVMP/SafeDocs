-- ============================================================
-- SafeDocs Module B: Benchmarking Queries
-- CS 432 - Databases | Assignment 2 | Track 1
-- IIT Gandhinagar | Semester II (2025-2026)
-- ============================================================
-- These queries mirror the Flask application's real routes and
-- the indexes created in setup.sql.
-- ============================================================

USE safedocs;

-- Query 1: Exact document title lookup (/api/documents?title=...)
EXPLAIN
SELECT d.DocumentID, d.Title, d.Description, d.FileSize,
       d.IsConfidential, d.IsActive, d.CreatedAt, d.UpdatedAt,
       m.Name AS UploaderName, f.FolderName, d.FolderID
FROM Document d
JOIN Member m ON d.UploadedBy = m.MemberID
JOIN Folder f ON d.FolderID   = f.FolderID
WHERE d.IsActive = TRUE
  AND d.Title = 'BENCH_DOC_01999'
ORDER BY d.CreatedAt DESC;

-- Query 2: Exact member-name lookup (/api/members?name=...)
EXPLAIN
SELECT m.MemberID, m.Name, m.Email, m.ContactNumber, m.Age,
       m.IsActive, m.CreatedAt, d.DeptName, r.RoleName
FROM Member m
JOIN Department d ON m.DepartmentID = d.DepartmentID
JOIN Role r       ON m.RoleID       = r.RoleID
WHERE m.Name = 'Benchmark User 2999'
ORDER BY m.MemberID;

-- Query 3: Portfolio recent activity (/portfolio/<member_id>)
EXPLAIN
SELECT recent.Action, recent.AccessTimestamp, doc.Title
FROM (
    SELECT DocumentID, Action, AccessTimestamp
    FROM AccessLog
    WHERE MemberID = 1
    ORDER BY AccessTimestamp DESC
    LIMIT 10
) AS recent
JOIN Document doc ON recent.DocumentID = doc.DocumentID
ORDER BY recent.AccessTimestamp DESC;

-- Query 4: Active folder listing (/api/folders)
EXPLAIN
SELECT FolderID, FolderName
FROM Folder
WHERE IsActive = TRUE
ORDER BY FolderName;

-- Query 5: Filtered security logs (/api/security-logs?session_valid=true)
EXPLAIN
SELECT sl.*, m.Name AS MemberName
FROM SecurityLog sl
LEFT JOIN Member m ON sl.MemberID = m.MemberID
WHERE sl.SessionValid = TRUE
ORDER BY sl.CreatedAt DESC
LIMIT 100;

-- ============================================================
-- Timing-based benchmarks (run these separately to measure)
-- ============================================================

-- Benchmark Query 1: Document by title
-- SET @start = NOW(6);
-- SELECT d.DocumentID, d.Title, d.Description, d.FileSize,
--        d.IsConfidential, d.IsActive, d.CreatedAt, d.UpdatedAt,
--        m.Name AS UploaderName, f.FolderName, d.FolderID
-- FROM Document d
-- JOIN Member m ON d.UploadedBy = m.MemberID
-- JOIN Folder f ON d.FolderID   = f.FolderID
-- WHERE d.IsActive = TRUE
--   AND d.Title = 'BENCH_DOC_01999'
-- ORDER BY d.CreatedAt DESC;
-- SELECT TIMESTAMPDIFF(MICROSECOND, @start, NOW(6)) AS execution_time_us;

-- Benchmark Query 2: Member by name
-- SET @start = NOW(6);
-- SELECT m.MemberID, m.Name, m.Email, m.ContactNumber, m.Age,
--        m.IsActive, m.CreatedAt, d.DeptName, r.RoleName
-- FROM Member m
-- JOIN Department d ON m.DepartmentID = d.DepartmentID
-- JOIN Role r       ON m.RoleID       = r.RoleID
-- WHERE m.Name = 'Benchmark User 2999'
-- ORDER BY m.MemberID;
-- SELECT TIMESTAMPDIFF(MICROSECOND, @start, NOW(6)) AS execution_time_us;

-- Benchmark Query 3: Portfolio recent activity
-- SET @start = NOW(6);
-- SELECT recent.Action, recent.AccessTimestamp, doc.Title
-- FROM (
--     SELECT DocumentID, Action, AccessTimestamp
--     FROM AccessLog
--     WHERE MemberID = 1
--     ORDER BY AccessTimestamp DESC
--     LIMIT 10
-- ) AS recent
-- JOIN Document doc ON recent.DocumentID = doc.DocumentID
-- ORDER BY recent.AccessTimestamp DESC;
-- SELECT TIMESTAMPDIFF(MICROSECOND, @start, NOW(6)) AS execution_time_us;

-- Benchmark Query 4: Active folder listing
-- SET @start = NOW(6);
-- SELECT FolderID, FolderName
-- FROM Folder
-- WHERE IsActive = TRUE
-- ORDER BY FolderName;
-- SELECT TIMESTAMPDIFF(MICROSECOND, @start, NOW(6)) AS execution_time_us;

-- Benchmark Query 5: Filtered security logs
-- SET @start = NOW(6);
-- SELECT sl.*, m.Name AS MemberName
-- FROM SecurityLog sl
-- LEFT JOIN Member m ON sl.MemberID = m.MemberID
-- WHERE sl.SessionValid = TRUE
-- ORDER BY sl.CreatedAt DESC
-- LIMIT 100;
-- SELECT TIMESTAMPDIFF(MICROSECOND, @start, NOW(6)) AS execution_time_us;

-- ============================================================
-- END OF BENCHMARK QUERIES
-- ============================================================
