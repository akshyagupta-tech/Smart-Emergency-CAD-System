package storage;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

/** Order-4 B+ tree (up to 4 children per internal node); insert O(log n), range query O(log n + k). */
public final class BPlusTreeTelemetry {
    private static final int ORDER = 4;

    public static final class TelemetryRecord {
        private final long timestamp;
        private final String vehicleId;
        private final double lat;
        private final double lon;
        private final String status;
        public TelemetryRecord(long timestamp, String vehicleId, double lat, double lon, String status) {
            if (timestamp < 0) throw new IllegalArgumentException("Timestamp cannot be negative.");
            if (vehicleId == null || vehicleId.isBlank()) throw new IllegalArgumentException("Vehicle ID cannot be blank.");
            if (!Double.isFinite(lat) || lat < -90 || lat > 90) throw new IllegalArgumentException("Latitude must be from -90 to 90.");
            if (!Double.isFinite(lon) || lon < -180 || lon > 180) throw new IllegalArgumentException("Longitude must be from -180 to 180.");
            if (status == null || status.isBlank()) throw new IllegalArgumentException("Status cannot be blank.");
            this.timestamp = timestamp; this.vehicleId = vehicleId.trim(); this.lat = lat; this.lon = lon;
            this.status = status.trim();
        }
        public long getTimestamp() { return timestamp; }
        public String getVehicleId() { return vehicleId; }
        public double getLat() { return lat; }
        public double getLon() { return lon; }
        public String getStatus() { return status; }
        @Override public String toString() {
            return String.format("[%d] %s | (%.5f, %.5f) | %s", timestamp, vehicleId, lat, lon, status);
        }
    }

    public abstract static class Node {
        protected final List<Long> keys = new ArrayList<>();
        public List<Long> getKeys() { return List.copyOf(keys); }
        abstract boolean isLeaf();
    }
    public static final class InternalNode extends Node {
        private final List<Node> children = new ArrayList<>();
        public List<Node> getChildren() { return List.copyOf(children); }
        @Override boolean isLeaf() { return false; }
    }
    public static final class LeafNode extends Node {
        private final List<TelemetryRecord> records = new ArrayList<>();
        private LeafNode next;
        private LeafNode prev;
        public List<TelemetryRecord> getRecords() { return List.copyOf(records); }
        public LeafNode getNext() { return next; }
        public LeafNode getPrev() { return prev; }
        @Override boolean isLeaf() { return true; }
    }

    private Node root = new LeafNode();
    private int recordCount;

    public void insert(TelemetryRecord record) {
        Objects.requireNonNull(record, "record");
        LeafNode leaf = findLeaf(root, record.timestamp, false);
        int index = upperBound(leaf.keys, record.timestamp);
        leaf.keys.add(index, record.timestamp);
        leaf.records.add(index, record);
        recordCount++;
        if (leaf.keys.size() >= ORDER) splitLeaf(leaf);
    }

    /** Returns an inclusive timestamp interval in O(log n + k) time and O(k) result space. */
    public List<TelemetryRecord> rangeQuery(long startTimestamp, long endTimestamp) {
        if (startTimestamp < 0 || endTimestamp < 0) throw new IllegalArgumentException("Timestamps cannot be negative.");
        if (startTimestamp > endTimestamp) throw new IllegalArgumentException("Start timestamp must not exceed end timestamp.");
        List<TelemetryRecord> results = new ArrayList<>();
        LeafNode leaf = findLeaf(root, startTimestamp, true);
        while (leaf != null) {
            for (int i = 0; i < leaf.keys.size(); i++) {
                long timestamp = leaf.keys.get(i);
                if (timestamp > endTimestamp) return results;
                if (timestamp >= startTimestamp) results.add(leaf.records.get(i));
            }
            leaf = leaf.next;
        }
        return results;
    }

    public int size() { return recordCount; }

    private LeafNode findLeaf(Node current, long key, boolean lowerBound) {
        if (current.isLeaf()) return (LeafNode) current;
        InternalNode internal = (InternalNode) current;
        int childIndex = 0;
        while (childIndex < internal.keys.size()
                && (lowerBound ? key > internal.keys.get(childIndex) : key >= internal.keys.get(childIndex))) childIndex++;
        return findLeaf(internal.children.get(childIndex), key, lowerBound);
    }

    private void splitLeaf(LeafNode leaf) {
        int middle = leaf.keys.size() / 2;
        LeafNode sibling = new LeafNode();
        sibling.keys.addAll(leaf.keys.subList(middle, leaf.keys.size()));
        sibling.records.addAll(leaf.records.subList(middle, leaf.records.size()));
        leaf.keys.subList(middle, leaf.keys.size()).clear();
        leaf.records.subList(middle, leaf.records.size()).clear();
        sibling.next = leaf.next;
        if (sibling.next != null) sibling.next.prev = sibling;
        sibling.prev = leaf;
        leaf.next = sibling;
        insertParent(leaf, sibling.keys.get(0), sibling);
    }

    private void insertParent(Node left, long separator, Node right) {
        if (left == root) {
            InternalNode newRoot = new InternalNode();
            newRoot.keys.add(separator);
            newRoot.children.add(left);
            newRoot.children.add(right);
            root = newRoot;
            return;
        }
        InternalNode parent = findParent(root, left);
        if (parent == null) throw new IllegalStateException("B+ tree parent link could not be located.");
        int keyIndex = upperBound(parent.keys, separator);
        parent.keys.add(keyIndex, separator);
        parent.children.add(keyIndex + 1, right);
        if (parent.keys.size() >= ORDER) splitInternal(parent);
    }

    private void splitInternal(InternalNode node) {
        int middle = node.keys.size() / 2;
        long promoted = node.keys.get(middle);
        InternalNode sibling = new InternalNode();
        sibling.keys.addAll(node.keys.subList(middle + 1, node.keys.size()));
        sibling.children.addAll(node.children.subList(middle + 1, node.children.size()));
        node.keys.subList(middle, node.keys.size()).clear();
        node.children.subList(middle + 1, node.children.size()).clear();
        insertParent(node, promoted, sibling);
    }

    private InternalNode findParent(Node current, Node target) {
        if (current.isLeaf()) return null;
        InternalNode internal = (InternalNode) current;
        if (internal.children.contains(target)) return internal;
        for (Node child : internal.children) {
            InternalNode parent = findParent(child, target);
            if (parent != null) return parent;
        }
        return null;
    }

    private static int upperBound(List<Long> values, long target) {
        int low = 0, high = values.size();
        while (low < high) {
            int middle = (low + high) >>> 1;
            if (values.get(middle) <= target) low = middle + 1;
            else high = middle;
        }
        return low;
    }
}