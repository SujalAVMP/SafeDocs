-- ============================================================
-- SafeDocs: Secure PDF Management System
-- CS 432 - Databases | Assignment 1 | Track 1 | Statement 6
-- IIT Gandhinagar | Semester II (2025-2026)
-- ============================================================
-- Team Members:
--   Sujal Patel       (22110261)
--   Siddharth Doshi   (22110250)
--   Viraj Vekaria     (22110287)
--   Nishit Mistry     (22110172)
--   Rutvi Shah        (22110227)
-- ============================================================
-- GitHub: https://github.com/SujalAVMP/SafeDocs
-- ============================================================

DROP DATABASE IF EXISTS safedocs;
CREATE DATABASE safedocs;
USE safedocs;

-- ============================================================
-- TABLE 1: Department
-- Organizational departments that members belong to.
-- ============================================================
CREATE TABLE Department (
    DepartmentID    INT             PRIMARY KEY AUTO_INCREMENT,
    DeptName        VARCHAR(100)    NOT NULL,
    Description     VARCHAR(255),
    CreatedAt       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_dept_name UNIQUE (DeptName)
);

-- ============================================================
-- TABLE 2: Role
-- Defines user roles and their system-wide capabilities.
-- ============================================================
CREATE TABLE Role (
    RoleID          INT             PRIMARY KEY AUTO_INCREMENT,
    RoleName        VARCHAR(50)     NOT NULL,
    Description     VARCHAR(255),
    CanUpload       BOOLEAN         NOT NULL DEFAULT FALSE,
    CanDelete       BOOLEAN         NOT NULL DEFAULT FALSE,
    CanShare        BOOLEAN         NOT NULL DEFAULT FALSE,
    CanManageUsers  BOOLEAN         NOT NULL DEFAULT FALSE,

    CONSTRAINT uq_role_name UNIQUE (RoleName)
);

-- ============================================================
-- TABLE 3: Member
-- System users. Required table per assignment spec.
-- ============================================================
CREATE TABLE Member (
    MemberID        INT             PRIMARY KEY AUTO_INCREMENT,
    Name            VARCHAR(100)    NOT NULL,
    Image           VARCHAR(255)    DEFAULT NULL,
    Age             INT,
    Email           VARCHAR(150)    NOT NULL,
    ContactNumber   VARCHAR(15)     NOT NULL,
    DepartmentID    INT             NOT NULL,
    RoleID          INT             NOT NULL,
    PasswordHash    VARCHAR(255)    NOT NULL,
    IsActive        BOOLEAN         NOT NULL DEFAULT TRUE,
    CreatedAt       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_member_email UNIQUE (Email),
    CONSTRAINT uq_member_contact UNIQUE (ContactNumber),
    CONSTRAINT chk_member_age CHECK (Age >= 18),
    CONSTRAINT fk_member_dept FOREIGN KEY (DepartmentID)
        REFERENCES Department(DepartmentID)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_member_role FOREIGN KEY (RoleID)
        REFERENCES Role(RoleID)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

-- ============================================================
-- TABLE 4: Folder
-- Hierarchical folder structure for organizing documents.
-- Supports self-referencing parent-child relationship.
-- ============================================================
CREATE TABLE Folder (
    FolderID        INT             PRIMARY KEY AUTO_INCREMENT,
    FolderName      VARCHAR(100)    NOT NULL,
    Description     VARCHAR(255),
    ParentFolderID  INT             DEFAULT NULL,
    CreatedBy       INT             NOT NULL,
    DepartmentID    INT             DEFAULT NULL,
    CreatedAt       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    IsActive        BOOLEAN         NOT NULL DEFAULT TRUE,

    CONSTRAINT fk_folder_parent FOREIGN KEY (ParentFolderID)
        REFERENCES Folder(FolderID)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_folder_creator FOREIGN KEY (CreatedBy)
        REFERENCES Member(MemberID)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_folder_dept FOREIGN KEY (DepartmentID)
        REFERENCES Department(DepartmentID)
        ON UPDATE CASCADE ON DELETE SET NULL
);

-- ============================================================
-- TABLE 5: Document
-- Core table storing metadata for each PDF document.
-- ============================================================
CREATE TABLE Document (
    DocumentID      INT             PRIMARY KEY AUTO_INCREMENT,
    Title           VARCHAR(200)    NOT NULL,
    Description     VARCHAR(500),
    FilePath        VARCHAR(500)    NOT NULL,
    FileSize        BIGINT          NOT NULL,
    MimeType        VARCHAR(50)     NOT NULL DEFAULT 'application/pdf',
    UploadedBy      INT             NOT NULL,
    FolderID        INT             NOT NULL,
    IsConfidential  BOOLEAN         NOT NULL DEFAULT FALSE,
    IsActive        BOOLEAN         NOT NULL DEFAULT TRUE,
    CreatedAt       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UpdatedAt       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT chk_doc_filesize CHECK (FileSize > 0),
    CONSTRAINT fk_doc_uploader FOREIGN KEY (UploadedBy)
        REFERENCES Member(MemberID)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_doc_folder FOREIGN KEY (FolderID)
        REFERENCES Folder(FolderID)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

-- ============================================================
-- TABLE 6: DocumentVersion
-- Tracks version history for each document.
-- ============================================================
CREATE TABLE DocumentVersion (
    DocumentID      INT             NOT NULL,
    VersionNumber   INT             NOT NULL,
    FilePath        VARCHAR(500)    NOT NULL,
    FileSize        BIGINT          NOT NULL,
    UploadedBy      INT             NOT NULL,
    ChangeNote      VARCHAR(300),
    CreatedAt       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (DocumentID, VersionNumber),
    CONSTRAINT chk_ver_number CHECK (VersionNumber > 0),
    CONSTRAINT chk_ver_filesize CHECK (FileSize > 0),
    CONSTRAINT fk_ver_document FOREIGN KEY (DocumentID)
        REFERENCES Document(DocumentID)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_ver_uploader FOREIGN KEY (UploadedBy)
        REFERENCES Member(MemberID)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

-- ============================================================
-- TABLE 7: Tag
-- Labels for categorizing documents.
-- ============================================================
CREATE TABLE Tag (
    TagID           INT             PRIMARY KEY AUTO_INCREMENT,
    TagName         VARCHAR(50)     NOT NULL,
    Description     VARCHAR(255),
    CreatedAt       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_tag_name UNIQUE (TagName)
);

-- ============================================================
-- TABLE 8: DocumentTag
-- Many-to-many junction between Document and Tag.
-- ============================================================
CREATE TABLE DocumentTag (
    DocumentID      INT             NOT NULL,
    TagID           INT             NOT NULL,
    AssignedAt      DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (DocumentID, TagID),
    CONSTRAINT fk_doctag_document FOREIGN KEY (DocumentID)
        REFERENCES Document(DocumentID)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_doctag_tag FOREIGN KEY (TagID)
        REFERENCES Tag(TagID)
        ON UPDATE CASCADE ON DELETE CASCADE
);

-- ============================================================
-- TABLE 9: Permission
-- Fine-grained per-document access control for members.
-- AccessLevel: 'VIEW', 'EDIT', 'DELETE', 'ADMIN'
-- ============================================================
CREATE TABLE Permission (
    PermissionID    INT             PRIMARY KEY AUTO_INCREMENT,
    DocumentID      INT             NOT NULL,
    MemberID        INT             NOT NULL,
    AccessLevel     ENUM('VIEW','EDIT','DELETE','ADMIN') NOT NULL,
    GrantedBy       INT             NOT NULL,
    GrantedAt       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ExpiresAt       DATETIME        DEFAULT NULL,

    CONSTRAINT chk_perm_expiry CHECK (ExpiresAt IS NULL OR ExpiresAt > GrantedAt),
    CONSTRAINT uq_perm_doc_member_level UNIQUE (DocumentID, MemberID, AccessLevel),
    CONSTRAINT fk_perm_document FOREIGN KEY (DocumentID)
        REFERENCES Document(DocumentID)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_perm_member FOREIGN KEY (MemberID)
        REFERENCES Member(MemberID)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_perm_granter FOREIGN KEY (GrantedBy)
        REFERENCES Member(MemberID)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

-- ============================================================
-- TABLE 10: AccessLog
-- Immutable audit trail of all document interactions.
-- ============================================================
CREATE TABLE AccessLog (
    LogID           INT             PRIMARY KEY AUTO_INCREMENT,
    DocumentID      INT             NOT NULL,
    MemberID        INT             NOT NULL,
    Action          ENUM('VIEW','DOWNLOAD','UPLOAD','EDIT','DELETE','SHARE','PERMISSION_CHANGE') NOT NULL,
    IPAddress       VARCHAR(45),
    UserAgent       VARCHAR(255),
    AccessTimestamp DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_log_document FOREIGN KEY (DocumentID)
        REFERENCES Document(DocumentID)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_log_member FOREIGN KEY (MemberID)
        REFERENCES Member(MemberID)
        ON UPDATE CASCADE ON DELETE CASCADE
);

-- ============================================================
-- TABLE 11: SharedLink
-- Secure, time-limited links for external document sharing.
-- ============================================================
CREATE TABLE SharedLink (
    LinkID          INT             PRIMARY KEY AUTO_INCREMENT,
    DocumentID      INT             NOT NULL,
    SharedBy        INT             NOT NULL,
    Token           VARCHAR(128)    NOT NULL,
    ExpiresAt       DATETIME        NOT NULL,
    MaxDownloads    INT             NOT NULL DEFAULT 5,
    DownloadCount   INT             NOT NULL DEFAULT 0,
    IsActive        BOOLEAN         NOT NULL DEFAULT TRUE,
    CreatedAt       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_shared_token UNIQUE (Token),
    CONSTRAINT chk_link_expiry CHECK (ExpiresAt > CreatedAt),
    CONSTRAINT chk_link_max_dl CHECK (MaxDownloads > 0),
    CONSTRAINT chk_link_dl_count CHECK (DownloadCount >= 0 AND DownloadCount <= MaxDownloads),
    CONSTRAINT fk_link_document FOREIGN KEY (DocumentID)
        REFERENCES Document(DocumentID)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_link_sharer FOREIGN KEY (SharedBy)
        REFERENCES Member(MemberID)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

-- ============================================================
-- TABLE 12: Notification
-- Alerts for document shares, permission changes, updates.
-- ============================================================
CREATE TABLE Notification (
    NotificationID  INT             PRIMARY KEY AUTO_INCREMENT,
    MemberID        INT             NOT NULL,
    DocumentID      INT             DEFAULT NULL,
    Message         VARCHAR(500)    NOT NULL,
    NotificationType ENUM('SHARE','PERMISSION','UPDATE','UPLOAD','DELETE','SYSTEM') NOT NULL,
    IsRead          BOOLEAN         NOT NULL DEFAULT FALSE,
    CreatedAt       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_notif_member FOREIGN KEY (MemberID)
        REFERENCES Member(MemberID)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_notif_document FOREIGN KEY (DocumentID)
        REFERENCES Document(DocumentID)
        ON UPDATE CASCADE ON DELETE SET NULL
);

-- ============================================================
-- INDEXES for performance
-- ============================================================
CREATE INDEX idx_member_dept ON Member(DepartmentID);
CREATE INDEX idx_member_role ON Member(RoleID);
CREATE INDEX idx_document_folder ON Document(FolderID);
CREATE INDEX idx_document_uploader ON Document(UploadedBy);
CREATE INDEX idx_version_document ON DocumentVersion(DocumentID);
CREATE INDEX idx_permission_document ON Permission(DocumentID);
CREATE INDEX idx_permission_member ON Permission(MemberID);
CREATE INDEX idx_accesslog_document ON AccessLog(DocumentID);
CREATE INDEX idx_accesslog_member ON AccessLog(MemberID);
CREATE INDEX idx_accesslog_timestamp ON AccessLog(AccessTimestamp);
CREATE INDEX idx_sharedlink_document ON SharedLink(DocumentID);
CREATE INDEX idx_notification_member ON Notification(MemberID);

-- ============================================================
-- SAMPLE DATA
-- ============================================================

-- -----------------------------------------------------------
-- Department (15 rows)
-- -----------------------------------------------------------
INSERT INTO Department (DeptName, Description, CreatedAt) VALUES
('Computer Science',     'Department of Computer Science and Engineering',    '2025-01-10 09:00:00'),
('Electrical Engineering','Department of Electrical Engineering',             '2025-01-10 09:00:00'),
('Mechanical Engineering','Department of Mechanical Engineering',             '2025-01-10 09:00:00'),
('Civil Engineering',    'Department of Civil Engineering',                   '2025-01-10 09:00:00'),
('Chemical Engineering', 'Department of Chemical Engineering',                '2025-01-10 09:00:00'),
('Mathematics',          'Department of Mathematics',                         '2025-01-10 09:00:00'),
('Physics',              'Department of Physics',                             '2025-01-10 09:00:00'),
('Chemistry',            'Department of Chemistry',                           '2025-01-10 09:00:00'),
('Humanities',           'Department of Humanities and Social Sciences',      '2025-01-10 09:00:00'),
('Biology',              'Department of Biological Engineering',              '2025-01-10 09:00:00'),
('Management',           'School of Management',                              '2025-01-10 09:00:00'),
('Design',               'Discipline of Design',                              '2025-01-10 09:00:00'),
('Earth Sciences',       'Department of Earth Sciences',                      '2025-01-10 09:00:00'),
('Materials Science',    'Department of Materials Science and Engineering',   '2025-01-10 09:00:00'),
('Administration',       'Central Administrative Office',                     '2025-01-10 09:00:00');

-- -----------------------------------------------------------
-- Role (5 rows)
-- -----------------------------------------------------------
INSERT INTO Role (RoleName, Description, CanUpload, CanDelete, CanShare, CanManageUsers) VALUES
('Admin',       'Full system administrator with all privileges',        TRUE,  TRUE,  TRUE,  TRUE),
('Manager',     'Department manager with upload, delete, share access', TRUE,  TRUE,  TRUE,  FALSE),
('Editor',      'Can upload and edit documents',                        TRUE,  FALSE, TRUE,  FALSE),
('Viewer',      'Read-only access to permitted documents',              FALSE, FALSE, FALSE, FALSE),
('Auditor',     'Read-only access with audit log visibility',           FALSE, FALSE, FALSE, FALSE);

-- -----------------------------------------------------------
-- Member (20 rows)
-- -----------------------------------------------------------
INSERT INTO Member (Name, Image, Age, Email, ContactNumber, DepartmentID, RoleID, PasswordHash, IsActive, CreatedAt) VALUES
('Aarav Sharma',     '/img/aarav.jpg',     35, 'aarav.sharma@iitgn.ac.in',     '9876543210', 1,  1, '$2b$12$aaravhashxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', TRUE,  '2025-01-15 10:00:00'),
('Priya Mehta',      '/img/priya.jpg',     29, 'priya.mehta@iitgn.ac.in',      '9876543211', 1,  2, '$2b$12$priyahashxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', TRUE,  '2025-01-15 10:05:00'),
('Rohan Patel',      '/img/rohan.jpg',     32, 'rohan.patel@iitgn.ac.in',      '9876543212', 2,  2, '$2b$12$rohanhashxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', TRUE,  '2025-01-15 10:10:00'),
('Ananya Iyer',      '/img/ananya.jpg',    27, 'ananya.iyer@iitgn.ac.in',      '9876543213', 3,  3, '$2b$12$ananyahashxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', TRUE,  '2025-01-16 09:00:00'),
('Vikram Singh',     '/img/vikram.jpg',    40, 'vikram.singh@iitgn.ac.in',     '9876543214', 15, 1, '$2b$12$vikramhashxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', TRUE,  '2025-01-16 09:05:00'),
('Sneha Reddy',      '/img/sneha.jpg',     26, 'sneha.reddy@iitgn.ac.in',      '9876543215', 4,  3, '$2b$12$snehahashxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', TRUE,  '2025-01-16 09:10:00'),
('Arjun Nair',       '/img/arjun.jpg',     31, 'arjun.nair@iitgn.ac.in',       '9876543216', 5,  3, '$2b$12$arjunhashxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', TRUE,  '2025-01-17 08:30:00'),
('Kavya Joshi',      '/img/kavya.jpg',     28, 'kavya.joshi@iitgn.ac.in',      '9876543217', 6,  4, '$2b$12$kavyahashxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', TRUE,  '2025-01-17 08:35:00'),
('Rahul Gupta',      '/img/rahul.jpg',     33, 'rahul.gupta@iitgn.ac.in',      '9876543218', 7,  4, '$2b$12$rahulhashxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', TRUE,  '2025-01-17 08:40:00'),
('Diya Verma',       '/img/diya.jpg',      24, 'diya.verma@iitgn.ac.in',       '9876543219', 8,  4, '$2b$12$diyahashxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', TRUE,  '2025-01-18 11:00:00'),
('Manish Kapoor',    '/img/manish.jpg',    45, 'manish.kapoor@iitgn.ac.in',    '9876543220', 9,  2, '$2b$12$manishhashxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', TRUE,  '2025-01-18 11:05:00'),
('Neha Agarwal',     '/img/neha.jpg',      30, 'neha.agarwal@iitgn.ac.in',     '9876543221', 10, 3, '$2b$12$nehahashxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', TRUE,  '2025-01-18 11:10:00'),
('Siddharth Rao',    '/img/siddharth.jpg', 36, 'siddharth.rao@iitgn.ac.in',    '9876543222', 11, 2, '$2b$12$siddharthhashxxxxxxxxxxxxxxxxxxxxxxxxxxxx', TRUE,  '2025-01-19 07:45:00'),
('Ishita Bansal',    '/img/ishita.jpg',    25, 'ishita.bansal@iitgn.ac.in',    '9876543223', 12, 3, '$2b$12$ishitahashxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', TRUE,  '2025-01-19 07:50:00'),
('Aditya Kulkarni',  '/img/aditya.jpg',    38, 'aditya.kulkarni@iitgn.ac.in',  '9876543224', 13, 5, '$2b$12$adityahashxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', TRUE,  '2025-01-19 07:55:00'),
('Meera Deshmukh',   '/img/meera.jpg',     29, 'meera.deshmukh@iitgn.ac.in',   '9876543225', 14, 3, '$2b$12$meerahashxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', TRUE,  '2025-01-20 14:00:00'),
('Karan Malhotra',   '/img/karan.jpg',     34, 'karan.malhotra@iitgn.ac.in',   '9876543226', 1,  3, '$2b$12$karanhashxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', TRUE,  '2025-01-20 14:05:00'),
('Pooja Tiwari',     '/img/pooja.jpg',     27, 'pooja.tiwari@iitgn.ac.in',     '9876543227', 2,  4, '$2b$12$poojahashxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', TRUE,  '2025-01-20 14:10:00'),
('Nikhil Saxena',    '/img/nikhil.jpg',    41, 'nikhil.saxena@iitgn.ac.in',    '9876543228', 15, 2, '$2b$12$nikhilhashxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', TRUE,  '2025-01-21 09:00:00'),
('Ritu Chauhan',     '/img/ritu.jpg',      23, 'ritu.chauhan@iitgn.ac.in',     '9876543229', 3,  4, '$2b$12$rituhashxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx', FALSE, '2025-01-21 09:05:00');

-- -----------------------------------------------------------
-- Folder (15 rows)
-- -----------------------------------------------------------
INSERT INTO Folder (FolderName, Description, ParentFolderID, CreatedBy, DepartmentID, CreatedAt, IsActive) VALUES
('CS Department Docs',         'Root folder for CS department',                NULL, 1,  1,    '2025-01-20 10:00:00', TRUE),
('EE Department Docs',         'Root folder for EE department',                NULL, 3,  2,    '2025-01-20 10:05:00', TRUE),
('ME Department Docs',         'Root folder for ME department',                NULL, 4,  3,    '2025-01-20 10:10:00', TRUE),
('Admin Records',              'Central administrative records',               NULL, 5,  15,   '2025-01-20 10:15:00', TRUE),
('Exam Papers',                'Previous year exam papers for CS',             1,    1,  1,    '2025-01-21 08:00:00', TRUE),
('Research Papers',            'Published research from CS faculty',           1,    2,  1,    '2025-01-21 08:05:00', TRUE),
('Faculty Meeting Minutes',    'Minutes of CS department meetings',            1,    2,  1,    '2025-01-21 08:10:00', TRUE),
('Lab Manuals',                'EE lab experiment manuals',                    2,    3,  2,    '2025-01-22 09:00:00', TRUE),
('Project Reports',            'Student project reports for ME',               3,    4,  3,    '2025-01-22 09:05:00', TRUE),
('HR Policies',                'Human resource policy documents',              4,    5,  15,   '2025-01-22 09:10:00', TRUE),
('Financial Records',          'Budget and expenditure reports',               4,    5,  15,   '2025-01-22 09:15:00', TRUE),
('Shared Resources',           'Cross-department shared documents',            NULL, 1,  NULL, '2025-01-23 10:00:00', TRUE),
('Templates',                  'Document templates and forms',                 12,   5,  NULL, '2025-01-23 10:05:00', TRUE),
('Archived',                   'Old documents retained for records',           NULL, 5,  NULL, '2025-01-23 10:10:00', TRUE),
('CE Department Docs',         'Root folder for Civil Engineering',            NULL, 6,  4,    '2025-01-24 11:00:00', TRUE);

-- -----------------------------------------------------------
-- Document (20 rows)
-- -----------------------------------------------------------
INSERT INTO Document (Title, Description, FilePath, FileSize, MimeType, UploadedBy, FolderID, IsConfidential, IsActive, CreatedAt, UpdatedAt) VALUES
('CS432 Database Syllabus',         'Course syllabus for Databases',                        '/docs/cs432_syllabus.pdf',          245000,   'application/pdf', 1,  5,  FALSE, TRUE,  '2025-01-25 10:00:00', '2025-01-25 10:00:00'),
('ML Research Paper - CNN',         'Convolutional Neural Networks survey paper',            '/docs/cnn_survey.pdf',              1520000,  'application/pdf', 2,  6,  FALSE, TRUE,  '2025-01-25 10:30:00', '2025-01-25 10:30:00'),
('Faculty Meeting Jan 2025',        'Minutes from January faculty meeting',                 '/docs/faculty_jan2025.pdf',         98000,    'application/pdf', 2,  7,  TRUE,  TRUE,  '2025-01-26 09:00:00', '2025-01-26 09:00:00'),
('EE Lab Manual - Circuits',        'Basic electrical circuits lab manual',                 '/docs/ee_circuits_lab.pdf',         3200000,  'application/pdf', 3,  8,  FALSE, TRUE,  '2025-01-26 11:00:00', '2025-01-26 11:00:00'),
('ME Final Year Project Report',    'Thermal analysis of heat exchangers',                  '/docs/me_project_thermal.pdf',      5400000,  'application/pdf', 4,  9,  FALSE, TRUE,  '2025-01-27 08:00:00', '2025-01-27 08:00:00'),
('Leave Policy 2025',               'Updated leave policy for faculty and staff',           '/docs/leave_policy_2025.pdf',       150000,   'application/pdf', 5,  10, FALSE, TRUE,  '2025-01-27 09:00:00', '2025-02-01 14:00:00'),
('Annual Budget Report FY25',       'Detailed budget allocation and expenditure report',    '/docs/budget_fy25.pdf',             780000,   'application/pdf', 5,  11, TRUE,  TRUE,  '2025-01-28 10:00:00', '2025-01-28 10:00:00'),
('NDA Template',                    'Non-disclosure agreement template',                    '/docs/nda_template.pdf',            65000,    'application/pdf', 5,  13, FALSE, TRUE,  '2025-01-28 11:00:00', '2025-01-28 11:00:00'),
('Research Grant Proposal',         'SERB grant proposal for AI in healthcare',             '/docs/serb_grant_ai.pdf',           920000,   'application/pdf', 2,  6,  TRUE,  TRUE,  '2025-01-29 07:30:00', '2025-02-05 16:00:00'),
('CS432 Midterm Paper 2024',        'Previous year midterm examination',                    '/docs/cs432_mid2024.pdf',           180000,   'application/pdf', 1,  5,  TRUE,  TRUE,  '2025-01-29 08:00:00', '2025-01-29 08:00:00'),
('EE Signal Processing Notes',     'Lecture notes on DSP fundamentals',                    '/docs/ee_dsp_notes.pdf',            2100000,  'application/pdf', 3,  8,  FALSE, TRUE,  '2025-01-30 09:00:00', '2025-01-30 09:00:00'),
('Student Handbook 2025',           'Comprehensive guide for incoming students',            '/docs/student_handbook.pdf',        4500000,  'application/pdf', 5,  12, FALSE, TRUE,  '2025-01-30 10:00:00', '2025-01-30 10:00:00'),
('CE Structural Analysis Report',  'Analysis of RCC beam designs',                         '/docs/ce_structural.pdf',           1800000,  'application/pdf', 6,  15, FALSE, TRUE,  '2025-01-31 08:00:00', '2025-01-31 08:00:00'),
('Chemistry Lab Safety Manual',    'Safety protocols for chemistry laboratories',           '/docs/chem_safety.pdf',             560000,   'application/pdf', 12, 12, FALSE, TRUE,  '2025-01-31 09:00:00', '2025-01-31 09:00:00'),
('Placement Brochure 2025',        'Campus placement statistics and company profiles',     '/docs/placement_2025.pdf',          8900000,  'application/pdf', 13, 12, FALSE, TRUE,  '2025-02-01 10:00:00', '2025-02-01 10:00:00'),
('IP Policy Document',             'Intellectual property guidelines for research',         '/docs/ip_policy.pdf',               310000,   'application/pdf', 5,  10, TRUE,  TRUE,  '2025-02-01 11:00:00', '2025-02-01 11:00:00'),
('Design Thinking Workshop',       'Materials from design thinking workshop',               '/docs/design_workshop.pdf',         2700000,  'application/pdf', 14, 12, FALSE, TRUE,  '2025-02-02 08:00:00', '2025-02-02 08:00:00'),
('PhD Thesis Guidelines',          'Formatting and submission guidelines for PhD thesis',  '/docs/phd_guidelines.pdf',          420000,   'application/pdf', 11, 12, FALSE, TRUE,  '2025-02-02 09:00:00', '2025-02-02 09:00:00'),
('Archived Syllabus CS 2020',      'Old CS syllabus for reference',                        '/docs/cs_syllabus_2020.pdf',        200000,   'application/pdf', 1,  14, FALSE, TRUE,  '2025-02-03 07:00:00', '2025-02-03 07:00:00'),
('Travel Reimbursement Form',      'Editable form for travel expense claims',              '/docs/travel_reimburse.pdf',        75000,    'application/pdf', 19, 13, FALSE, TRUE,  '2025-02-03 08:00:00', '2025-02-03 08:00:00');

-- -----------------------------------------------------------
-- DocumentVersion (15 rows)
-- -----------------------------------------------------------
INSERT INTO DocumentVersion (DocumentID, VersionNumber, FilePath, FileSize, UploadedBy, ChangeNote, CreatedAt) VALUES
(1,  1, '/docs/versions/cs432_syllabus_v1.pdf',     230000,  1,  'Initial upload',                               '2025-01-25 10:00:00'),
(1,  2, '/docs/versions/cs432_syllabus_v2.pdf',     245000,  1,  'Added project component details',              '2025-02-01 12:00:00'),
(2,  1, '/docs/versions/cnn_survey_v1.pdf',         1500000, 2,  'Initial draft',                                '2025-01-25 10:30:00'),
(2,  2, '/docs/versions/cnn_survey_v2.pdf',         1520000, 2,  'Added references and conclusion section',      '2025-02-03 15:00:00'),
(4,  1, '/docs/versions/ee_circuits_lab_v1.pdf',    3100000, 3,  'First version of lab manual',                  '2025-01-26 11:00:00'),
(4,  2, '/docs/versions/ee_circuits_lab_v2.pdf',    3200000, 3,  'Added experiment 7 and 8',                     '2025-02-04 10:00:00'),
(6,  1, '/docs/versions/leave_policy_v1.pdf',       140000,  5,  'Original leave policy document',               '2025-01-27 09:00:00'),
(6,  2, '/docs/versions/leave_policy_v2.pdf',       150000,  5,  'Updated maternity and paternity leave clauses','2025-02-01 14:00:00'),
(9,  1, '/docs/versions/serb_grant_v1.pdf',         850000,  2,  'First draft of grant proposal',                '2025-01-29 07:30:00'),
(9,  2, '/docs/versions/serb_grant_v2.pdf',         900000,  2,  'Revised budget estimates',                     '2025-02-02 09:00:00'),
(9,  3, '/docs/versions/serb_grant_v3.pdf',         920000,  2,  'Final version with co-PI details',             '2025-02-05 16:00:00'),
(12, 1, '/docs/versions/student_handbook_v1.pdf',   4200000, 5,  'Initial handbook for 2025 batch',              '2025-01-30 10:00:00'),
(12, 2, '/docs/versions/student_handbook_v2.pdf',   4500000, 5,  'Added hostel and mess information',            '2025-02-06 08:00:00'),
(15, 1, '/docs/versions/placement_2025_v1.pdf',     8500000, 13, 'Draft brochure',                               '2025-02-01 10:00:00'),
(15, 2, '/docs/versions/placement_2025_v2.pdf',     8900000, 13, 'Added final placement statistics',             '2025-02-07 12:00:00');

-- -----------------------------------------------------------
-- Tag (12 rows)
-- -----------------------------------------------------------
INSERT INTO Tag (TagName, Description, CreatedAt) VALUES
('Confidential',   'Restricted access documents',                        '2025-01-20 08:00:00'),
('Syllabus',       'Course syllabi and curriculum documents',            '2025-01-20 08:01:00'),
('Research',       'Research papers, proposals, and publications',       '2025-01-20 08:02:00'),
('Policy',         'Institutional and department policy documents',      '2025-01-20 08:03:00'),
('Lab Manual',     'Laboratory experiment manuals',                      '2025-01-20 08:04:00'),
('Report',         'Project reports and analysis documents',             '2025-01-20 08:05:00'),
('Template',       'Reusable document templates and forms',              '2025-01-20 08:06:00'),
('Meeting Notes',  'Minutes and notes from meetings',                    '2025-01-20 08:07:00'),
('Exam',           'Examination papers and answer keys',                 '2025-01-20 08:08:00'),
('Finance',        'Budget, expenditure, and financial documents',       '2025-01-20 08:09:00'),
('Student',        'Student-related documents and guides',               '2025-01-20 08:10:00'),
('Archived',       'Old documents kept for historical reference',        '2025-01-20 08:11:00');

-- -----------------------------------------------------------
-- DocumentTag (20 rows)
-- -----------------------------------------------------------
INSERT INTO DocumentTag (DocumentID, TagID, AssignedAt) VALUES
(1,  2,  '2025-01-25 10:01:00'),
(1,  9,  '2025-01-25 10:01:00'),
(2,  3,  '2025-01-25 10:31:00'),
(3,  8,  '2025-01-26 09:01:00'),
(3,  1,  '2025-01-26 09:01:00'),
(4,  5,  '2025-01-26 11:01:00'),
(5,  6,  '2025-01-27 08:01:00'),
(6,  4,  '2025-01-27 09:01:00'),
(7,  10, '2025-01-28 10:01:00'),
(7,  1,  '2025-01-28 10:01:00'),
(8,  7,  '2025-01-28 11:01:00'),
(9,  3,  '2025-01-29 07:31:00'),
(9,  1,  '2025-01-29 07:31:00'),
(10, 9,  '2025-01-29 08:01:00'),
(10, 1,  '2025-01-29 08:01:00'),
(11, 5,  '2025-01-30 09:01:00'),
(12, 11, '2025-01-30 10:01:00'),
(13, 6,  '2025-01-31 08:01:00'),
(14, 5,  '2025-01-31 09:01:00'),
(19, 12, '2025-02-03 07:01:00');

-- -----------------------------------------------------------
-- Permission (20 rows)
-- -----------------------------------------------------------
INSERT INTO Permission (DocumentID, MemberID, AccessLevel, GrantedBy, GrantedAt, ExpiresAt) VALUES
(1,  1,  'ADMIN',  1,  '2025-01-25 10:00:00', NULL),
(1,  2,  'EDIT',   1,  '2025-01-25 10:05:00', NULL),
(1,  8,  'VIEW',   1,  '2025-01-25 10:10:00', '2025-06-30 23:59:59'),
(2,  2,  'ADMIN',  2,  '2025-01-25 10:30:00', NULL),
(2,  17, 'VIEW',   2,  '2025-01-26 08:00:00', NULL),
(3,  2,  'ADMIN',  1,  '2025-01-26 09:00:00', NULL),
(3,  1,  'VIEW',   2,  '2025-01-26 09:05:00', NULL),
(4,  3,  'ADMIN',  3,  '2025-01-26 11:00:00', NULL),
(4,  18, 'VIEW',   3,  '2025-01-27 08:00:00', '2025-07-31 23:59:59'),
(5,  4,  'ADMIN',  4,  '2025-01-27 08:00:00', NULL),
(6,  5,  'ADMIN',  5,  '2025-01-27 09:00:00', NULL),
(6,  19, 'EDIT',   5,  '2025-01-28 08:00:00', NULL),
(7,  5,  'ADMIN',  5,  '2025-01-28 10:00:00', NULL),
(7,  15, 'VIEW',   5,  '2025-01-28 10:30:00', '2025-12-31 23:59:59'),
(9,  2,  'ADMIN',  2,  '2025-01-29 07:30:00', NULL),
(9,  1,  'EDIT',   2,  '2025-01-29 08:00:00', NULL),
(10, 1,  'ADMIN',  1,  '2025-01-29 08:00:00', NULL),
(12, 5,  'ADMIN',  5,  '2025-01-30 10:00:00', NULL),
(12, 8,  'VIEW',   5,  '2025-01-31 09:00:00', NULL),
(15, 13, 'ADMIN',  13, '2025-02-01 10:00:00', NULL);

-- -----------------------------------------------------------
-- AccessLog (20 rows)
-- -----------------------------------------------------------
INSERT INTO AccessLog (DocumentID, MemberID, Action, IPAddress, UserAgent, AccessTimestamp) VALUES
(1,  1,  'UPLOAD',   '10.0.1.10',  'Mozilla/5.0 (Windows NT 10.0)',   '2025-01-25 10:00:00'),
(1,  2,  'VIEW',     '10.0.1.11',  'Mozilla/5.0 (Macintosh)',         '2025-01-25 14:00:00'),
(2,  2,  'UPLOAD',   '10.0.1.11',  'Mozilla/5.0 (Macintosh)',         '2025-01-25 10:30:00'),
(3,  2,  'UPLOAD',   '10.0.1.11',  'Mozilla/5.0 (Macintosh)',         '2025-01-26 09:00:00'),
(3,  1,  'VIEW',     '10.0.1.10',  'Mozilla/5.0 (Windows NT 10.0)',   '2025-01-26 15:00:00'),
(4,  3,  'UPLOAD',   '10.0.2.20',  'Mozilla/5.0 (Linux; Ubuntu)',     '2025-01-26 11:00:00'),
(6,  5,  'UPLOAD',   '10.0.3.30',  'Mozilla/5.0 (Windows NT 10.0)',   '2025-01-27 09:00:00'),
(6,  5,  'EDIT',     '10.0.3.30',  'Mozilla/5.0 (Windows NT 10.0)',   '2025-02-01 14:00:00'),
(7,  5,  'UPLOAD',   '10.0.3.30',  'Mozilla/5.0 (Windows NT 10.0)',   '2025-01-28 10:00:00'),
(7,  15, 'VIEW',     '10.0.4.40',  'Mozilla/5.0 (X11; Linux)',        '2025-02-02 11:00:00'),
(9,  2,  'UPLOAD',   '10.0.1.11',  'Mozilla/5.0 (Macintosh)',         '2025-01-29 07:30:00'),
(9,  1,  'VIEW',     '10.0.1.10',  'Mozilla/5.0 (Windows NT 10.0)',   '2025-02-01 08:00:00'),
(9,  2,  'EDIT',     '10.0.1.11',  'Mozilla/5.0 (Macintosh)',         '2025-02-05 16:00:00'),
(10, 1,  'UPLOAD',   '10.0.1.10',  'Mozilla/5.0 (Windows NT 10.0)',   '2025-01-29 08:00:00'),
(12, 5,  'UPLOAD',   '10.0.3.30',  'Mozilla/5.0 (Windows NT 10.0)',   '2025-01-30 10:00:00'),
(12, 8,  'VIEW',     '10.0.5.50',  'Mozilla/5.0 (Macintosh)',         '2025-02-03 13:00:00'),
(12, 8,  'DOWNLOAD', '10.0.5.50',  'Mozilla/5.0 (Macintosh)',         '2025-02-03 13:05:00'),
(1,  1,  'SHARE',    '10.0.1.10',  'Mozilla/5.0 (Windows NT 10.0)',   '2025-02-04 09:00:00'),
(15, 13, 'UPLOAD',   '10.0.6.60',  'Mozilla/5.0 (Windows NT 10.0)',   '2025-02-01 10:00:00'),
(6,  19, 'VIEW',     '10.0.7.70',  'Mozilla/5.0 (X11; Linux)',        '2025-02-06 10:30:00');

-- -----------------------------------------------------------
-- SharedLink (12 rows)
-- -----------------------------------------------------------
INSERT INTO SharedLink (DocumentID, SharedBy, Token, ExpiresAt, MaxDownloads, DownloadCount, IsActive, CreatedAt) VALUES
(1,  1,  'tok_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6', '2025-03-25 10:00:00', 10, 3,  TRUE,  '2025-02-04 09:00:00'),
(12, 5,  'tok_b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7', '2025-04-30 23:59:59', 50, 12, TRUE,  '2025-02-05 10:00:00'),
(4,  3,  'tok_c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8', '2025-03-31 23:59:59', 20, 7,  TRUE,  '2025-02-06 11:00:00'),
(8,  5,  'tok_d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9', '2025-05-28 23:59:59', 100,45, TRUE,  '2025-02-06 14:00:00'),
(15, 13, 'tok_e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0', '2025-06-01 23:59:59', 200,89, TRUE,  '2025-02-07 08:00:00'),
(6,  5,  'tok_f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1', '2025-02-15 23:59:59', 5,  5,  FALSE, '2025-02-01 14:30:00'),
(14, 12, 'tok_g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2', '2025-04-01 23:59:59', 30, 8,  TRUE,  '2025-02-07 09:00:00'),
(17, 14, 'tok_h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3', '2025-03-15 23:59:59', 15, 2,  TRUE,  '2025-02-08 10:00:00'),
(18, 11, 'tok_i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4', '2025-05-01 23:59:59', 50, 20, TRUE,  '2025-02-08 11:00:00'),
(20, 19, 'tok_j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5', '2025-04-03 23:59:59', 25, 0,  TRUE,  '2025-02-09 07:00:00'),
(5,  4,  'tok_k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6', '2025-02-10 08:00:00', 3,  3,  FALSE, '2025-02-08 08:00:00'),
(11, 3,  'tok_l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7', '2025-03-30 23:59:59', 10, 4,  TRUE,  '2025-02-09 09:00:00');

-- -----------------------------------------------------------
-- Notification (20 rows)
-- -----------------------------------------------------------
INSERT INTO Notification (MemberID, DocumentID, Message, NotificationType, IsRead, CreatedAt) VALUES
(2,  1,  'You have been granted EDIT access to "CS432 Database Syllabus".',                  'PERMISSION', TRUE,  '2025-01-25 10:05:00'),
(8,  1,  'You have been granted VIEW access to "CS432 Database Syllabus" until Jun 30.',     'PERMISSION', TRUE,  '2025-01-25 10:10:00'),
(17, 2,  'Priya Mehta shared "ML Research Paper - CNN" with you.',                           'SHARE',      TRUE,  '2025-01-26 08:00:00'),
(1,  3,  'You have been granted VIEW access to "Faculty Meeting Jan 2025".',                 'PERMISSION', TRUE,  '2025-01-26 09:05:00'),
(18, 4,  'Rohan Patel shared "EE Lab Manual - Circuits" with you.',                          'SHARE',      FALSE, '2025-01-27 08:00:00'),
(19, 6,  'You have been granted EDIT access to "Leave Policy 2025".',                        'PERMISSION', TRUE,  '2025-01-28 08:00:00'),
(15, 7,  'Vikram Singh shared "Annual Budget Report FY25" with you.',                        'SHARE',      TRUE,  '2025-01-28 10:30:00'),
(1,  9,  'You have been granted EDIT access to "Research Grant Proposal".',                  'PERMISSION', TRUE,  '2025-01-29 08:00:00'),
(2,  9,  'A new version (v2) of "Research Grant Proposal" has been uploaded.',               'UPDATE',     TRUE,  '2025-02-02 09:01:00'),
(2,  9,  'A new version (v3) of "Research Grant Proposal" has been uploaded.',               'UPDATE',     TRUE,  '2025-02-05 16:01:00'),
(8,  12, 'Vikram Singh shared "Student Handbook 2025" with you.',                            'SHARE',      TRUE,  '2025-01-31 09:00:00'),
(1,  1,  'A shared link has been created for "CS432 Database Syllabus".',                    'SHARE',      TRUE,  '2025-02-04 09:00:00'),
(5,  12, '"Student Handbook 2025" has been updated to version 2.',                           'UPDATE',     FALSE, '2025-02-06 08:01:00'),
(13, 15, '"Placement Brochure 2025" has been updated to version 2.',                         'UPDATE',     TRUE,  '2025-02-07 12:01:00'),
(1,  NULL, 'System maintenance scheduled for Feb 15, 2025. Documents may be temporarily unavailable.', 'SYSTEM', FALSE, '2025-02-10 08:00:00'),
(2,  NULL, 'System maintenance scheduled for Feb 15, 2025. Documents may be temporarily unavailable.', 'SYSTEM', FALSE, '2025-02-10 08:00:00'),
(5,  NULL, 'System maintenance scheduled for Feb 15, 2025. Documents may be temporarily unavailable.', 'SYSTEM', FALSE, '2025-02-10 08:00:00'),
(4,  5,  'The shared link for "ME Final Year Project Report" has expired.',                  'SHARE',      TRUE,  '2025-02-10 08:01:00'),
(5,  6,  'The shared link for "Leave Policy 2025" has reached its download limit.',          'SHARE',      TRUE,  '2025-02-08 15:00:00'),
(3,  11, 'A shared link has been created for "EE Signal Processing Notes".',                 'SHARE',      FALSE, '2025-02-09 09:01:00');

-- ============================================================
-- END OF SQL DUMP
-- ============================================================
