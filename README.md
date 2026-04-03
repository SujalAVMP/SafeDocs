# SafeDocs -- Secure PDF Management System

**CS 432 -- Databases | Track 1 | Statement 6**
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

SafeDocs is a secure PDF document management system designed for organisations that handle sensitive documents such as legal files, financial reports, academic records, and internal policies. It provides fine-grained access control, version tracking, audit logging, and secure sharing.

## Core Functionalities

1. **Document Upload & Version Control** -- Upload PDFs with full version history and change notes
2. **Fine-Grained Access Control** -- Per-document permissions (VIEW, EDIT, DELETE, ADMIN) with optional expiry
3. **Audit Logging & Compliance** -- Immutable logs tracking every view, download, edit, share, and permission change
4. **Secure Document Sharing** -- Tokenised links with configurable expiry and download limits
5. **Document Organisation & Search** -- Hierarchical folders, tags, and department-scoped organisation
6. **Notification System** -- Alerts for shares, permission changes, version updates, and system events


## Repository Structure

```
.
├── README.md
├── safedocs_dump.sql              # Full schema DDL + sample data (Assignment 1)
├── er_diagram.md                  # Mermaid ER diagram (Assignment 1)
├── Report_A1.pdf                  # Assignment report (UML, ER, schema details)
├── Report_A2.pdf                  # Assignment 2 report (Module A + B details)
│
├── figures/                       # Benchmarking and design figures for reports
├── Module_A/                      # Lightweight DBMS with B+ Tree Index
│   ├── assignment3_demo.py        # ACID, recovery, and isolation demo runner
│   ├── database/
│   │   ├── __init__.py
│   │   ├── bplustree.py           # B+ Tree implementation
│   │   ├── bruteforce.py          # BruteForceDB baseline
│   │   ├── table.py               # Typed relational Table
│   │   ├── db_manager.py          # Multi-database DatabaseManager
│   │   ├── persistence.py         # Snapshot + journal durability helpers
│   │   └── transaction_manager.py # BEGIN / COMMIT / ROLLBACK coordinator
│   ├── report.ipynb               # Benchmarks, visualizations, and report
│   └── requirements.txt
│
├── Module_B/                      # Local API, RBAC, and Database Optimization
│   ├── app/
│   │   ├── app.py                 # Flask application (CRUD APIs + UI routes)
│   │   ├── auth.py                # JWT auth, RBAC decorators, audit logging
│   │   ├── __init__.py
│   │   └── templates/             # HTML templates (login, dashboard, etc.)
│   ├── sql/
│   │   ├── setup.sql              # UserLogin, SecurityLog tables + indexes
│   │   └── benchmark.sql          # EXPLAIN-based benchmark queries
│   ├── logs/
│   │   └── audit.log              # Security audit log file
│   ├── stress/
│   │   └── assignment3_stress.py  # Concurrency, rollback, and load harness
│   ├── report.ipynb               # Optimization report with benchmarks
│   └── requirements.txt
```


## Setup

### Prerequisites
- Python 3.10+
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

### Module A
```bash
cd Module_A
pip install -r requirements.txt
jupyter notebook report.ipynb
```

### Module A Assignment 3 Demo
```bash
cd Module_A
python3 assignment3_demo.py
```

This runs a three-table transactional scenario over B+ Tree-backed relations and verifies:
- atomic rollback after injected failure
- consistency checks for invalid transactions
- serialized isolation under concurrent buyers
- durability after restart
- recovery of incomplete transactions
- recovery from a journaled commit when checkpointing is interrupted

### Module B
```bash
# Import the base schema
mysql -u root -p < safedocs_dump.sql
# Run Module B setup (auth tables + indexes)
mysql -u safedocs -psafedocs123 safedocs < Module_B/sql/setup.sql
# Install dependencies
cd Module_B
pip install -r requirements.txt
# Run the Flask app from inside Module_B
python -m app.app
```

### Module B Assignment 3 Stress Test
Start the Flask app first, then run the stress harness in a second terminal:

```bash
cd Module_B
python3 stress/assignment3_stress.py
```

The harness checks:
- rollback integrity on a failed multi-step member creation request
- concurrent soft-delete safety on the same document
- mixed read-heavy API load across hundreds of requests with latency summaries

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


## Key Design Decisions

- **Normalised to 3NF** -- no redundant data; tags, roles, and departments are separate entities
- **Soft deletes** -- Documents and folders use `IsActive` flags instead of physical deletion
- **Immutable audit logs** -- `AccessLog` is append-only by design
- **Cascading deletes** -- Versions, tags, and permissions cascade with their parent document
- **Restrict deletes** -- Members cannot be deleted if they have uploaded documents
- **Logical constraints** -- Age >= 18, file size > 0, expiry > grant time, download count <= max


## Instructor

Dr. Yogesh K. Meena
