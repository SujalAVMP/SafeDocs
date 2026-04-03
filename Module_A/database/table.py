"""
Table abstraction backed by a B+ Tree index.

Each Table has a name, a typed schema (dict of {column: data_type}), and a
designated search_key column used for B+ Tree indexing.  Methods follow the
(success, result/message) return convention expected by the Flask API layer.

CS 432 - Databases | IIT Gandhinagar | Assignment 2 - Module A
"""

import copy

from .bplustree import BPlusTree


TYPE_NAME_MAP = {
    int: "int",
    float: "float",
    str: "str",
    bool: "bool",
}

NAME_TYPE_MAP = {name: dtype for dtype, name in TYPE_NAME_MAP.items()}


class Table:
    """
    A relational table storing records (dicts) indexed by a B+ Tree.

    Parameters
    ----------
    name : str
        Table name.
    schema : dict[str, type]
        Column definitions, e.g. ``{"student_id": int, "name": str, "age": float}``.
    order : int, default 8
        B+ Tree order for the underlying index.
    search_key : str | None
        Column to use as the primary / index key.  Must be present in *schema*.
    """

    def __init__(self, name, schema, order=8, search_key=None):
        self.name = name
        self.schema = schema                        # {column_name: data_type}
        self.order = order
        self.data = BPlusTree(order=order)           # underlying B+ Tree
        self.search_key = search_key                 # PK / index column

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_record(self, record):
        """
        Validate that *record* matches the table schema:
        - All columns defined in the schema are present.
        - Values are coercible to the declared type.

        Returns (True, "Valid") or (False, error_message).
        Also coerces values in-place when possible (e.g. str → int).
        """
        for col, dtype in self.schema.items():
            if col not in record:
                return False, f"Missing required column: {col}"
            if not isinstance(record[col], dtype):
                try:
                    record[col] = dtype(record[col])
                except (ValueError, TypeError):
                    return False, (
                        f"Invalid type for '{col}': "
                        f"expected {dtype.__name__}, got {type(record[col]).__name__}"
                    )
        return True, "Valid"

    @staticmethod
    def _serialize_schema(schema):
        """Convert Python types to stable string names for persistence."""
        serialized = {}
        for column, dtype in schema.items():
            if dtype not in TYPE_NAME_MAP:
                raise ValueError(f"Unsupported schema type for persistence: {dtype!r}")
            serialized[column] = TYPE_NAME_MAP[dtype]
        return serialized

    @staticmethod
    def _deserialize_schema(schema_payload):
        """Convert persisted schema type names back to Python types."""
        schema = {}
        for column, dtype_name in schema_payload.items():
            if dtype_name not in NAME_TYPE_MAP:
                raise ValueError(f"Unsupported persisted schema type: {dtype_name!r}")
            schema[column] = NAME_TYPE_MAP[dtype_name]
        return schema

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def insert(self, record):
        """
        Insert a new record into the table.

        Returns (True, key) on success, or (False, error_message) on failure.
        """
        valid, msg = self.validate_record(record)
        if not valid:
            return False, msg
        key = record[self.search_key]
        if self.data.contains(key):
            return False, f"Duplicate key: {key}"
        stored = {col: record.get(col) for col in self.schema}
        self.data.insert(key, stored)
        return True, key

    def get(self, record_id):
        """
        Retrieve a single record by its search_key value.
        Returns the record dict, or None if not found.
        """
        return self.data.search(record_id)

    def get_all(self):
        """
        Return all records as a list of (key, record_dict) tuples,
        sorted by the search key.
        """
        return self.data.get_all()

    def update(self, record_id, new_record):
        """
        Update the record identified by *record_id*.

        Returns (True, message) on success, or (False, message) on failure.
        """
        existing = self.data.search(record_id)
        if existing is None:
            return False, "Record not found"

        updated = existing.copy()
        changed = False
        for col, value in new_record.items():
            if col in self.schema:
                updated[col] = value
                changed = True

        if not changed:
            return False, "No valid fields to update"

        valid, msg = self.validate_record(updated)
        if not valid:
            return False, msg

        for col in self.schema:
            existing[col] = updated[col]
        return True, "Record updated"

    def delete(self, record_id):
        """
        Delete the record with the given search_key value.

        Returns (True, message) on success, or (False, message) on failure.
        """
        if self.data.delete(record_id):
            return True, "Record deleted"
        return False, "Record not found"

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def search(self, constraints):
        """
        Constraint-based search: *constraints* is a dict of {column: value}.
        Returns all matching records as a list of (key, record) tuples.
        Performs a linear scan through all records.
        """
        results = []
        for key, record in self.data.get_all():
            match = all(
                field in record and record[field] == value
                for field, value in constraints.items()
            )
            if match:
                results.append((key, record))
        return results

    def range_query(self, field_or_start, start_or_end=None, end=None):
        """
        Range query supporting two calling conventions:

        - ``range_query(start, end)``  -- range on the search key (B+ Tree)
        - ``range_query(field, start, end)``  -- range on any field
          (B+ Tree if *field* == search_key, otherwise linear scan)

        Returns list of (key, record) tuples.
        """
        if end is not None:
            # 3-arg: (field, start, end)
            field, start_val, end_val = field_or_start, start_or_end, end
        else:
            # 2-arg: (start, end) on search key
            field, start_val, end_val = self.search_key, field_or_start, start_or_end

        if field == self.search_key:
            return self.data.range_query(start_val, end_val)
        else:
            # linear scan for non-indexed fields
            results = []
            for key, record in self.data.get_all():
                if field in record and start_val <= record[field] <= end_val:
                    results.append((key, record))
            return results

    # ------------------------------------------------------------------
    # Visualization
    # ------------------------------------------------------------------

    def visualize_index(self, filename=None, view_graph=False):
        """Return a Graphviz Digraph of the underlying B+ Tree index."""
        return self.data.visualize_tree(filename=filename, view_graph=view_graph)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def count(self):
        """Return number of records in the table."""
        return len(self.data)

    def __len__(self):
        return len(self.data)

    def __repr__(self):
        return f"Table(name='{self.name}', rows={len(self)})"

    # ------------------------------------------------------------------
    # Persistence / cloning
    # ------------------------------------------------------------------

    def to_dict(self):
        """Serialize the table using the B+ Tree contents as the source of truth."""
        return {
            "name": self.name,
            "schema": self._serialize_schema(self.schema),
            "order": self.order,
            "search_key": self.search_key,
            "records": [
                {"key": copy.deepcopy(key), "record": copy.deepcopy(record)}
                for key, record in self.get_all()
            ],
        }

    @classmethod
    def from_dict(cls, payload):
        """Rebuild a table from a serialized payload."""
        table = cls(
            name=payload["name"],
            schema=cls._deserialize_schema(payload["schema"]),
            order=payload.get("order", 8),
            search_key=payload.get("search_key"),
        )
        for row in payload.get("records", []):
            table.insert(copy.deepcopy(row["record"]))
        return table

    def clone(self):
        """Return a deep logical copy of the table."""
        return self.from_dict(self.to_dict())
