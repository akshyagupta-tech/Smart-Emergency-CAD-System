public class PatientNode implements Comparable<PatientNode> {
    private String patientId;
    private String name;
    private int esiLevel;
    private int waitTimeMin;
    private double vitalsRisk;
    private int age;
    private double priorityScore;

    public PatientNode(String patientId, String name, int esiLevel, int waitTimeMin, double vitalsRisk, int age) {
        this.patientId = patientId;
        this.name = name;
        this.esiLevel = esiLevel;
        this.waitTimeMin = waitTimeMin;
        this.vitalsRisk = vitalsRisk;
        this.age = age;
        calculatePriorityScore();
    }

    public void calculatePriorityScore() {
        int esiInv = 6 - this.esiLevel;
        double ageRisk = (this.age > 60 || this.age < 5) ? 2.0 : 1.0;
        this.priorityScore = (15.0 * esiInv) + (0.5 * this.waitTimeMin) + (8.0 * this.vitalsRisk) + (2.0 * ageRisk);
    }

    public void incrementWaitTime(int minutes) {
        this.waitTimeMin += minutes;
        calculatePriorityScore();
    }

    public double getPriorityScore() { return priorityScore; }
    public String getPatientId() { return patientId; }
    public String getName() { return name; }
    public int getEsiLevel() { return esiLevel; }

    @Override
    public int compareTo(PatientNode other) {
        return Double.compare(other.priorityScore, this.priorityScore);
    }

    @Override
    public String toString() {
        return String.format("[%s] %-18s | ESI: %d | Wait: %2d min | Score: %6.2f",
                patientId, name, esiLevel, waitTimeMin, priorityScore);
    }
}
