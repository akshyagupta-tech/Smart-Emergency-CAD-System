public class MCIRoutingTSP {
    private static final int INF = Integer.MAX_VALUE;
    private int n;
    private int[][] matrix;
    private boolean[] visited;
    private int bestCost = INF;
    private int[] bestTour;

    public MCIRoutingTSP(int[][] matrix) {
        this.n = matrix.length;
        this.matrix = matrix;
        this.visited = new boolean[n];
        this.bestTour = new int[n + 1];
    }

    public void solve() {
        int[] currPath = new int[n + 1];
        visited[0] = true;
        currPath[0] = 0;
        int initialBound = calculateInitialBound();

        branch(1, 0, initialBound, currPath);

        System.out.printf("Optimal MCI Tour Latency: %d minutes%n", bestCost);
        System.out.print("Ordered Pickup Tour: ");
        for (int i = 0; i <= n; i++) {
            System.out.print(bestTour[i] + (i < n ? " -> " : "\n"));
        }
    }

    private void branch(int level, int currentCost, int currentBound, int[] path) {
        if (level == n) {
            if (matrix[path[level - 1]][path[0]] != INF) {
                int totalCost = currentCost + matrix[path[level - 1]][path[0]];
                if (totalCost < bestCost) {
                    bestCost = totalCost;
                    System.arraycopy(path, 0, bestTour, 0, n);
                    bestTour[n] = path[0];
                }
            }
            return;
        }

        for (int next = 0; next < n; next++) {
            if (!visited[next] && matrix[path[level - 1]][next] != INF) {
                int nextCost = currentCost + matrix[path[level - 1]][next];
                if (nextCost < bestCost) {
                    visited[next] = true;
                    path[level] = next;
                    branch(level + 1, nextCost, currentBound, path);
                    visited[next] = false;
                }
            }
        }
    }

    private int calculateInitialBound() {
        int bound = 0;
        for (int i = 0; i < n; i++) {
            int min = INF;
            for (int j = 0; j < n; j++) {
                if (i != j && matrix[i][j] < min) min = matrix[i][j];
            }
            if (min != INF) bound += min;
        }
        return bound;
    }
}
