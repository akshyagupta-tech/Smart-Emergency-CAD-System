import java.util.ArrayList;
import java.util.List;

public class KnapsackPayload {
    public static class MedicalItem {
        String name;
        int weightKg;
        int utility;

        public MedicalItem(String name, int weightKg, int utility) {
            this.name = name;
            this.weightKg = weightKg;
            this.utility = utility;
        }
    }

    public static void optimizePayload(List<MedicalItem> items, int maxCapacity) {
        int n = items.size();
        int[][] dp = new int[n + 1][maxCapacity + 1];

        for (int i = 1; i <= n; i++) {
            MedicalItem item = items.get(i - 1);
            for (int w = 0; w <= maxCapacity; w++) {
                if (item.weightKg <= w) {
                    dp[i][w] = Math.max(dp[i - 1][w], dp[i - 1][w - item.weightKg] + item.utility);
                } else {
                    dp[i][w] = dp[i - 1][w];
                }
            }
        }

        List<String> selected = new ArrayList<>();
        int remainingWeight = maxCapacity;
        for (int i = n; i > 0; i--) {
            if (dp[i][remainingWeight] != dp[i - 1][remainingWeight]) {
                MedicalItem item = items.get(i - 1);
                selected.add(String.format("%s (%dkg, Score: %d)", item.name, item.weightKg, item.utility));
                remainingWeight -= item.weightKg;
            }
        }

        System.out.printf("Max Life-Saving Utility: %d%n", dp[n][maxCapacity]);
        System.out.printf("Payload Weight Consumed: %d / %d kg%n", (maxCapacity - remainingWeight), maxCapacity);
        System.out.println("Selected Equipment Packages:");
        for (String s : selected) {
            System.out.println("  • " + s);
        }
    }
}
