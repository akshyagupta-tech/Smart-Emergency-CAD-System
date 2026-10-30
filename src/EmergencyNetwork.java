import java.util.*;

public class EmergencyNetwork {
    public static class Edge implements Comparable<Edge> {
        public String u, v;
        public int weight;

        public Edge(String u, String v, int weight) {
            this.u = u;
            this.v = v;
            this.weight = weight;
        }

        @Override
        public int compareTo(Edge o) {
            return Integer.compare(this.weight, o.weight);
        }
    }

    private Map<String, List<Edge>> adjList;
    private List<Edge> allEdges;

    public EmergencyNetwork() {
        adjList = new HashMap<>();
        allEdges = new ArrayList<>();
    }

    public void addIntersection(String id) {
        adjList.putIfAbsent(id, new ArrayList<>());
    }

    public void addRoadSegment(String u, String v, int weight) {
        addIntersection(u);
        addIntersection(v);
        Edge e1 = new Edge(u, v, weight);
        Edge e2 = new Edge(v, u, weight);
        adjList.get(u).add(e1);
        adjList.get(v).add(e2);
        allEdges.add(e1);
    }

    public void findShortestPath(String start, String target) {
        Map<String, Integer> dist = new HashMap<>();
        Map<String, String> prev = new HashMap<>();
        PriorityQueue<String> pq = new PriorityQueue<>(Comparator.comparingInt(dist::get));

        for (String node : adjList.keySet()) {
            dist.put(node, Integer.MAX_VALUE);
            prev.put(node, null);
        }

        dist.put(start, 0);
        pq.add(start);

        while (!pq.isEmpty()) {
            String curr = pq.poll();
            if (curr.equals(target)) break;

            for (Edge edge : adjList.get(curr)) {
                int newDist = dist.get(curr) + edge.weight;
                if (newDist < dist.get(edge.v)) {
                    dist.put(edge.v, newDist);
                    prev.put(edge.v, curr);
                    pq.remove(edge.v);
                    pq.add(edge.v);
                }
            }
        }

        List<String> path = new ArrayList<>();
        for (String at = target; at != null; at = prev.get(at)) {
            path.add(at);
        }
        Collections.reverse(path);

        System.out.printf("Optimal Route: %s%n", String.join(" -> ", path));
        System.out.printf("Total Transit Time: %d minutes%n", dist.get(target));
    }

    public void computeKruskalMST() {
        Collections.sort(allEdges);
        Map<String, String> parent = new HashMap<>();
        for (String node : adjList.keySet()) parent.put(node, node);

        List<Edge> mst = new ArrayList<>();
        int totalWeight = 0;

        for (Edge e : allEdges) {
            String rootU = find(parent, e.u);
            String rootV = find(parent, e.v);
            if (!rootU.equals(rootV)) {
                mst.add(e);
                totalWeight += e.weight;
                parent.put(rootU, rootV);
            }
        }

        System.out.println("Comms Infrastructure MST Total Latency: " + totalWeight + " ms");
        for (Edge e : mst) {
            System.out.printf("  Link: %s <---> %s (Cost: %d)%n", e.u, e.v, e.weight);
        }
    }

    private String find(Map<String, String> parent, String node) {
        if (parent.get(node).equals(node)) return node;
        parent.put(node, find(parent, parent.get(node)));
        return parent.get(node);
    }
}
