package logistics;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

/** 0/1 payload optimization. Matrix DP is O(nW) time/space; rolling DP is O(nW) time/O(W) space. */
public final class KnapsackPayload {
    public static final int DISASTER_PAYLOAD_CAPACITY_KG = 30;

    public static final class MedicalItem {
        private final String name;
        private final int weightKg;
        private final int utilityScore;
        public MedicalItem(String name, int weightKg, int utilityScore) {
            if (name == null || name.isBlank()) throw new IllegalArgumentException("Item name cannot be blank.");
            if (weightKg <= 0) throw new IllegalArgumentException("Item weight must be positive.");
            if (utilityScore < 0) throw new IllegalArgumentException("Utility score cannot be negative.");
            this.name = name.trim(); this.weightKg = weightKg; this.utilityScore = utilityScore;
        }
        public String getName() { return name; }
        public int getWeightKg() { return weightKg; }
        public int getUtilityScore() { return utilityScore; }
        @Override public String toString() { return name + " (" + weightKg + " kg, utility " + utilityScore + ")"; }
    }

    public static final class Result {
        private final int maxUtility;
        private final int totalWeightKg;
        private final List<MedicalItem> selectedItems;
        private Result(int maxUtility, int totalWeightKg, List<MedicalItem> selectedItems) {
            this.maxUtility = maxUtility; this.totalWeightKg = totalWeightKg;
            this.selectedItems = List.copyOf(selectedItems);
        }
        public int getMaxUtility() { return maxUtility; }
        public int getTotalWeightKg() { return totalWeightKg; }
        public List<MedicalItem> getSelectedItems() { return selectedItems; }
    }

    public static Result optimizePayload(List<MedicalItem> items, int capacityW) {
        List<MedicalItem> safeItems = validate(items, capacityW);
        int[][] table = generateDpTable(safeItems, capacityW);
        List<MedicalItem> selected = new ArrayList<>();
        int remaining = capacityW;
        for (int i = safeItems.size(); i > 0; i--) {
            if (table[i][remaining] != table[i - 1][remaining]) {
                MedicalItem item = safeItems.get(i - 1);
                selected.add(item);
                remaining -= item.weightKg;
            }
        }
        Collections.reverse(selected);
        int weight = selected.stream().mapToInt(MedicalItem::getWeightKg).sum();
        return new Result(table[safeItems.size()][capacityW], weight, selected);
    }

    /** Returns the full DP table; O(nW) time and O(nW) space. */
    public static int[][] generateDpTable(List<MedicalItem> items, int capacityW) {
        List<MedicalItem> safeItems = validate(items, capacityW);
        int[][] dp = new int[safeItems.size() + 1][capacityW + 1];
        for (int i = 1; i <= safeItems.size(); i++) {
            MedicalItem item = safeItems.get(i - 1);
            for (int capacity = 0; capacity <= capacityW; capacity++) {
                dp[i][capacity] = dp[i - 1][capacity];
                if (item.weightKg <= capacity)
                    dp[i][capacity] = Math.max(dp[i][capacity], dp[i - 1][capacity - item.weightKg] + item.utilityScore);
            }
        }
        return dp;
    }

    /** Space-optimized optimum utility only; O(nW) time and O(W) space. */
    public static int optimizePayloadRolling(List<MedicalItem> items, int capacityW) {
        List<MedicalItem> safeItems = validate(items, capacityW);
        int[] dp = new int[capacityW + 1];
        for (MedicalItem item : safeItems)
            for (int capacity = capacityW; capacity >= item.weightKg; capacity--)
                dp[capacity] = Math.max(dp[capacity], dp[capacity - item.weightKg] + item.utilityScore);
        return dp[capacityW];
    }

    public static List<MedicalItem> disasterEmergencyPreset() {
        return List.of(
                new MedicalItem("Field Amputation & Hemostatic Kit", 6, 98),
                new MedicalItem("Portable Disaster Ventilator", 10, 95),
                new MedicalItem("Whole Blood Infusion Cooler", 8, 92),
                new MedicalItem("Crush Injury Electrolyte/IV Pack", 6, 85),
                new MedicalItem("Heavy Debris Splint / Cervical Set", 4, 70));
    }

    public static Result optimizeDisasterPayload(int capacityKg) {
        return optimizePayload(disasterEmergencyPreset(), capacityKg);
    }

    private static List<MedicalItem> validate(List<MedicalItem> items, int capacityW) {
        Objects.requireNonNull(items, "items");
        if (capacityW < 0) throw new IllegalArgumentException("Capacity cannot be negative.");
        List<MedicalItem> copy = new ArrayList<>(items.size());
        for (MedicalItem item : items) copy.add(Objects.requireNonNull(item, "item"));
        return copy;
    }
}