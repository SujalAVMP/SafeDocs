# SafeDocs -- Secure PDF Management System

**CS 432 -- Databases | Assignment 1 | Track 1 | Statement 6**
**Indian Institute of Technology, Gandhinagar | Semester II (2025--2026)**

## Team

| Name | Roll Number |
|------|-------------|
| Sujal Patel | 22110261 |
| Siddharth Doshi | 22110250 |
| Viraj Vekaria | 22110287 |
| Nishit Mistry | 22110172 |
| Rutvi Shah | 22110227 |

## About

SafeDocs is a secure PDF document management system designed for organisations that handle sensitive documents such as legal files, financial reports, academic records, and internal policies. It provides fine-grained access control, version tracking, audit logging, and secure sharing -- addressing the limitations of generic cloud storage platforms.

## Core Functionalities

1. **Document Upload & Version Control** -- Upload PDFs with full version history and change notes
2. **Fine-Grained Access Control** -- Per-document permissions (VIEW, EDIT, DELETE, ADMIN) with optional expiry
3. **Audit Logging & Compliance** -- Immutable logs tracking every view, download, edit, share, and permission change
4. **Secure Document Sharing** -- Tokenised links with configurable expiry and download limits
5. **Document Organisation & Search** -- Hierarchical folders, tags, and department-scoped organisation
6. **Notification System** -- Alerts for shares, permission changes, version updates, and system events

## Database Schema

The system uses **12 tables** across **7 entities**:

| # | Table | Purpose |
|---|-------|---------|
| 1 | Department | Organisational units |
| 2 | Role | User roles with capability flags |
| 3 | Member | System users |
| 4 | Folder | Hierarchical document folders (self-referencing) |
| 5 | Document | Core PDF document metadata |
| 6 | DocumentVersion | Version history per document |
| 7 | Tag | Categorisation labels |
| 8 | DocumentTag | Many-to-many junction (Document -- Tag) |
| 9 | Permission | Per-document access grants |
| 10 | AccessLog | Immutable audit trail |
| 11 | SharedLink | Secure external sharing links |
| 12 | Notification | User alert messages |

## ER Diagram

See [er_diagram.md](er_diagram.md) for the full Mermaid ER diagram.

## Repository Structure

```
.
├── README.md              # This file
├── safedocs_dump.sql      # Complete SQL dump (DDL + sample data)
├── er_diagram.md          # Mermaid ER diagram
└── Report.pdf             # Assignment report (UML, ER, schema details)
```

## Setup

### Prerequisites
- MySQL 8.0+ or MariaDB 10.5+

### Import the database
```bash
mysql -u root -p < safedocs_dump.sql
```

This creates the `safedocs` database, all 12 tables with constraints and indexes, and populates them with realistic sample data (10--20 rows per table).

### Verify
```bash
mysql -u root -p safedocs -e "SELECT COUNT(*) AS table_count FROM information_schema.tables WHERE table_schema='safedocs';"
```
Expected output: `12`

## Key Design Decisions

- **Normalised to 3NF** -- no redundant data; tags, roles, and departments are separate entities
- **Soft deletes** -- Documents and folders use `IsActive` flags instead of physical deletion
- **Immutable audit logs** -- `AccessLog` is append-only by design
- **Cascading deletes** -- Versions, tags, and permissions cascade with their parent document
- **Restrict deletes** -- Members cannot be deleted if they have uploaded documents
- **Logical constraints** -- Age >= 18, file size > 0, expiry > grant time, download count <= max

## Instructor

Dr. Yogesh K. Meena
