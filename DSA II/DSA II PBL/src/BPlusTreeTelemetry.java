import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class BPlusTreeTelemetry {
    private static final int M = 4;

    public static class TelemetryRecord {
        public long timestamp;
        public String entityId;
        public double latitude;
        public double longitude;
        public String status;

        public TelemetryRecord(long timestamp, String entityId, double lat, double lon, String status) {
            this.timestamp = timestamp;
            this.entityId = entityId;
            this.latitude = lat;
            this.longitude = lon;
            this.status = status;
        }

        @Override
        public String toString() {
            return String.format("[TS: %d] %s | Pos: (%.4f, %.4f) | Status: %s",
                    timestamp, entityId, latitude, longitude, status);
        }
    }

    public static abstract class Node {
        List<Long> keys = new ArrayList<>();
        abstract boolean isLeaf();
    }

    public static class InternalNode extends Node {
        List<Node> children = new ArrayList<>();
        @Override boolean isLeaf() { return false; }
    }

    public static class LeafNode extends Node {
        List<TelemetryRecord> records = new ArrayList<>();
        LeafNode next = null;
        LeafNode prev = null;
        @Override boolean isLeaf() { return true; }
    }

    private Node root = new LeafNode();

    public void insert(TelemetryRecord record) {
        LeafNode leaf = findLeaf(root, record.timestamp);
        insertIntoLeaf(leaf, record);
        if (leaf.keys.size() >= M) splitLeaf(leaf);
    }

    private LeafNode findLeaf(Node current, long key) {
        if (current.isLeaf()) return (LeafNode) current;
        InternalNode internal = (InternalNode) current;
        int idx = 0;
        while (idx < internal.keys.size() && key >= internal.keys.get(idx)) idx++;
        return findLeaf(internal.children.get(idx), key);
    }

    private void insertIntoLeaf(LeafNode leaf, TelemetryRecord record) {
        int idx = Collections.binarySearch(leaf.keys, record.timestamp);
        if (idx < 0) idx = -(idx + 1);
        leaf.keys.add(idx, record.timestamp);
        leaf.records.add(idx, record);
    }

    private void splitLeaf(LeafNode leaf) {
        int mid = leaf.keys.size() / 2;
        LeafNode sibling = new LeafNode();
        sibling.keys.addAll(leaf.keys.subList(mid, leaf.keys.size()));
        sibling.records.addAll(leaf.records.subList(mid, leaf.records.size()));
        leaf.keys.subList(mid, leaf.keys.size()).clear();
        leaf.records.subList(mid, leaf.records.size()).clear();

        sibling.next = leaf.next;
        if (sibling.next != null) sibling.next.prev = sibling;
        leaf.next = sibling;
        sibling.prev = leaf;

        long promoKey = sibling.keys.get(0);
        if (leaf == root) {
            InternalNode newRoot = new InternalNode();
            newRoot.keys.add(promoKey);
            newRoot.children.add(leaf);
            newRoot.children.add(sibling);
            this.root = newRoot;
        } else {
            insertParent(leaf, promoKey, sibling);
        }
    }

    private void insertParent(Node left, long key, Node right) {
        InternalNode parent = findParent(root, left);
        int idx = 0;
        while (idx < parent.keys.size() && key > parent.keys.get(idx)) idx++;
        parent.keys.add(idx, key);
        parent.children.add(idx + 1, right);
        if (parent.keys.size() >= M) splitInternal(parent);
    }

    private InternalNode findParent(Node current, Node target) {
        if (current.isLeaf() || ((InternalNode) current).children.contains(target)) {
            return current.isLeaf() ? null : (InternalNode) current;
        }
        for (Node child : ((InternalNode) current).children) {
            InternalNode res = findParent(child, target);
            if (res != null) return res;
        }
        return null;
    }

    private void splitInternal(InternalNode node) {
        int mid = node.keys.size() / 2;
        long upKey = node.keys.get(mid);
        InternalNode sibling = new InternalNode();
        sibling.keys.addAll(node.keys.subList(mid + 1, node.keys.size()));
        sibling.children.addAll(node.children.subList(mid + 1, node.children.size()));
        node.keys.subList(mid, node.keys.size()).clear();
        node.children.subList(mid + 1, node.children.size()).clear();

        if (node == root) {
            InternalNode newRoot = new InternalNode();
            newRoot.keys.add(upKey);
            newRoot.children.add(node);
            newRoot.children.add(sibling);
            this.root = newRoot;
        } else {
            insertParent(node, upKey, sibling);
        }
    }

    public List<TelemetryRecord> rangeQuery(long startTS, long endTS) {
        List<TelemetryRecord> results = new ArrayList<>();
        LeafNode curr = findLeaf(root, startTS);
        while (curr != null) {
            for (int i = 0; i < curr.keys.size(); i++) {
                long ts = curr.keys.get(i);
                if (ts >= startTS && ts <= endTS) results.add(curr.records.get(i));
                if (ts > endTS) return results;
            }
            curr = curr.next;
        }
        return results;
    }
}
