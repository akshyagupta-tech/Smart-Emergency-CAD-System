package triage;

import model.PatientNode;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/** Array-backed max heap; insert/extract are O(log n), peek O(1), and storage O(n). */
public final class DynamicTriageHeap {
    private final List<PatientNode> heap = new ArrayList<>();
    private final Map<String, Integer> indexByPatientId = new HashMap<>();

    public void insert(PatientNode patient) {
        Objects.requireNonNull(patient, "patient");
        if (indexByPatientId.containsKey(patient.getPatientId()))
            throw new IllegalArgumentException("Patient ID already exists in triage: " + patient.getPatientId());
        heap.add(patient);
        int index = heap.size() - 1;
        indexByPatientId.put(patient.getPatientId(), index);
        bubbleUp(index);
    }

    public PatientNode extractMax() {
        if (heap.isEmpty()) return null;
        PatientNode maximum = heap.get(0);
        indexByPatientId.remove(maximum.getPatientId());
        PatientNode last = heap.remove(heap.size() - 1);
        if (!heap.isEmpty()) {
            heap.set(0, last);
            indexByPatientId.put(last.getPatientId(), 0);
            siftDown(0);
        }
        return maximum;
    }

        public PatientNode remove(String patientId) {
        Integer index = indexByPatientId.remove(patientId);
        if (index == null) return null;
        PatientNode removed = heap.get(index);
        PatientNode last = heap.remove(heap.size() - 1);
        if (index < heap.size()) {
            heap.set(index, last);
            indexByPatientId.put(last.getPatientId(), index);
            siftDown(bubbleUp(index));
        }
        return removed;
        }

        public void loadDisasterDemoPatients() {
        insertIfMissing(PatientNode.withPriority("D-101", "P. Sharma", "Crush Syndrome (Building Collapse)",
            1, 0, 10.0, 34, PatientNode.DisasterTriageTag.RED, 184.5));
        insertIfMissing(PatientNode.withPriority("D-102", "R. Verma", "Traumatic Hemorrhagic Shock",
            1, 0, 10.0, 8, PatientNode.DisasterTriageTag.RED, 192.0));
        insertIfMissing(PatientNode.withPriority("D-103", "S. Khan", "Acute Asphyxiation / Dust Inhalation",
            1, 0, 9.0, 68, PatientNode.DisasterTriageTag.RED, 176.0));
        insertIfMissing(PatientNode.withPriority("D-104", "A. Patel", "Compound Femur Fracture",
            2, 0, 6.0, 22, PatientNode.DisasterTriageTag.YELLOW, 122.0));
        insertIfMissing(PatientNode.withPriority("D-105", "M. Das", "Moderate Blunt Chest Trauma",
            2, 0, 5.0, 45, PatientNode.DisasterTriageTag.YELLOW, 115.0));
        insertIfMissing(PatientNode.withPriority("D-106", "K. Devi", "Superficial Lacerations & Panic",
            4, 0, 2.5, 29, PatientNode.DisasterTriageTag.GREEN, 54.0));
        }

    public PatientNode peek() { return heap.isEmpty() ? null : heap.get(0); }

    /** Uniform aging changes every score equally, so heap order is unchanged: O(n) time, O(1) extra space. */
    public void ageAllPatients(int deltaMinutes) {
        if (deltaMinutes < 0) throw new IllegalArgumentException("Aging delta cannot be negative.");
        for (PatientNode patient : heap)
            if (patient.getWaitTimeMinutes() > Integer.MAX_VALUE - deltaMinutes)
                throw new ArithmeticException("Patient wait time would exceed the supported range.");
        for (PatientNode patient : heap)
            patient.setWaitTimeMinutes(patient.getWaitTimeMinutes() + deltaMinutes);
    }

    /** Updates a patient's mutable clinical fields and repairs the heap in O(log n) time. */
    public boolean updatePriority(String patientId, int esiLevel, int waitTimeMinutes,
                                  double vitalsRiskScore, int age) {
        Integer index = indexByPatientId.get(patientId);
        if (index == null) return false;
        if (esiLevel < 1 || esiLevel > 5 || waitTimeMinutes < 0 || !Double.isFinite(vitalsRiskScore)
                || vitalsRiskScore < 0.0 || vitalsRiskScore > 10.0 || age < 0 || age > 130)
            throw new IllegalArgumentException("Invalid patient priority update values.");
        PatientNode patient = heap.get(index);
        patient.setEsiLevel(esiLevel);
        patient.setWaitTimeMinutes(waitTimeMinutes);
        patient.setVitalsRiskScore(vitalsRiskScore);
        patient.setAge(age);
        patient.recalculateScore();
        int newIndex = bubbleUp(index);
        siftDown(newIndex);
        return true;
    }

    public int size() { return heap.size(); }
    public boolean isEmpty() { return heap.isEmpty(); }

    /** Returns detached patient copies in priority order in O(n log n) time and O(n) space. */
    public List<PatientNode> snapshotInPriorityOrder() {
        List<PatientNode> snapshot = new ArrayList<>(heap.size());
        for (PatientNode patient : heap) snapshot.add(patient.copy());
        snapshot.sort(Comparator.reverseOrder());
        return List.copyOf(snapshot);
    }

    /** Prints a snapshot in heap-array order in O(n) time and O(1) extra space. */
    public void printQueue() {
        System.out.println("--- Triage Priority Queue ---");
        if (heap.isEmpty()) System.out.println("(empty)");
        for (PatientNode patient : heap) System.out.println(patient);
    }

    private void insertIfMissing(PatientNode patient) {
        if (!indexByPatientId.containsKey(patient.getPatientId())) insert(patient);
    }

    private int bubbleUp(int index) {
        while (index > 0) {
            int parent = (index - 1) / 2;
            if (heap.get(index).compareTo(heap.get(parent)) <= 0) break;
            swap(index, parent);
            index = parent;
        }
        return index;
    }

    private void siftDown(int index) {
        while (true) {
            int largest = index;
            int left = 2 * index + 1;
            int right = left + 1;
            if (left < heap.size() && heap.get(left).compareTo(heap.get(largest)) > 0) largest = left;
            if (right < heap.size() && heap.get(right).compareTo(heap.get(largest)) > 0) largest = right;
            if (largest == index) return;
            swap(index, largest);
            index = largest;
        }
    }

    private void swap(int first, int second) {
        PatientNode temporary = heap.get(first);
        heap.set(first, heap.get(second));
        heap.set(second, temporary);
        indexByPatientId.put(heap.get(first).getPatientId(), first);
        indexByPatientId.put(heap.get(second).getPatientId(), second);
    }
}