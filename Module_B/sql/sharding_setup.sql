-- ============================================================
-- SafeDocs Module B: Assignment 4 Sharding Setup
-- Strategy: Hash-based sharding on DocumentID using MOD(DocumentID, 3)
-- Sharded tables:
--   - shard_0_document / shard_1_document / shard_2_document
--   - shard_0_accesslog / shard_1_accesslog / shard_2_accesslog
-- Support tables:
--   - DocumentIdSequence
--   - DocumentShardDirectory
-- ============================================================

USE safedocs;

-- ============================================================
-- Global helpers
-- ============================================================

CREATE TABLE IF NOT EXISTS DocumentIdSequence (
    DocumentID   INT PRIMARY KEY AUTO_INCREMENT,
    ReservedAt   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS DocumentShardDirectory (
    DocumentID   INT PRIMARY KEY,
    ShardID      TINYINT NOT NULL,
    Origin       VARCHAR(20) NOT NULL DEFAULT 'migration',
    RoutedAt     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_doc_directory_shard CHECK (ShardID IN (0, 1, 2))
);

CREATE INDEX IF NOT EXISTS idx_doc_directory_shard ON DocumentShardDirectory(ShardID, DocumentID);

-- ============================================================
-- Shard 0
-- ============================================================

CREATE TABLE IF NOT EXISTS shard_0_document (
    DocumentID      INT             PRIMARY KEY,
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

    CONSTRAINT chk_shard0_doc_filesize CHECK (FileSize > 0),
    CONSTRAINT fk_shard0_doc_uploader FOREIGN KEY (UploadedBy)
        REFERENCES Member(MemberID)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_shard0_doc_folder FOREIGN KEY (FolderID)
        REFERENCES Folder(FolderID)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_shard0_doc_title ON shard_0_document(Title);
CREATE INDEX IF NOT EXISTS idx_shard0_doc_created ON shard_0_document(CreatedAt);
CREATE INDEX IF NOT EXISTS idx_shard0_doc_uploaded_active ON shard_0_document(UploadedBy, IsActive);

CREATE TABLE IF NOT EXISTS shard_0_accesslog (
    LogID           INT             PRIMARY KEY AUTO_INCREMENT,
    DocumentID      INT             NOT NULL,
    MemberID        INT             NOT NULL,
    Action          ENUM('VIEW','DOWNLOAD','UPLOAD','EDIT','DELETE','SHARE','PERMISSION_CHANGE') NOT NULL,
    IPAddress       VARCHAR(45),
    UserAgent       VARCHAR(255),
    AccessTimestamp DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_shard0_log_document FOREIGN KEY (DocumentID)
        REFERENCES shard_0_document(DocumentID)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_shard0_log_member FOREIGN KEY (MemberID)
        REFERENCES Member(MemberID)
        ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_shard0_log_member_ts ON shard_0_accesslog(MemberID, AccessTimestamp);
CREATE INDEX IF NOT EXISTS idx_shard0_log_doc_ts ON shard_0_accesslog(DocumentID, AccessTimestamp);

-- ============================================================
-- Shard 1
-- ============================================================

CREATE TABLE IF NOT EXISTS shard_1_document (
    DocumentID      INT             PRIMARY KEY,
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

    CONSTRAINT chk_shard1_doc_filesize CHECK (FileSize > 0),
    CONSTRAINT fk_shard1_doc_uploader FOREIGN KEY (UploadedBy)
        REFERENCES Member(MemberID)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_shard1_doc_folder FOREIGN KEY (FolderID)
        REFERENCES Folder(FolderID)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_shard1_doc_title ON shard_1_document(Title);
CREATE INDEX IF NOT EXISTS idx_shard1_doc_created ON shard_1_document(CreatedAt);
CREATE INDEX IF NOT EXISTS idx_shard1_doc_uploaded_active ON shard_1_document(UploadedBy, IsActive);

CREATE TABLE IF NOT EXISTS shard_1_accesslog (
    LogID           INT             PRIMARY KEY AUTO_INCREMENT,
    DocumentID      INT             NOT NULL,
    MemberID        INT             NOT NULL,
    Action          ENUM('VIEW','DOWNLOAD','UPLOAD','EDIT','DELETE','SHARE','PERMISSION_CHANGE') NOT NULL,
    IPAddress       VARCHAR(45),
    UserAgent       VARCHAR(255),
    AccessTimestamp DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_shard1_log_document FOREIGN KEY (DocumentID)
        REFERENCES shard_1_document(DocumentID)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_shard1_log_member FOREIGN KEY (MemberID)
        REFERENCES Member(MemberID)
        ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_shard1_log_member_ts ON shard_1_accesslog(MemberID, AccessTimestamp);
CREATE INDEX IF NOT EXISTS idx_shard1_log_doc_ts ON shard_1_accesslog(DocumentID, AccessTimestamp);

-- ============================================================
-- Shard 2
-- ============================================================

CREATE TABLE IF NOT EXISTS shard_2_document (
    DocumentID      INT             PRIMARY KEY,
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

    CONSTRAINT chk_shard2_doc_filesize CHECK (FileSize > 0),
    CONSTRAINT fk_shard2_doc_uploader FOREIGN KEY (UploadedBy)
        REFERENCES Member(MemberID)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_shard2_doc_folder FOREIGN KEY (FolderID)
        REFERENCES Folder(FolderID)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_shard2_doc_title ON shard_2_document(Title);
CREATE INDEX IF NOT EXISTS idx_shard2_doc_created ON shard_2_document(CreatedAt);
CREATE INDEX IF NOT EXISTS idx_shard2_doc_uploaded_active ON shard_2_document(UploadedBy, IsActive);

CREATE TABLE IF NOT EXISTS shard_2_accesslog (
    LogID           INT             PRIMARY KEY AUTO_INCREMENT,
    DocumentID      INT             NOT NULL,
    MemberID        INT             NOT NULL,
    Action          ENUM('VIEW','DOWNLOAD','UPLOAD','EDIT','DELETE','SHARE','PERMISSION_CHANGE') NOT NULL,
    IPAddress       VARCHAR(45),
    UserAgent       VARCHAR(255),
    AccessTimestamp DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_shard2_log_document FOREIGN KEY (DocumentID)
        REFERENCES shard_2_document(DocumentID)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_shard2_log_member FOREIGN KEY (MemberID)
        REFERENCES Member(MemberID)
        ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_shard2_log_member_ts ON shard_2_accesslog(MemberID, AccessTimestamp);
CREATE INDEX IF NOT EXISTS idx_shard2_log_doc_ts ON shard_2_accesslog(DocumentID, AccessTimestamp);

-- ============================================================
-- Migration from legacy unsharded tables
-- ============================================================

INSERT IGNORE INTO shard_0_document
    (DocumentID, Title, Description, FilePath, FileSize, MimeType, UploadedBy, FolderID,
     IsConfidential, IsActive, CreatedAt, UpdatedAt)
SELECT DocumentID, Title, Description, FilePath, FileSize, MimeType, UploadedBy, FolderID,
       IsConfidential, IsActive, CreatedAt, UpdatedAt
FROM Document
WHERE MOD(DocumentID, 3) = 0;

INSERT IGNORE INTO shard_1_document
    (DocumentID, Title, Description, FilePath, FileSize, MimeType, UploadedBy, FolderID,
     IsConfidential, IsActive, CreatedAt, UpdatedAt)
SELECT DocumentID, Title, Description, FilePath, FileSize, MimeType, UploadedBy, FolderID,
       IsConfidential, IsActive, CreatedAt, UpdatedAt
FROM Document
WHERE MOD(DocumentID, 3) = 1;

INSERT IGNORE INTO shard_2_document
    (DocumentID, Title, Description, FilePath, FileSize, MimeType, UploadedBy, FolderID,
     IsConfidential, IsActive, CreatedAt, UpdatedAt)
SELECT DocumentID, Title, Description, FilePath, FileSize, MimeType, UploadedBy, FolderID,
       IsConfidential, IsActive, CreatedAt, UpdatedAt
FROM Document
WHERE MOD(DocumentID, 3) = 2;

INSERT IGNORE INTO shard_0_accesslog
    (LogID, DocumentID, MemberID, Action, IPAddress, UserAgent, AccessTimestamp)
SELECT LogID, DocumentID, MemberID, Action, IPAddress, UserAgent, AccessTimestamp
FROM AccessLog
WHERE MOD(DocumentID, 3) = 0;

INSERT IGNORE INTO shard_1_accesslog
    (LogID, DocumentID, MemberID, Action, IPAddress, UserAgent, AccessTimestamp)
SELECT LogID, DocumentID, MemberID, Action, IPAddress, UserAgent, AccessTimestamp
FROM AccessLog
WHERE MOD(DocumentID, 3) = 1;

INSERT IGNORE INTO shard_2_accesslog
    (LogID, DocumentID, MemberID, Action, IPAddress, UserAgent, AccessTimestamp)
SELECT LogID, DocumentID, MemberID, Action, IPAddress, UserAgent, AccessTimestamp
FROM AccessLog
WHERE MOD(DocumentID, 3) = 2;

INSERT INTO DocumentShardDirectory (DocumentID, ShardID, Origin)
SELECT DocumentID, MOD(DocumentID, 3), 'migration'
FROM Document
ON DUPLICATE KEY UPDATE
    ShardID = VALUES(ShardID),
    Origin = VALUES(Origin);

INSERT IGNORE INTO DocumentIdSequence (DocumentID)
SELECT DocumentID FROM Document
UNION
SELECT DocumentID FROM shard_0_document
UNION
SELECT DocumentID FROM shard_1_document
UNION
SELECT DocumentID FROM shard_2_document;

-- ============================================================
-- Verification queries (run manually if needed)
-- ============================================================
-- SELECT
--   (SELECT COUNT(*) FROM Document) AS legacy_document_count,
--   (SELECT COUNT(*) FROM shard_0_document)
-- + (SELECT COUNT(*) FROM shard_1_document)
-- + (SELECT COUNT(*) FROM shard_2_document) AS sharded_document_count;
--
-- SELECT
--   (SELECT COUNT(*) FROM AccessLog) AS legacy_accesslog_count,
--   (SELECT COUNT(*) FROM shard_0_accesslog)
-- + (SELECT COUNT(*) FROM shard_1_accesslog)
-- + (SELECT COUNT(*) FROM shard_2_accesslog) AS sharded_accesslog_count;
