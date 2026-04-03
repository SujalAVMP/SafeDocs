"""
DatabaseManager -- multi-database manager that holds named databases,
each containing named Table instances.  Provides a convenient interface
for DDL (create/drop database/table) and delegates DML to individual tables.

CS 432 - Databases | IIT Gandhinagar | Assignment 2 - Module A
"""

import copy

from .table import Table


class DatabaseManager:
    """
    Manages multiple databases, each a dict of {table_name: Table}.

    Usage::

        dm = DatabaseManager()
        dm.create_database("university")
        dm.create_table("university", "students",
                        schema={"sid": int, "name": str},
                        order=6, search_key="sid")
        table, _ = dm.get_table("university", "students")
        table.insert({"sid": 1, "name": "Alice"})
    """

    def __init__(self):
        self.databases: dict[str, dict[str, Table]] = {}

    # ------------------------------------------------------------------
    # Database-level DDL
    # ------------------------------------------------------------------

    def create_database(self, db_name):
        """Create a new empty database. Returns (success, message)."""
        if db_name in self.databases:
            return False, f"Database '{db_name}' already exists"
        self.databases[db_name] = {}
        return True, f"Database '{db_name}' created successfully"

    def delete_database(self, db_name):
        """Delete a database and all its tables. Returns (success, message)."""
        if db_name not in self.databases:
            return False, f"Database '{db_name}' not found"
        del self.databases[db_name]
        return True, f"Database '{db_name}' deleted successfully"

    def list_databases(self):
        """Return a list of all database names."""
        return list(self.databases.keys())

    # ------------------------------------------------------------------
    # Table-level DDL
    # ------------------------------------------------------------------

    def create_table(self, db_name, table_name, schema, order=8, search_key=None):
        """
        Create a new table in the specified database.

        Parameters
        ----------
        db_name : str
        table_name : str
        schema : dict[str, type]
            Column definitions, e.g. ``{"id": int, "name": str}``.
        order : int
            B+ Tree order.
        search_key : str | None
            Column used as the primary / index key.

        Returns (success, message).
        """
        if db_name not in self.databases:
            return False, f"Database '{db_name}' not found"
        if table_name in self.databases[db_name]:
            return False, f"Table '{table_name}' already exists in database '{db_name}'"
        self.databases[db_name][table_name] = Table(
            table_name, schema, order=order, search_key=search_key
        )
        return True, f"Table '{table_name}' created successfully in database '{db_name}'"

    def delete_table(self, db_name, table_name):
        """Delete a table from the specified database. Returns (success, message)."""
        if db_name not in self.databases:
            return False, f"Database '{db_name}' not found"
        if table_name not in self.databases[db_name]:
            return False, f"Table '{table_name}' not found in database '{db_name}'"
        del self.databases[db_name][table_name]
        return True, f"Table '{table_name}' deleted successfully"

    def list_tables(self, db_name):
        """
        List all tables in a database.

        Returns (list_of_names, message) or (None, error_message).
        """
        if db_name not in self.databases:
            return None, f"Database '{db_name}' not found"
        return list(self.databases[db_name].keys()), "Success"

    def get_table(self, db_name, table_name):
        """
        Retrieve a Table instance.

        Returns (Table, message) or (None, error_message).
        """
        if db_name not in self.databases:
            return None, f"Database '{db_name}' not found"
        if table_name not in self.databases[db_name]:
            return None, f"Table '{table_name}' not found in database '{db_name}'"
        return self.databases[db_name][table_name], "Success"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def __repr__(self):
        return f"DatabaseManager(databases={self.list_databases()})"

    # ------------------------------------------------------------------
    # Persistence / cloning
    # ------------------------------------------------------------------

    def to_dict(self):
        """Serialize every database and table managed by this instance."""
        return {
            "databases": {
                db_name: {
                    table_name: table.to_dict()
                    for table_name, table in tables.items()
                }
                for db_name, tables in self.databases.items()
            }
        }

    @classmethod
    def from_dict(cls, payload):
        """Rebuild a DatabaseManager from serialized databases/tables."""
        manager = cls()
        for db_name, tables in payload.get("databases", {}).items():
            manager.databases[db_name] = {}
            for table_name, table_payload in tables.items():
                rebuilt = Table.from_dict(copy.deepcopy(table_payload))
                manager.databases[db_name][table_name] = rebuilt
        return manager

    def clone(self):
        """Return a deep logical copy of the manager and all tables."""
        return self.from_dict(self.to_dict())
