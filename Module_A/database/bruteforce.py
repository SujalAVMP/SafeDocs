"""
BruteForceDB -- a simple linear-scan baseline for performance comparison
against the B+ Tree implementation.

All operations are O(n). Insert handles duplicates (updates in place), and
get_all / range_query return sorted results for apples-to-apples comparison
with the B+ Tree.

CS 432 - Databases | IIT Gandhinagar | Assignment 2 - Module A
"""


class BruteForceDB:
    """Stores key-value pairs in a flat Python list; all operations are O(n)."""

    def __init__(self):
        self.data = []

    def insert(self, key, value=None):
        """Insert or update a key-value pair. O(n) duplicate check."""
        for i, (k, _) in enumerate(self.data):
            if k == key:
                self.data[i] = (key, value)
                return
        self.data.append((key, value))

    def search(self, key):
        """Linear scan for *key*. Return value if found, else None."""
        for k, v in self.data:
            if k == key:
                return v
        return None

    def contains(self, key):
        """Return True if *key* exists. O(n)."""
        return any(k == key for k, _ in self.data)

    def delete(self, key):
        """Remove the first occurrence of *key*. Return True/False."""
        for i, (k, v) in enumerate(self.data):
            if k == key:
                self.data.pop(i)
                return True
        return False

    def update(self, key, value):
        """Update value for an existing key. Returns True if updated. O(n)."""
        for i, (k, _) in enumerate(self.data):
            if k == key:
                self.data[i] = (key, value)
                return True
        return False

    def range_query(self, start, end):
        """Return all (key, value) pairs where start <= key <= end, sorted."""
        return sorted(
            [(k, v) for k, v in self.data if start <= k <= end],
            key=lambda x: x[0],
        )

    def get_all(self):
        """Return all stored (key, value) pairs, sorted by key."""
        return sorted(self.data, key=lambda x: x[0])

    def count(self):
        """Return number of stored keys."""
        return len(self.data)

    def __len__(self):
        return len(self.data)

    def __repr__(self):
        return f"BruteForceDB(size={len(self.data)})"
