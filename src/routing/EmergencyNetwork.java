package routing;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.PriorityQueue;

/** Directed road graph; Dijkstra is O((V+E) log V), Kruskal is O(E log E). */
public final class EmergencyNetwork {
    public static final class Edge {
        private final String source;
        private final String target;
        private final double baseMinutes;
        private final double distanceKm;
        private final double speedLimit;
        private double congestionFactor = 1.0;
        private double waterFactorLow = 1.0;
        private double waterFactorHigh = 1.0;
        private long waterCycleNanos;
        private long waterProfileStarted;
        private boolean severed;

        private Edge(String source, String target, double baseMinutes, double distanceKm, double speedLimit) {
            this.source = source;
            this.target = target;
            this.baseMinutes = baseMinutes;
            this.distanceKm = distanceKm;
            this.speedLimit = speedLimit;
        }
        public String getSource() { return source; }
        public String getTarget() { return target; }
        public double getBaseMinutes() { return baseMinutes; }
        public double getWeightMinutes() { return severed ? Double.POSITIVE_INFINITY : baseMinutes * getCongestionFactor(); }
        public double getDistanceKm() { return distanceKm; }
        public double getSpeedLimit() { return speedLimit; }
        public double getCongestionFactor() { return congestionFactor * currentWaterFactor(); }
        public boolean isSevered() { return severed; }
        public boolean isPassable() { return !severed && Double.isFinite(getWeightMinutes()); }

        private double currentWaterFactor() {
            if (waterCycleNanos <= 0 || waterFactorLow == waterFactorHigh) return waterFactorLow;
            double phase = (double) ((System.nanoTime() - waterProfileStarted) % waterCycleNanos) / waterCycleNanos;
            return phase < 0.5
                    ? waterFactorLow + (waterFactorHigh - waterFactorLow) * phase * 2.0
                    : waterFactorHigh - (waterFactorHigh - waterFactorLow) * (phase - 0.5) * 2.0;
        }

        private void setWaterLoggingProfile(double low, double high, long cycleNanos) {
            waterFactorLow = low;
            waterFactorHigh = high;
            waterCycleNanos = cycleNanos;
            waterProfileStarted = System.nanoTime();
        }

        private void clearWaterLogging() { setWaterLoggingProfile(1.0, 1.0, 0); }
    }

    public static final class PathResult {
        private final List<String> path;
        private final double totalMinutes;
        private PathResult(List<String> path, double totalMinutes) {
            this.path = List.copyOf(path);
            this.totalMinutes = totalMinutes;
        }
        public List<String> getPath() { return path; }
        public double getTotalMinutes() { return totalMinutes; }
        public boolean isReachable() { return !path.isEmpty(); }
        @Override public String toString() {
            return isReachable() ? String.join(" -> ", path) + String.format(" (%.2f min)", totalMinutes)
                    : "No route available.";
        }
    }

    public static final class MstResult {
        private final List<Edge> edges;
        private final double totalLatency;
        private final boolean connected;
        private MstResult(List<Edge> edges, double totalLatency, boolean connected) {
            this.edges = List.copyOf(edges);
            this.totalLatency = totalLatency;
            this.connected = connected;
        }
        public List<Edge> getEdges() { return edges; }
        public double getTotalLatency() { return totalLatency; }
        public boolean isConnected() { return connected; }
    }

    private final Map<String, List<Edge>> adjacency = new LinkedHashMap<>();
    private final Map<String, Edge> directedEdges = new HashMap<>();
    private final java.util.Set<String> inactiveNodes = new java.util.HashSet<>();

    public void addNode(String node) {
        adjacency.computeIfAbsent(requireNode(node), ignored -> new ArrayList<>());
    }

    public void addRoadSegment(String u, String v, double baseMinutes, double distanceKm, double speedLimit) {
        String from = requireNode(u);
        String to = requireNode(v);
        if (from.equals(to)) throw new IllegalArgumentException("A road segment must connect distinct nodes.");
        requirePositive(baseMinutes, "baseMinutes");
        requirePositive(distanceKm, "distanceKm");
        requirePositive(speedLimit, "speedLimit");
        String key = edgeKey(from, to);
        if (directedEdges.containsKey(key)) throw new IllegalArgumentException("Road already exists: " + from + " -> " + to);
        Edge edge = new Edge(from, to, baseMinutes, distanceKm, speedLimit);
        adjacency.computeIfAbsent(from, ignored -> new ArrayList<>()).add(edge);
        adjacency.computeIfAbsent(to, ignored -> new ArrayList<>());
        directedEdges.put(key, edge);
    }

    public void updateCongestion(String u, String v, double congestionMultiplier) {
        if (!Double.isFinite(congestionMultiplier) || congestionMultiplier < 1.0)
            throw new IllegalArgumentException("Congestion multiplier must be finite and at least 1.0.");
        Edge edge = directedEdges.get(edgeKey(requireNode(u), requireNode(v)));
        if (edge == null) throw new IllegalArgumentException("Directed road does not exist: " + u + " -> " + v);
        edge.congestionFactor = congestionMultiplier;
    }

    public void severEdge(String u, String v) { requireEdge(u, v).severed = true; }

    public void restoreEdge(String u, String v) {
        Edge edge = requireEdge(u, v);
        edge.severed = false;
        edge.congestionFactor = 1.0;
        edge.clearWaterLogging();
    }

    public void setWaterLoggingProfile(String u, String v, double lowFactor, double highFactor,
                                       long cycleSeconds) {
        if (!Double.isFinite(lowFactor) || lowFactor < 1.0 || !Double.isFinite(highFactor)
                || highFactor < lowFactor || cycleSeconds < 2)
            throw new IllegalArgumentException("Water logging profile must use finite factors >= 1 and a cycle of at least 2 seconds.");
        requireEdge(u, v).setWaterLoggingProfile(lowFactor, highFactor, cycleSeconds * 1_000_000_000L);
    }

    public void clearDisasterConditions() {
        for (Edge edge : directedEdges.values()) {
            edge.severed = false;
            edge.congestionFactor = 1.0;
            edge.clearWaterLogging();
        }
        inactiveNodes.clear();
    }

    public void setNodeActive(String node, boolean active) {
        String normalized = requireNode(node);
        if (!adjacency.containsKey(normalized)) throw new IllegalArgumentException("Unknown road node: " + normalized);
        if (active) inactiveNodes.remove(normalized);
        else inactiveNodes.add(normalized);
    }

    public boolean isNodeActive(String node) {
        String normalized = requireNode(node);
        return adjacency.containsKey(normalized) && !inactiveNodes.contains(normalized);
    }

    public boolean isEdgePassable(String u, String v) {
        Edge edge = requireEdge(u, v);
        return edge.isPassable() && isNodeActive(edge.source) && isNodeActive(edge.target);
    }

    public PathResult findShortestPath(String source, String destination) {
        String start = requireNode(source);
        String end = requireNode(destination);
        if (!adjacency.containsKey(start) || !adjacency.containsKey(end))
            throw new IllegalArgumentException("Source and destination must be registered road nodes.");
        if (!isNodeActive(start) || !isNodeActive(end))
            return new PathResult(List.of(), Double.POSITIVE_INFINITY);
        Map<String, Double> distances = new HashMap<>();
        Map<String, String> previous = new HashMap<>();
        PriorityQueue<String> queue = new PriorityQueue<>(Comparator.comparingDouble(distances::get));
        for (String node : adjacency.keySet()) distances.put(node, Double.POSITIVE_INFINITY);
        distances.put(start, 0.0);
        queue.add(start);
        while (!queue.isEmpty()) {
            String current = queue.poll();
            if (current.equals(end)) break;
            for (Edge edge : adjacency.get(current)) {
                if (!edge.isPassable() || !isNodeActive(edge.target)) continue;
                double candidate = distances.get(current) + edge.getWeightMinutes();
                if (candidate < distances.get(edge.target)) {
                    distances.put(edge.target, candidate);
                    previous.put(edge.target, current);
                    queue.remove(edge.target);
                    queue.add(edge.target);
                }
            }
        }
        if (!Double.isFinite(distances.get(end))) return new PathResult(List.of(), Double.POSITIVE_INFINITY);
        List<String> path = new ArrayList<>();
        for (String node = end; node != null; node = previous.get(node)) path.add(node);
        Collections.reverse(path);
        return new PathResult(path, distances.get(end));
    }

    /** Treats each directed road as an undirected physical link and retains its least-latency direction. */
    public MstResult computeKruskalMST() {
        Map<String, Edge> physicalLinks = new HashMap<>();
        for (Edge edge : directedEdges.values()) {
            if (!edge.isPassable() || !isNodeActive(edge.source) || !isNodeActive(edge.target)) continue;
            String key = edge.source.compareTo(edge.target) < 0
                    ? edge.source + "\u0000" + edge.target : edge.target + "\u0000" + edge.source;
            Edge prior = physicalLinks.get(key);
            if (prior == null || edge.getWeightMinutes() < prior.getWeightMinutes()) physicalLinks.put(key, edge);
        }
        List<Edge> sorted = new ArrayList<>(physicalLinks.values());
        sorted.sort(Comparator.comparingDouble(Edge::getWeightMinutes));
        List<String> activeNodes = getActiveNodes();
        DisjointSet dsu = new DisjointSet(activeNodes);
        List<Edge> chosen = new ArrayList<>();
        double latency = 0.0;
        for (Edge edge : sorted) {
            if (dsu.union(edge.source, edge.target)) {
                chosen.add(edge);
                latency += edge.getWeightMinutes();
            }
        }
        boolean connected = activeNodes.size() <= 1 || chosen.size() == activeNodes.size() - 1;
        return new MstResult(chosen, latency, connected);
    }

    public List<String> getNodes() { return List.copyOf(adjacency.keySet()); }

    public List<String> getActiveNodes() {
        List<String> nodes = new ArrayList<>();
        for (String node : adjacency.keySet()) if (!inactiveNodes.contains(node)) nodes.add(node);
        return List.copyOf(nodes);
    }

    /** Returns a detached list of directed edges in O(E) time and O(E) space. */
    public List<Edge> getEdges() {
        List<Edge> edges = new ArrayList<>(directedEdges.values());
        edges.sort(Comparator.comparing(Edge::getSource).thenComparing(Edge::getTarget));
        return List.copyOf(edges);
    }

    private Edge requireEdge(String u, String v) {
        String from = requireNode(u), to = requireNode(v);
        Edge edge = directedEdges.get(edgeKey(from, to));
        if (edge == null) throw new IllegalArgumentException("Directed road does not exist: " + from + " -> " + to);
        return edge;
    }

    private static String edgeKey(String u, String v) { return u + "\u0000" + v; }
    private static String requireNode(String value) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException("Road node cannot be blank.");
        return value.trim();
    }
    private static void requirePositive(double value, String name) {
        if (!Double.isFinite(value) || value <= 0.0) throw new IllegalArgumentException(name + " must be finite and positive.");
    }

    private static final class DisjointSet {
        private final Map<String, String> parent = new HashMap<>();
        private final Map<String, Integer> rank = new HashMap<>();
        private DisjointSet(Iterable<String> nodes) {
            for (String node : nodes) { parent.put(node, node); rank.put(node, 0); }
        }
        private String find(String node) {
            String root = parent.get(node);
            if (!Objects.equals(root, node)) parent.put(node, root = find(root));
            return root;
        }
        private boolean union(String first, String second) {
            String rootA = find(first), rootB = find(second);
            if (rootA.equals(rootB)) return false;
            int rankA = rank.get(rootA), rankB = rank.get(rootB);
            if (rankA < rankB) parent.put(rootA, rootB);
            else if (rankA > rankB) parent.put(rootB, rootA);
            else { parent.put(rootB, rootA); rank.put(rootA, rankA + 1); }
            return true;
        }
    }
}