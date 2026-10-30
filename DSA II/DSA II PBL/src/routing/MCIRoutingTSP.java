package routing;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

/**
 * Reduced-cost-matrix branch and bound; worst-case O(n! n^2) time and O(n^3) stack-held matrix space.
 */
public final class MCIRoutingTSP {
    private static final long INF = Long.MAX_VALUE / 8;
    private final int[][] costs;
    private final String[] locations;
    private final int size;
    private long bestCost = INF;
    private int[] bestSuccessor;
    private long prunedBranches;
    private long exploredNodes;

    public static final class Result {
        private final List<String> tour;
        private final long totalLatency;
        private final long prunedBranches;
        private final long exploredNodes;
        private final long totalPermutations;
        private Result(List<String> tour, long totalLatency, long prunedBranches,
                       long exploredNodes, long totalPermutations) {
            this.tour = List.copyOf(tour); this.totalLatency = totalLatency;
            this.prunedBranches = prunedBranches; this.exploredNodes = exploredNodes;
            this.totalPermutations = totalPermutations;
        }
        public List<String> getTour() { return tour; }
        public long getTotalLatency() { return totalLatency; }
        public long getPrunedBranches() { return prunedBranches; }
        public long getExploredNodes() { return exploredNodes; }
        public long getTotalPermutations() { return totalPermutations; }
        public boolean hasTour() { return !tour.isEmpty(); }
    }

    public MCIRoutingTSP(int[][] costMatrix) { this(costMatrix, null); }

    public MCIRoutingTSP(int[][] costMatrix, String[] locationNames) {
        Objects.requireNonNull(costMatrix, "costMatrix");
        if (costMatrix.length < 2) throw new IllegalArgumentException("At least two MCI locations are required.");
        size = costMatrix.length;
        if (locationNames != null && locationNames.length != size)
            throw new IllegalArgumentException("Location names must match the cost matrix size.");
        locations = locationNames == null ? new String[size] : locationNames.clone();
        for (int i = 0; i < size; i++) {
            if (costMatrix[i] == null || costMatrix[i].length != size)
                throw new IllegalArgumentException("Cost matrix must be square.");
            if (locations[i] == null) locations[i] = "Scene " + i;
            if (locations[i].isBlank()) throw new IllegalArgumentException("Location names cannot be blank.");
            for (int j = 0; j < size; j++)
                if (i != j && costMatrix[i][j] < 0 && costMatrix[i][j] != Integer.MAX_VALUE)
                    throw new IllegalArgumentException("Travel costs must be non-negative or Integer.MAX_VALUE for no edge.");
        }
        costs = new int[size][size];
        for (int i = 0; i < size; i++) costs[i] = costMatrix[i].clone();
    }

    /** Solves exactly from location 0; worst-case O(n! n^2) time and O(n^3) space. */
    public Result solve() {
        bestCost = INF;
        prunedBranches = 0;
        exploredNodes = 0;
        bestSuccessor = null;
        int[] path = new int[size];
        boolean[] visited = new boolean[size];
        path[0] = 0;
        visited[0] = true;
        search(path, visited, 1, 0);

        List<String> tour = new ArrayList<>();
        if (bestSuccessor != null) {
            int node = 0;
            for (int step = 0; step < size; step++) {
                tour.add(locations[node]);
                node = bestSuccessor[node];
            }
            tour.add(locations[0]);
        }
        Result result = new Result(tour, bestCost == INF ? -1 : bestCost, prunedBranches,
            exploredNodes, factorialSaturated(size - 1));
        if (result.hasTour()) {
            System.out.println("Optimal MCI tour: " + String.join(" -> ", result.getTour()));
            System.out.println("Total circuit latency: " + result.getTotalLatency() + " minutes");
        } else System.out.println("No complete circuit is available for this road matrix.");
        System.out.printf("Pruned branches: %d / %d anchored permutations (%d search nodes).%n",
            result.getPrunedBranches(), result.getTotalPermutations(), result.getExploredNodes());
        return result;
    }

    public void printSolution() {
        Result result = solve();
        if (result.hasTour()) {
            System.out.println("Optimal MCI tour: " + String.join(" -> ", result.getTour()));
            System.out.println("Total circuit latency: " + result.getTotalLatency() + " minutes");
        } else System.out.println("No complete circuit is available for this road matrix.");
        System.out.printf("Search statistics: %d pruned branches, %d search nodes, %d anchored permutations.%n",
                result.getPrunedBranches(), result.getExploredNodes(), result.getTotalPermutations());
    }

    private void search(int[] path, boolean[] visited, int pathLength, long currentCost) {
        exploredNodes++;
        if (pathLength == size) {
            int returnCost = costs[path[size - 1]][0];
            if (returnCost != Integer.MAX_VALUE && currentCost + returnCost < bestCost) {
                bestCost = currentCost + returnCost;
                bestSuccessor = new int[size];
                for (int index = 0; index < size - 1; index++) bestSuccessor[path[index]] = path[index + 1];
                bestSuccessor[path[size - 1]] = 0;
            } else prunedBranches++;
            return;
        }
        long lowerBound = reducedCostLowerBound(path, visited, pathLength, currentCost);
        if (lowerBound >= bestCost) { prunedBranches++; return; }

        int current = path[pathLength - 1];
        List<Integer> candidates = new ArrayList<>();
        for (int node = 1; node < size; node++)
            if (!visited[node] && costs[current][node] != Integer.MAX_VALUE) candidates.add(node);
        candidates.sort((first, second) -> Integer.compare(costs[current][first], costs[current][second]));
        if (candidates.isEmpty()) { prunedBranches++; return; }
        for (int next : candidates) {
            long nextCost = currentCost + costs[current][next];
            if (nextCost >= bestCost) { prunedBranches++; continue; }
            path[pathLength] = next;
            visited[next] = true;
            search(path, visited, pathLength + 1, nextCost);
            visited[next] = false;
        }
    }

    private long reducedCostLowerBound(int[] path, boolean[] visited, int pathLength, long currentCost) {
        int current = path[pathLength - 1];
        long[][] residual = new long[size][size];
        for (int row = 0; row < size; row++) {
            for (int col = 0; col < size; col++) {
                residual[row][col] = row == col || costs[row][col] == Integer.MAX_VALUE ? INF : costs[row][col];
                if (visited[row] && row != current) residual[row][col] = INF;
                if (visited[col] && col != 0) residual[row][col] = INF;
            }
        }
        if (pathLength < size) residual[current][0] = INF;
        return safeAdd(currentCost, reduce(residual));
    }

    private long reduce(long[][] matrix) {
        long reduction = 0;
        for (int row = 0; row < size; row++) {
            long minimum = INF;
            for (int col = 0; col < size; col++) minimum = Math.min(minimum, matrix[row][col]);
            if (minimum != INF && minimum != 0) {
                reduction = safeAdd(reduction, minimum);
                for (int col = 0; col < size; col++) if (matrix[row][col] != INF) matrix[row][col] -= minimum;
            }
        }
        for (int col = 0; col < size; col++) {
            long minimum = INF;
            for (int row = 0; row < size; row++) minimum = Math.min(minimum, matrix[row][col]);
            if (minimum != INF && minimum != 0) {
                reduction = safeAdd(reduction, minimum);
                for (int row = 0; row < size; row++) if (matrix[row][col] != INF) matrix[row][col] -= minimum;
            }
        }
        return reduction;
    }

    private static long safeAdd(long first, long second) {
        if (first >= INF || second >= INF || first > INF - second) return INF;
        return first + second;
    }
    private static long factorialSaturated(int value) {
        long result = 1;
        for (int i = 2; i <= value; i++) {
            if (result > Long.MAX_VALUE / i) return Long.MAX_VALUE;
            result *= i;
        }
        return result;
    }
}