package model;

import java.util.Objects;

/** Patient information used by triage. Score recalculation is O(1) time and O(1) space. */
public final class PatientNode implements Comparable<PatientNode> {
    public enum DisasterTriageTag { RED, YELLOW, GREEN, BLACK }

    private final String patientId;
    private final String patientName;
    private String condition;
    private int esiLevel;
    private int waitTimeMinutes;
    private double vitalsRiskScore;
    private int age;
    private double priorityScore;
    private double priorityAdjustment;
    private DisasterTriageTag disasterTriageTag;

    public PatientNode(String patientId, String condition, int esiLevel, int waitTimeMinutes,
                       double vitalsRiskScore, int age) {
        this(patientId, patientId, condition, esiLevel, waitTimeMinutes, vitalsRiskScore, age,
                defaultTag(esiLevel));
    }

    public PatientNode(String patientId, String patientName, String condition, int esiLevel, int waitTimeMinutes,
                       double vitalsRiskScore, int age, DisasterTriageTag disasterTriageTag) {
        this.patientId = requireText(patientId, "patientId");
        this.patientName = requireText(patientName, "patientName");
        this.disasterTriageTag = Objects.requireNonNull(disasterTriageTag, "disasterTriageTag");
        setCondition(condition);
        setEsiLevel(esiLevel);
        setWaitTimeMinutes(waitTimeMinutes);
        setVitalsRiskScore(vitalsRiskScore);
        setAge(age);
    }

    public static PatientNode withPriority(String patientId, String patientName, String condition, int esiLevel,
                                           int waitTimeMinutes, double vitalsRiskScore, int age,
                                           DisasterTriageTag disasterTriageTag, double priorityScore) {
        if (!Double.isFinite(priorityScore) || priorityScore < 0.0)
            throw new IllegalArgumentException("Priority score must be finite and non-negative.");
        PatientNode patient = new PatientNode(patientId, patientName, condition, esiLevel, waitTimeMinutes,
                vitalsRiskScore, age, disasterTriageTag);
        patient.priorityAdjustment = priorityScore - patient.priorityScore;
        patient.recalculateScore();
        return patient;
    }

    /** Recalculates the clinical priority score in O(1) time and O(1) space. */
    public void recalculateScore() {
        double ageFactor = age > 65 || age < 5 ? 5.0 : 1.0;
        priorityScore = (15.0 * (6 - esiLevel)) + (0.5 * waitTimeMinutes)
                + (8.0 * vitalsRiskScore) + (2.0 * ageFactor) + priorityAdjustment;
    }

    public String getPatientId() { return patientId; }
    public String getPatientName() { return patientName; }
    public String getCondition() { return condition; }
    public int getEsiLevel() { return esiLevel; }
    public int getWaitTimeMinutes() { return waitTimeMinutes; }
    public double getVitalsRiskScore() { return vitalsRiskScore; }
    public int getAge() { return age; }
    public double getPriorityScore() { return priorityScore; }
    public DisasterTriageTag getDisasterTriageTag() { return disasterTriageTag; }

    public PatientNode copy() {
        PatientNode copy = new PatientNode(patientId, patientName, condition, esiLevel, waitTimeMinutes,
                vitalsRiskScore, age, disasterTriageTag);
        copy.priorityAdjustment = priorityAdjustment;
        copy.recalculateScore();
        return copy;
    }

    public void setCondition(String condition) { this.condition = requireText(condition, "condition"); }
    public void setEsiLevel(int esiLevel) {
        if (esiLevel < 1 || esiLevel > 5) throw new IllegalArgumentException("ESI level must be from 1 to 5.");
        this.esiLevel = esiLevel;
        recalculateScore();
    }
    public void setWaitTimeMinutes(int waitTimeMinutes) {
        if (waitTimeMinutes < 0) throw new IllegalArgumentException("Wait time cannot be negative.");
        this.waitTimeMinutes = waitTimeMinutes;
        recalculateScore();
    }
    public void setVitalsRiskScore(double vitalsRiskScore) {
        if (!Double.isFinite(vitalsRiskScore) || vitalsRiskScore < 0.0 || vitalsRiskScore > 10.0)
            throw new IllegalArgumentException("Vitals risk score must be between 0 and 10.");
        this.vitalsRiskScore = vitalsRiskScore;
        recalculateScore();
    }
    public void setAge(int age) {
        if (age < 0 || age > 130) throw new IllegalArgumentException("Age must be between 0 and 130.");
        this.age = age;
        recalculateScore();
    }

    @Override
    public int compareTo(PatientNode other) {
        Objects.requireNonNull(other, "other");
        int byScore = Double.compare(priorityScore, other.priorityScore);
        return byScore != 0 ? byScore : patientId.compareTo(other.patientId);
    }

    @Override
    public String toString() {
        return String.format("[%s] %s | %s | %s | ESI %d | Wait %d min | Risk %.1f | Age %d | Priority %.2f",
                patientId, patientName, condition, disasterTriageTag, esiLevel, waitTimeMinutes,
                vitalsRiskScore, age, priorityScore);
    }

    private static DisasterTriageTag defaultTag(int esiLevel) {
        if (esiLevel <= 2) return DisasterTriageTag.RED;
        if (esiLevel <= 4) return DisasterTriageTag.YELLOW;
        return DisasterTriageTag.GREEN;
    }

    private static String requireText(String value, String label) {
        if (value == null || value.isBlank()) throw new IllegalArgumentException(label + " cannot be blank.");
        return value.trim();
    }
}