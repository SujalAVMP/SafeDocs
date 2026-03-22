# SafeDocs - ER Diagram

```mermaid
erDiagram
    Department ||--o{ Member : "belongs to"
    Department ||--o{ Folder : "scopes"
    Role ||--o{ Member : "has role"
    Member ||--o{ Document : "uploads"
    Member ||--o{ Folder : "creates"
    Member ||--o{ Permission : "granted to"
    Member ||--o{ AccessLog : "performs"
    Member ||--o{ SharedLink : "creates"
    Member ||--o{ Notification : "receives"
    Folder ||--o{ Document : "contains"
    Folder ||--o{ Folder : "parent of"
    Document ||--o{ DocumentVersion : "has version"
    Document }o--o{ Tag : "tagged with"
    Document ||--o{ Permission : "controls"
    Document ||--o{ AccessLog : "logged"
    Document ||--o{ SharedLink : "shared via"
    Document ||--o{ Notification : "triggers"

    Department {
        INT DepartmentID PK
        VARCHAR DeptName "NOT NULL, UNIQUE"
        VARCHAR Description
        DATETIME CreatedAt "NOT NULL"
    }

    Role {
        INT RoleID PK
        VARCHAR RoleName "NOT NULL, UNIQUE"
        VARCHAR Description
        BOOLEAN CanUpload "NOT NULL"
        BOOLEAN CanDelete "NOT NULL"
        BOOLEAN CanShare "NOT NULL"
        BOOLEAN CanManageUsers "NOT NULL"
    }

    Member {
        INT MemberID PK
        VARCHAR Name "NOT NULL"
        VARCHAR Image
        INT Age "CHECK >= 18"
        VARCHAR Email "NOT NULL, UNIQUE"
        VARCHAR ContactNumber "NOT NULL, UNIQUE"
        INT DepartmentID FK
        INT RoleID FK
        VARCHAR PasswordHash "NOT NULL"
        BOOLEAN IsActive "NOT NULL"
        DATETIME CreatedAt "NOT NULL"
    }

    Folder {
        INT FolderID PK
        VARCHAR FolderName "NOT NULL"
        VARCHAR Description
        INT ParentFolderID FK
        INT CreatedBy FK
        INT DepartmentID FK
        DATETIME CreatedAt "NOT NULL"
        BOOLEAN IsActive "NOT NULL"
    }

    Document {
        INT DocumentID PK
        VARCHAR Title "NOT NULL"
        VARCHAR Description
        VARCHAR FilePath "NOT NULL"
        BIGINT FileSize "NOT NULL, CHECK > 0"
        VARCHAR MimeType "NOT NULL"
        INT UploadedBy FK
        INT FolderID FK
        BOOLEAN IsConfidential "NOT NULL"
        BOOLEAN IsActive "NOT NULL"
        DATETIME CreatedAt "NOT NULL"
        DATETIME UpdatedAt "NOT NULL"
    }

    DocumentVersion {
        INT DocumentID PK_FK "Identifying relationship"
        INT VersionNumber PK "Partial key, CHECK > 0"
        VARCHAR FilePath "NOT NULL"
        BIGINT FileSize "NOT NULL"
        INT UploadedBy FK
        VARCHAR ChangeNote
        DATETIME CreatedAt "NOT NULL"
    }

    Tag {
        INT TagID PK
        VARCHAR TagName "NOT NULL, UNIQUE"
        VARCHAR Description
        DATETIME CreatedAt "NOT NULL"
    }

    DocumentTag {
        INT DocumentID PK_FK
        INT TagID PK_FK
        DATETIME AssignedAt "NOT NULL"
    }

    Permission {
        INT PermissionID PK
        INT DocumentID FK
        INT MemberID FK
        ENUM AccessLevel "NOT NULL"
        INT GrantedBy FK
        DATETIME GrantedAt "NOT NULL"
        DATETIME ExpiresAt "CHECK > GrantedAt"
    }

    AccessLog {
        INT LogID PK
        INT DocumentID FK
        INT MemberID FK
        ENUM Action "NOT NULL"
        VARCHAR IPAddress
        VARCHAR UserAgent
        DATETIME AccessTimestamp "NOT NULL"
    }

    SharedLink {
        INT LinkID PK
        INT DocumentID FK
        INT SharedBy FK
        VARCHAR Token "NOT NULL, UNIQUE"
        DATETIME ExpiresAt "NOT NULL"
        INT MaxDownloads "NOT NULL, CHECK > 0"
        INT DownloadCount "NOT NULL"
        BOOLEAN IsActive "NOT NULL"
        DATETIME CreatedAt "NOT NULL"
    }

    Notification {
        INT NotificationID PK
        INT MemberID FK
        INT DocumentID FK
        VARCHAR Message "NOT NULL"
        ENUM NotificationType "NOT NULL"
        BOOLEAN IsRead "NOT NULL"
        DATETIME CreatedAt "NOT NULL"
    }
```
