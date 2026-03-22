-- ============================================================
-- SafeDocs Module B: Authentication & Security Setup
-- CS 432 - Databases | Assignment 2 | Track 1
-- IIT Gandhinagar | Semester II (2025-2026)
-- ============================================================

USE safedocs;

-- ============================================================
-- TABLE: UserLogin
-- Stores authentication credentials, separated from Member
-- to maintain clean separation of concerns.
-- ============================================================
CREATE TABLE IF NOT EXISTS UserLogin (
    LoginID      INT           PRIMARY KEY AUTO_INCREMENT,
    MemberID     INT           NOT NULL UNIQUE,
    Username     VARCHAR(50)   NOT NULL UNIQUE,
    PasswordHash VARCHAR(255)  NOT NULL,
    CreatedAt    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (MemberID) REFERENCES Member(MemberID)
        ON UPDATE CASCADE ON DELETE CASCADE
);

-- ============================================================
-- TABLE: SecurityLog
-- Tracks all API access for security auditing.
-- ============================================================
CREATE TABLE IF NOT EXISTS SecurityLog (
    LogID        INT           PRIMARY KEY AUTO_INCREMENT,
    MemberID     INT,
    Action       VARCHAR(100)  NOT NULL,
    TableName    VARCHAR(50),
    RecordID     INT,
    IPAddress    VARCHAR(45),
    SessionValid BOOLEAN       NOT NULL,
    Details      TEXT,
    CreatedAt    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (MemberID) REFERENCES Member(MemberID)
        ON UPDATE CASCADE ON DELETE SET NULL
);

-- ============================================================
-- SAMPLE UserLogin DATA
-- Passwords are hashed using SHA2-256 for simplicity.
-- ============================================================
INSERT IGNORE INTO UserLogin (MemberID, Username, PasswordHash) VALUES
(1,  'admin',   SHA2('admin123',   256)),
(2,  'priya',   SHA2('priya123',   256)),
(3,  'rohan',   SHA2('rohan123',   256)),
(4,  'ananya',  SHA2('ananya123',  256)),
(5,  'vikram',  SHA2('vikram123',  256)),
(6,  'sneha',   SHA2('sneha123',   256)),
(7,  'arjun',   SHA2('arjun123',   256)),
(8,  'kavya',   SHA2('kavya123',   256)),
(9,  'rahul',   SHA2('rahul123',   256)),
(10, 'diya',    SHA2('diya123',    256)),
(11, 'manish',  SHA2('manish123',  256)),
(12, 'neha',    SHA2('neha123',    256)),
(13, 'siddharth', SHA2('siddharth123', 256)),
(14, 'ishita',  SHA2('ishita123',  256)),
(15, 'aditya',  SHA2('aditya123',  256));

-- ============================================================
-- INDEXES for performance optimization (Module B - SubTask 4)
-- These indexes are aligned with the actual Flask routes:
--   /api/documents?title=...
--   /api/members?name=...
--   /portfolio/<member_id>
--   /api/folders
--   /api/security-logs?session_valid=true|false
-- ============================================================

-- Exact title lookup for document search/filter API
CREATE INDEX IF NOT EXISTS idx_document_title ON Document(Title);

-- Exact member-name lookup for admin member filtering API
CREATE INDEX IF NOT EXISTS idx_member_name ON Member(Name);

-- Recent activity on the portfolio page:
-- WHERE MemberID = ? ORDER BY AccessTimestamp DESC LIMIT 10
CREATE INDEX IF NOT EXISTS idx_accesslog_member_timestamp
    ON AccessLog(MemberID, AccessTimestamp);

-- Active folder listing ordered by name
CREATE INDEX IF NOT EXISTS idx_folder_active_name
    ON Folder(IsActive, FolderName);

-- Filtered security-log view ordered by newest first
CREATE INDEX IF NOT EXISTS idx_securitylog_session_created
    ON SecurityLog(SessionValid, CreatedAt);

-- UserLogin.Username is already UNIQUE, so MySQL maintains an index
-- for the login lookup automatically.

-- ============================================================
-- END OF SETUP
-- ============================================================
