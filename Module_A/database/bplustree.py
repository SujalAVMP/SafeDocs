"""
B+ Tree Implementation for SafeDocs Database Indexing Engine.

A complete B+ Tree with support for insertion, deletion, search, range queries,
update, and Graphviz-based visualization. Leaf nodes are connected via a linked
list (next pointers) to allow efficient sequential and range scans.

CS 432 - Databases | IIT Gandhinagar | Assignment 2 - Module A
"""

import copy

try:
    from graphviz import Digraph
except ImportError:
    Digraph = None


class BPlusTreeNode:
    """A single node in the B+ Tree (internal or leaf)."""

    def __init__(self, is_leaf=False):
        self.keys = []          # list of keys stored in this node
        self.values = []        # only used in leaf nodes: parallel list of values
        self.children = []      # only used in internal nodes: child pointers
        self.is_leaf = is_leaf
        self.next = None   # linked-list pointer (leaf -> next leaf)

    def __repr__(self):
        kind = "Leaf" if self.is_leaf else "Internal"
        return f"{kind}(keys={self.keys})"


class BPlusTree:
    """
    B+ Tree with configurable order.

    Parameters
    ----------
    order : int, default 5
        Maximum number of children an internal node may have.
        A node can hold at most (order - 1) keys.
        Minimum keys in a non-root node = ceil(order / 2) - 1.
    """

    def __init__(self, order=5):
        if order < 3:
            raise ValueError("Order must be at least 3")
        self.order = order
        self.root = BPlusTreeNode(is_leaf=True)
        self._max_keys = order - 1          # maximum keys per node
        self._min_keys = (order + 1) // 2 - 1  # minimum keys for non-root node
        self._size = 0  # O(1) record count

    @property
    def min_keys_leaf(self):
        """Minimum keys allowed in a non-root leaf node."""
        return (self.order - 1) // 2

    @property
    def min_keys_internal(self):
        """Minimum keys allowed in a non-root internal node."""
        return self.order // 2 - 1

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _find_leaf(self, key):
        """Navigate to the leaf node where *key* would reside."""
        node = self.root
        while not node.is_leaf:
            i = 0
            while i < len(node.keys) and key >= node.keys[i]:
                i += 1
            node = node.children[i]
        return node

    def search(self, key):
        """Search for *key*. Return the associated value, or None."""
        leaf = self._find_leaf(key)
        for i, k in enumerate(leaf.keys):
            if k == key:
                return leaf.values[i]
        return None

    def contains(self, key):
        """Return True if *key* exists in the tree."""
        return self.search(key) is not None

    # ------------------------------------------------------------------
    # Insert
    # ------------------------------------------------------------------

    def insert(self, key, value):
        """Insert a key-value pair. If key exists, update value in place."""
        # check if key already exists (update, not a new entry)
        existing = self.search(key)
        root = self.root
        if len(root.keys) == self._max_keys:
            # root is full -- create a new root and split
            new_root = BPlusTreeNode(is_leaf=False)
            new_root.children.append(self.root)
            self._split_child(new_root, 0)
            self.root = new_root
        self._insert_non_full(self.root, key, value)
        if existing is None:
            self._size += 1

    def _insert_non_full(self, node, key, value):
        """Recursively insert into a node that is guaranteed not to be full."""
        if node.is_leaf:
            # find the correct sorted position
            i = 0
            while i < len(node.keys) and node.keys[i] < key:
                i += 1
            # if key already exists, update value
            if i < len(node.keys) and node.keys[i] == key:
                node.values[i] = value
                return
            node.keys.insert(i, key)
            node.values.insert(i, value)
        else:
            # find the child to descend into
            i = 0
            while i < len(node.keys) and key >= node.keys[i]:
                i += 1
            # if that child is full, split it first
            if len(node.children[i].keys) == self._max_keys:
                self._split_child(node, i)
                # after split, decide which of the two children to go into
                if key >= node.keys[i]:
                    i += 1
            self._insert_non_full(node.children[i], key, value)

    def _split_child(self, parent, index):
        """
        Split the child of *parent* at *index*.

        For leaf nodes:
          - The right half keeps keys[mid:] and values[mid:]
          - The middle key is *copied* up to the parent
          - Linked-list pointers are updated

        For internal nodes:
          - The middle key is *pushed* (promoted) up to the parent
          - Left child keeps keys[:mid], right child gets keys[mid+1:]
          - Children are split accordingly
        """
        child = parent.children[index]
        mid = len(child.keys) // 2

        new_node = BPlusTreeNode(is_leaf=child.is_leaf)

        if child.is_leaf:
            # --- leaf split ---
            new_node.keys = child.keys[mid:]
            new_node.values = child.values[mid:]
            child.keys = child.keys[:mid]
            child.values = child.values[:mid]

            # maintain linked list
            new_node.next = child.next
            child.next = new_node

            # copy the first key of the new node up to the parent
            promote_key = new_node.keys[0]
        else:
            # --- internal node split ---
            promote_key = child.keys[mid]

            new_node.keys = child.keys[mid + 1:]
            new_node.children = child.children[mid + 1:]
            child.keys = child.keys[:mid]
            child.children = child.children[:mid + 1]

        parent.keys.insert(index, promote_key)
        parent.children.insert(index + 1, new_node)

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete(self, key):
        """
        Delete *key* from the B+ tree.
        Returns True if the key was found and deleted, False otherwise.
        """
        if not self.root.keys:
            return False
        found = self._delete(self.root, key)
        # if the root is an internal node with 0 keys, shrink the tree
        if not self.root.is_leaf and len(self.root.keys) == 0:
            self.root = self.root.children[0]
        if found:
            self._size -= 1
        return found

    def _delete(self, node, key):
        """Recursive helper for deletion."""
        if node.is_leaf:
            # --- leaf: remove directly ---
            for i, k in enumerate(node.keys):
                if k == key:
                    node.keys.pop(i)
                    node.values.pop(i)
                    return True
            return False

        # --- internal node: find the child that should contain *key* ---
        i = 0
        while i < len(node.keys) and key >= node.keys[i]:
            i += 1

        # ensure the child we descend into has enough keys
        if len(node.children[i].keys) <= self._min_keys:
            self._fill_child(node, i)
            # recalculate i after possible merge
            i = 0
            while i < len(node.keys) and key >= node.keys[i]:
                i += 1
            if i > len(node.children) - 1:
                i = len(node.children) - 1

        found = self._delete(node.children[i], key)

        # after deletion we may need to update internal keys that were acting
        # as separators equal to the deleted key
        if found:
            self._update_internal_keys(node, key)

        return found

    def _update_internal_keys(self, node, old_key):
        """
        After deleting *old_key* from a leaf, walk the internal nodes and
        replace any separator that equals *old_key* with the new minimum key
        of the right subtree.
        """
        for i, k in enumerate(node.keys):
            if k == old_key:
                # find the leftmost leaf in the right subtree
                successor = node.children[i + 1]
                while not successor.is_leaf:
                    successor = successor.children[0]
                if successor.keys:
                    node.keys[i] = successor.keys[0]
                break

    def _fill_child(self, node, index):
        """
        Ensure child at *index* has more than _min_keys keys by borrowing
        from a sibling or merging.
        """
        if index > 0 and len(node.children[index - 1].keys) > self._min_keys:
            self._borrow_from_prev(node, index)
        elif index < len(node.children) - 1 and len(node.children[index + 1].keys) > self._min_keys:
            self._borrow_from_next(node, index)
        else:
            # merge with a sibling
            if index < len(node.children) - 1:
                self._merge(node, index)
            else:
                self._merge(node, index - 1)

    def _borrow_from_prev(self, node, index):
        """Borrow a key from the left sibling to prevent underflow."""
        child = node.children[index]
        left_sibling = node.children[index - 1]

        if child.is_leaf:
            # move the last key/value of the left sibling to the front of child
            child.keys.insert(0, left_sibling.keys.pop())
            child.values.insert(0, left_sibling.values.pop())
            # update the separator in the parent
            node.keys[index - 1] = child.keys[0]
        else:
            # move the separator key down from parent into child
            child.keys.insert(0, node.keys[index - 1])
            # move the last key of left sibling up to be the new separator
            node.keys[index - 1] = left_sibling.keys.pop()
            # move the last child pointer of left sibling to child
            child.children.insert(0, left_sibling.children.pop())

    def _borrow_from_next(self, node, index):
        """Borrow a key from the right sibling to prevent underflow."""
        child = node.children[index]
        right_sibling = node.children[index + 1]

        if child.is_leaf:
            # move the first key/value of the right sibling to the end of child
            child.keys.append(right_sibling.keys.pop(0))
            child.values.append(right_sibling.values.pop(0))
            # update the separator in the parent
            node.keys[index] = right_sibling.keys[0]
        else:
            # move the separator key down from parent into child
            child.keys.append(node.keys[index])
            # move the first key of right sibling up to be the new separator
            node.keys[index] = right_sibling.keys.pop(0)
            # move the first child pointer of right sibling to child
            child.children.append(right_sibling.children.pop(0))

    def _merge(self, node, index):
        """
        Merge the child at *index* with the child at *index + 1*.
        The separator key in the parent is consumed.
        """
        left = node.children[index]
        right = node.children[index + 1]

        if left.is_leaf:
            # for leaves: concatenate keys/values, fix linked list
            left.keys.extend(right.keys)
            left.values.extend(right.values)
            left.next = right.next
        else:
            # for internal nodes: pull the separator down, then merge
            left.keys.append(node.keys[index])
            left.keys.extend(right.keys)
            left.children.extend(right.children)

        # remove the separator and the right child from the parent
        node.keys.pop(index)
        node.children.pop(index + 1)

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, key, new_value):
        """Update the value associated with *key*. Return True if found."""
        node = self.root
        while not node.is_leaf:
            i = 0
            while i < len(node.keys) and key >= node.keys[i]:
                i += 1
            node = node.children[i]
        for i, k in enumerate(node.keys):
            if k == key:
                node.values[i] = new_value
                return True
        return False

    # ------------------------------------------------------------------
    # Range Query
    # ------------------------------------------------------------------

    def range_query(self, start_key, end_key):
        """
        Return all (key, value) pairs where start_key <= key <= end_key.
        Uses the leaf linked-list for efficient sequential access.
        """
        # navigate to the leaf that might contain start_key
        node = self.root
        while not node.is_leaf:
            i = 0
            while i < len(node.keys) and start_key >= node.keys[i]:
                i += 1
            node = node.children[i]

        result = []
        while node is not None:
            for i, k in enumerate(node.keys):
                if k > end_key:
                    return result
                if k >= start_key:
                    result.append((k, node.values[i]))
            node = node.next
        return result

    # ------------------------------------------------------------------
    # Get All
    # ------------------------------------------------------------------

    def get_all(self):
        """Return all (key, value) pairs via in-order leaf traversal."""
        result = []
        node = self.root
        # find the leftmost leaf
        while not node.is_leaf:
            node = node.children[0]
        while node is not None:
            for i, k in enumerate(node.keys):
                result.append((k, node.values[i]))
            node = node.next
        return result

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def count(self):
        """Return the number of keys stored in the tree (O(1))."""
        return self._size

    def min_key(self):
        """Return the minimum key, or None if the tree is empty."""
        node = self.root
        while not node.is_leaf:
            node = node.children[0]
        return node.keys[0] if node.keys else None

    def max_key(self):
        """Return the maximum key, or None if the tree is empty."""
        node = self.root
        while not node.is_leaf:
            node = node.children[-1]
        return node.keys[-1] if node.keys else None

    def sum_keys(self):
        """Return the sum of all keys in the tree."""
        return sum(k for k, _ in self.get_all())

    # ------------------------------------------------------------------
    # Persistence / cloning
    # ------------------------------------------------------------------

    def to_dict(self):
        """
        Serialize the tree as sorted key-value pairs.

        The B+ Tree remains the authoritative storage structure in memory; this
        representation is only used to clone or persist committed state.
        """
        return {
            "order": self.order,
            "records": [
                {"key": copy.deepcopy(key), "value": copy.deepcopy(value)}
                for key, value in self.get_all()
            ],
        }

    @classmethod
    def from_dict(cls, payload):
        """Rebuild a B+ Tree from a serialized representation."""
        tree = cls(order=payload["order"])
        for row in payload.get("records", []):
            tree.insert(copy.deepcopy(row["key"]), copy.deepcopy(row["value"]))
        return tree

    def clone(self):
        """Return a deep logical copy of the tree."""
        return self.from_dict(self.to_dict())

    # ------------------------------------------------------------------
    # Visualization (Graphviz)
    # ------------------------------------------------------------------

    def visualize_tree(self, filename=None, view_graph=False):
        """
        Generate and return a Graphviz Digraph object representing the tree.

        Parameters
        ----------
        filename : str, optional
            If provided, render the graph to this file (PNG).
        view_graph : bool, default False
            If True and *filename* is given, open the rendered image.

        Returns
        -------
        graphviz.Digraph
        """
        if Digraph is None:
            raise ImportError(
                "The 'graphviz' package is required for visualization. "
                "Install it with: pip install graphviz"
            )
        dot = Digraph(comment="B+ Tree", format="png")
        dot.attr(rankdir="TB", bgcolor="white")
        dot.attr("node", shape="plaintext", fontname="Courier", fontsize="10")
        dot.attr("edge", color="#555555")

        if not self.root.keys:
            dot.node("empty", "Empty Tree")
        else:
            self._add_nodes(dot, self.root, "0")
            self._add_leaf_links(dot)

        if filename:
            dot.render(filename, cleanup=True, view=view_graph)
        return dot

    @staticmethod
    def _html_table(cells, bg_color, ports=None):
        """Build an HTML-like label for a Graphviz node."""
        rows = ""
        for i, cell in enumerate(cells):
            port = f' PORT="{ports[i]}"' if ports else ""
            rows += f'<TD{port} BGCOLOR="{bg_color}" BORDER="1">{cell}</TD>'
        return f'<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0"><TR>{rows}</TR></TABLE>>'

    def _add_nodes(self, dot, node, node_id):
        """Recursively add nodes to the Graphviz Digraph with HTML-table labels."""
        if node.is_leaf:
            cells = [str(k) for k in node.keys]
            ports = [f"f{i}" for i in range(len(node.keys))]
            label = self._html_table(cells, "#D5F5E3", ports)  # green for leaves
            dot.node(node_id, label)
        else:
            cells, ports = [], []
            for i in range(len(node.keys)):
                cells.append(" ")
                ports.append(f"c{i}")
                cells.append(str(node.keys[i]))
                ports.append(f"f{i}")
            cells.append(" ")
            ports.append(f"c{len(node.keys)}")
            label = self._html_table(cells, "#E8F4FD", ports)  # blue for internals
            dot.node(node_id, label)

        if not node.is_leaf:
            for i, child in enumerate(node.children):
                child_id = f"{node_id}_{i}"
                self._add_nodes(dot, child, child_id)
                dot.edge(f"{node_id}:c{i}", child_id)

    def _add_leaf_links(self, dot):
        """Add dashed linked-list arrows between adjacent leaf nodes."""
        leaf_ids = []
        self._collect_leaf_ids(self.root, "0", leaf_ids)
        for i in range(len(leaf_ids) - 1):
            dot.edge(leaf_ids[i], leaf_ids[i + 1],
                     style="dashed", color="#E74C3C", constraint="false")

    def _collect_leaf_ids(self, node, node_id, leaf_ids):
        """Collect Graphviz IDs of leaf nodes in left-to-right order."""
        if node.is_leaf:
            leaf_ids.append(node_id)
        else:
            for i, child in enumerate(node.children):
                self._collect_leaf_ids(child, f"{node_id}_{i}", leaf_ids)

    # ------------------------------------------------------------------
    # Helpers / dunder methods
    # ------------------------------------------------------------------

    def __len__(self):
        return self._size

    def __contains__(self, key):
        return self.search(key) is not None

    def __repr__(self):
        return f"BPlusTree(order={self.order}, size={self._size})"
