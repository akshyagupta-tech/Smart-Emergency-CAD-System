package cad;

import logistics.KnapsackPayload;
import disaster.DisasterScenarioManager;
import model.PatientNode;
import routing.EmergencyNetwork;
import routing.MCIRoutingTSP;
import storage.BPlusTreeTelemetry;
import triage.DynamicTriageHeap;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.locks.ReentrantReadWriteLock;

/**
 * Owns the mutable CAD state. Public operations share one fair lock so dispatch is atomic relative
 * to web requests, CLI actions, and the simulated call stream while read-only snapshots can overlap.
 */
public final class ThreadSafeDispatchEngine {
    private final ReentrantReadWriteLock lock = new ReentrantReadWriteLock(true);
    private final DynamicTriageHeap triage = new DynamicTriageHeap();
    private final EmergencyNetwork roads = new EmergencyNetwork();
    private final HospitalRegistry hospitals = new HospitalRegistry();
    private final DisasterScenarioManager disasterScenarios;
    private final BPlusTreeTelemetry telemetry = new BPlusTreeTelemetry();
    private final List<KnapsackPayload.MedicalItem> equipment = new ArrayList<>();
    private long dispatchSequence;
    private long simulatedCallSequence;
    private long sosSequence;
    private Map<String, Object> lastDispatch;

    public ThreadSafeDispatchEngine() {
        initializeDemoState();
        disasterScenarios = new DisasterScenarioManager(roads, hospitals, triage);
        triage.loadDisasterDemoPatients();
    }

    public PatientNode admit(String patientId, String condition, int esiLevel, int waitTimeMinutes,
                             double vitalsRiskScore, int age) {
        lock.writeLock().lock();
        try {
            PatientNode patient = new PatientNode(patientId, condition, esiLevel, waitTimeMinutes,
                    vitalsRiskScore, age);
            triage.insert(patient);
            return copyPatient(patient);
        } finally { lock.writeLock().unlock(); }
    }

    public List<PatientNode> triageSnapshot() {
        lock.readLock().lock();
        try { return triage.snapshotInPriorityOrder(); }
        finally { lock.readLock().unlock(); }
    }

    public int triageSize() {
        lock.readLock().lock();
        try { return triage.size(); }
        finally { lock.readLock().unlock(); }
    }

    public int ageWaitingPatients(int deltaMinutes) {
        lock.writeLock().lock();
        try {
            triage.ageAllPatients(deltaMinutes);
            return triage.size();
        } finally { lock.writeLock().unlock(); }
    }

    public PatientNode updatePatientVitals(String patientId, double vitalsRiskScore) {
        lock.writeLock().lock();
        try {
            PatientNode patient = null;
            for (PatientNode current : triage.snapshotInPriorityOrder())
                if (current.getPatientId().equals(patientId)) { patient = current; break; }
            if (patient == null) throw new IllegalArgumentException("Patient is not waiting in the triage queue.");
            boolean updated = triage.updatePriority(patientId, patient.getEsiLevel(), patient.getWaitTimeMinutes(),
                    vitalsRiskScore, patient.getAge());
            if (!updated) throw new IllegalStateException("Patient left the triage queue during the update.");
            for (PatientNode current : triage.snapshotInPriorityOrder())
                if (current.getPatientId().equals(patientId)) return current;
            throw new IllegalStateException("Updated patient could not be found in triage.");
        } finally { lock.writeLock().unlock(); }
    }

    public List<Map<String, Object>> hospitalStatusSnapshot() {
        lock.readLock().lock();
        try { return hospitals.snapshot(); }
        finally { lock.readLock().unlock(); }
    }

    public Map<String, Object> metricsSnapshot() {
        lock.readLock().lock();
        try {
            List<Map<String, Object>> facilities = hospitals.snapshot();
            long activeFacilities = facilities.stream().filter(item -> Boolean.TRUE.equals(item.get("active"))).count();
            return Map.of("waitingPatients", triage.size(), "totalFacilities", facilities.size(),
                    "activeFacilities", activeFacilities, "telemetryRecords", telemetry.size(),
                    "activeScenario", disasterScenarios.getActiveScenario(),
                    "temporaryCasualties", disasterScenarios.snapshot().get("temporaryPatients"));
        } finally { lock.readLock().unlock(); }
    }

    public Map<String, Object> activeDispatchSnapshot() {
        lock.readLock().lock();
        try {
            if (lastDispatch == null) return Map.of("assigned", false);
            return Map.of("assigned", true, "dispatch", lastDispatch);
        } finally { lock.readLock().unlock(); }
    }

    public Map<String, Object> submitCitizenSos(String details) {
        lock.writeLock().lock();
        try {
            String description = details == null || details.isBlank() ? "Citizen emergency call" : details.trim();
            if (description.length() > 200) throw new IllegalArgumentException("SOS details must not exceed 200 characters.");
            String patientId = "SOS-" + String.format("%05d", ++sosSequence);
            PatientNode patient = new PatientNode(patientId, "Citizen caller", description, 2, 0, 7.0, 30,
                    PatientNode.DisasterTriageTag.RED);
            triage.insert(patient);
            return Map.of("accepted", true, "callId", patientId, "etaMinutes", 9,
                    "message", "Distress call received. A dispatcher will verify and assign a unit.");
        } finally { lock.writeLock().unlock(); }
    }

    public PatientNode generateSimulatedCall() {
        lock.writeLock().lock();
        try {
            long sequence = ++simulatedCallSequence;
            String[] conditions = {"Respiratory distress", "Road trauma", "Cardiac symptoms", "Burn injury", "Pediatric fever"};
            int index = (int) ((sequence - 1) % conditions.length);
            int[] esi = {2, 1, 2, 2, 3};
            double[] risk = {7.4, 8.6, 8.1, 7.8, 5.3};
            int[] ages = {42, 31, 68, 24, 4};
            String id = "AUTO-" + String.format("%05d", sequence);
            PatientNode patient = new PatientNode(id, conditions[index], esi[index], 0, risk[index], ages[index]);
            triage.insert(patient);
            return copyPatient(patient);
        } finally { lock.writeLock().unlock(); }
    }

    public Map<String, Object> networkSnapshot() {
        lock.readLock().lock();
        try {
            List<Map<String, Object>> edges = new ArrayList<>();
            for (EmergencyNetwork.Edge edge : roads.getEdges()) {
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("source", edge.getSource());
                item.put("target", edge.getTarget());
                item.put("baseMinutes", edge.getBaseMinutes());
                item.put("weightMinutes", edge.getWeightMinutes());
                item.put("distanceKm", edge.getDistanceKm());
                item.put("speedLimit", edge.getSpeedLimit());
                item.put("congestionFactor", edge.getCongestionFactor());
                item.put("severed", edge.isSevered());
                item.put("passable", disasterScenarios.isEdgePassable(edge.getSource(), edge.getTarget()));
                edges.add(item);
            }
            EmergencyNetwork.MstResult mst = roads.computeKruskalMST();
            List<Map<String, Object>> backbone = new ArrayList<>();
            for (EmergencyNetwork.Edge edge : mst.getEdges()) {
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("source", edge.getSource());
                item.put("target", edge.getTarget());
                item.put("weightMinutes", edge.getWeightMinutes());
                backbone.add(item);
            }
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("nodes", roads.getNodes());
            Map<String, String> nodeStatus = new LinkedHashMap<>();
            for (String node : roads.getNodes()) {
                String status = hospitals.contains(node)
                        ? (hospitals.isActive(node) ? "ACTIVE" : "OFFLINE")
                        : (disasterScenarios.isNodeActive(node) ? "ACTIVE" : "INACTIVE");
                nodeStatus.put(node, status);
            }
            result.put("nodeStatus", nodeStatus);
            result.put("edges", edges);
            result.put("mst", Map.of("connected", mst.isConnected(), "totalLatency", mst.getTotalLatency(), "edges", backbone));
            result.put("disaster", disasterScenarios.snapshot());
            return result;
        } finally { lock.readLock().unlock(); }
    }

    public Map<String, Object> executeDispatch() {
        lock.writeLock().lock();
        try {
            PatientNode waiting = triage.peek();
            if (waiting == null) throw new IllegalStateException("No patients are waiting for dispatch.");
            String specialty = chooseSpecialty(waiting.getCondition());
            String preferredHospital = disasterScenarios.getPreferredHospital();
            String primaryHospital = preferredHospital == null ? "TraumaCenter" : preferredHospital;
            HospitalRegistry.Allocation allocation = hospitals.allocateBedOrDivert(primaryHospital, specialty);
            if (!allocation.isAllocated())
                throw new IllegalStateException("No hospital has a suitable ICU bed and " + specialty + " bay.");

            PatientNode patient = triage.extractMax();
            EmergencyNetwork.PathResult toScene = roads.findShortestPath("AmbulanceDepot", "IncidentScene");
            EmergencyNetwork.PathResult toHospital = roads.findShortestPath("IncidentScene", allocation.getHospitalName());
            if (!toScene.isReachable() || !toHospital.isReachable())
                throw new IllegalStateException("Bed reserved, but no complete dispatch route exists.");

                KnapsackPayload.Result payload = usesDisasterPayload()
                    ? KnapsackPayload.optimizeDisasterPayload(KnapsackPayload.DISASTER_PAYLOAD_CAPACITY_KG)
                    : KnapsackPayload.optimizePayload(equipment, KnapsackPayload.DISASTER_PAYLOAD_CAPACITY_KG);
            String vehicleId = "AMB-" + String.format("%02d", (dispatchSequence % 3) + 1);
            long timestamp = System.currentTimeMillis() / 1000;
            String status = "EN_ROUTE_HOSPITAL";
            BPlusTreeTelemetry.TelemetryRecord record = new BPlusTreeTelemetry.TelemetryRecord(
                    timestamp, vehicleId, 28.4795, 77.4980, status);
            telemetry.insert(record);
            long dispatchId = ++dispatchSequence;

            Map<String, Object> result = new LinkedHashMap<>();
            result.put("dispatchId", dispatchId);
            result.put("patient", patientMap(patient));
            result.put("hospital", allocation.getHospitalName());
            result.put("diverted", allocation.isDiverted());
            result.put("specialty", specialty);
            result.put("vehicleId", vehicleId);
            result.put("route", Map.of("toScene", pathMap(toScene), "toHospital", pathMap(toHospital),
                    "totalMinutes", toScene.getTotalMinutes() + toHospital.getTotalMinutes()));
            List<Map<String, Object>> selectedItems = new ArrayList<>();
            for (KnapsackPayload.MedicalItem item : payload.getSelectedItems()) {
                selectedItems.add(Map.of("name", item.getName(), "weightKg", item.getWeightKg(),
                        "utilityScore", item.getUtilityScore()));
            }
            result.put("payload", Map.of("capacityKg", 30, "weightKg", payload.getTotalWeightKg(),
                    "utilityScore", payload.getMaxUtility(), "items", selectedItems));
            result.put("telemetry", telemetryMap(record));
            lastDispatch = Map.copyOf(result);
            return result;
        } finally { lock.writeLock().unlock(); }
    }

    public Map<String, Object> spikeCongestion(String from, String to, double multiplier,
                                                String source, String destination) {
        lock.writeLock().lock();
        try {
            roads.updateCongestion(from, to, multiplier);
            EmergencyNetwork.PathResult path = roads.findShortestPath(source, destination);
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("updatedEdge", Map.of("source", from, "target", to, "congestionFactor", multiplier));
            result.put("reroutedPath", pathMap(path));
            return result;
        } finally { lock.writeLock().unlock(); }
    }

    public Map<String, Object> activateDisasterScenario(String scenarioName) {
        lock.writeLock().lock();
        try {
            disasterScenarios.activateScenario(scenarioName);
            return disasterScenarios.snapshot();
        } finally { lock.writeLock().unlock(); }
    }

    public Map<String, Object> resetDisasterScenario() {
        lock.writeLock().lock();
        try {
            disasterScenarios.resetToNormal();
            return disasterScenarios.snapshot();
        } finally { lock.writeLock().unlock(); }
    }

    public Map<String, Object> loadEarthquakeCasualties() {
        lock.writeLock().lock();
        try {
            disasterScenarios.loadEarthquakeCasualties();
            return Map.of("loaded", disasterScenarios.snapshot().get("temporaryPatients"),
                    "queueSize", triage.size());
        } finally { lock.writeLock().unlock(); }
    }

    public Map<String, Object> severMainBridge() {
        lock.writeLock().lock();
        try {
            disasterScenarios.severMainBridge();
            return disasterScenarios.snapshot();
        } finally { lock.writeLock().unlock(); }
    }

    public Map<String, Object> divertToFieldHospital() {
        lock.writeLock().lock();
        try {
            disasterScenarios.divertToFieldHospital();
            return disasterScenarios.snapshot();
        } finally { lock.writeLock().unlock(); }
    }

    public Map<String, Object> disasterSnapshot() {
        lock.readLock().lock();
        try { return disasterScenarios.snapshot(); }
        finally { lock.readLock().unlock(); }
    }

    public boolean isNodeActive(String nodeId) {
        lock.readLock().lock();
        try { return disasterScenarios.isNodeActive(nodeId); }
        finally { lock.readLock().unlock(); }
    }

    public boolean isEdgePassable(String from, String to) {
        lock.readLock().lock();
        try { return disasterScenarios.isEdgePassable(from, to); }
        finally { lock.readLock().unlock(); }
    }

    public Map<String, Object> routeSnapshot(String source, String destination) {
        lock.readLock().lock();
        try { return pathMap(roads.findShortestPath(source, destination)); }
        finally { lock.readLock().unlock(); }
    }

    public List<Map<String, Object>> telemetryQuery(long startTimestamp, long endTimestamp) {
        lock.readLock().lock();
        try {
            List<Map<String, Object>> records = new ArrayList<>();
            for (BPlusTreeTelemetry.TelemetryRecord record : telemetry.rangeQuery(startTimestamp, endTimestamp))
                records.add(telemetryMap(record));
            return List.copyOf(records);
        } finally { lock.readLock().unlock(); }
    }

    public Map<String, Object> payloadSnapshot(int capacityKg) {
        lock.readLock().lock();
        try {
            KnapsackPayload.Result result = usesDisasterPayload()
                    ? KnapsackPayload.optimizeDisasterPayload(capacityKg)
                    : KnapsackPayload.optimizePayload(equipment, capacityKg);
            List<Map<String, Object>> items = new ArrayList<>();
            for (KnapsackPayload.MedicalItem item : result.getSelectedItems())
                items.add(Map.of("name", item.getName(), "weightKg", item.getWeightKg(), "utilityScore", item.getUtilityScore()));
            return Map.of("capacityKg", capacityKg, "weightKg", result.getTotalWeightKg(),
                    "utilityScore", result.getMaxUtility(), "items", items);
        } finally { lock.readLock().unlock(); }
    }

    public Map<String, Object> solveMci() {
        lock.readLock().lock();
        try {
            int[][] costs = {{0, 10, 15, 20}, {10, 0, 35, 25}, {15, 35, 0, 30}, {20, 25, 30, 0}};
            MCIRoutingTSP.Result result = new MCIRoutingTSP(costs,
                    new String[]{"Command Post", "Scene Alpha", "Scene Bravo", "Scene Charlie"}).solve();
            return Map.of("reachable", result.hasTour(), "tour", result.getTour(),
                    "totalLatencyMinutes", result.getTotalLatency(), "prunedBranches", result.getPrunedBranches(),
                    "totalPermutations", result.getTotalPermutations(), "exploredNodes", result.getExploredNodes());
        } finally { lock.readLock().unlock(); }
    }

    public void printTriageQueue() {
        lock.readLock().lock();
        try { triage.printQueue(); }
        finally { lock.readLock().unlock(); }
    }

    public KnapsackPayload.Result optimizePayload(int capacityKg) {
        lock.readLock().lock();
        try {
            return usesDisasterPayload() ? KnapsackPayload.optimizeDisasterPayload(capacityKg)
                    : KnapsackPayload.optimizePayload(equipment, capacityKg);
        }
        finally { lock.readLock().unlock(); }
    }

    public void runBenchmark() {
        lock.readLock().lock();
        try {
            if (!roads.findShortestPath("AmbulanceDepot", "IncidentScene").isReachable())
                throw new IllegalStateException("Road graph benchmark failed.");
            if (!roads.computeKruskalMST().isConnected()) throw new IllegalStateException("MST benchmark failed.");
            KnapsackPayload.Result payload = KnapsackPayload.optimizePayload(equipment, 30);
            if (payload.getMaxUtility() != KnapsackPayload.optimizePayloadRolling(equipment, 30))
                throw new IllegalStateException("Knapsack benchmark failed.");
        } finally { lock.readLock().unlock(); }
    }

    public static Map<String, Object> patientMap(PatientNode patient) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("patientId", patient.getPatientId());
        result.put("patientName", patient.getPatientName());
        result.put("condition", patient.getCondition());
        result.put("esiLevel", patient.getEsiLevel());
        result.put("waitTimeMinutes", patient.getWaitTimeMinutes());
        result.put("vitalsRiskScore", patient.getVitalsRiskScore());
        result.put("age", patient.getAge());
        result.put("priorityScore", patient.getPriorityScore());
        result.put("disasterTriageTag", patient.getDisasterTriageTag().name());
        return result;
    }

    private static Map<String, Object> pathMap(EmergencyNetwork.PathResult path) {
        return Map.of("reachable", path.isReachable(), "nodes", path.getPath(), "totalMinutes", path.getTotalMinutes());
    }

    private static Map<String, Object> telemetryMap(BPlusTreeTelemetry.TelemetryRecord record) {
        return Map.of("timestamp", record.getTimestamp(), "vehicleId", record.getVehicleId(),
                "lat", record.getLat(), "lon", record.getLon(), "status", record.getStatus());
    }

    private static PatientNode copyPatient(PatientNode patient) {
        return patient.copy();
    }

    private boolean usesDisasterPayload() {
        return !DisasterScenarioManager.NORMAL.equals(disasterScenarios.getActiveScenario())
                || disasterScenarios.getPreferredHospital() != null;
    }

    private void initializeDemoState() {
        hospitals.registerHospital("TraumaCenter", 3, Map.of("TRAUMA", 3, "BURN", 1, "CATH LAB", 1));
        hospitals.registerHospital("MetroGeneral", 2, Map.of("TRAUMA", 2, "BURN", 1, "CATH LAB", 2));
        hospitals.registerHospital("CityHeart", 2, Map.of("CATH LAB", 2, "TRAUMA", 1));

        addBidirectionalRoad("AmbulanceDepot", "Inter_A", 4, 2.4, 50);
        addBidirectionalRoad("AmbulanceDepot", "Inter_B", 3, 1.8, 50);
        addBidirectionalRoad("Inter_A", "IncidentScene", 5, 3.2, 40);
        addBidirectionalRoad("Inter_B", "Inter_C", 1, 0.7, 40);
        addBidirectionalRoad("Inter_C", "IncidentScene", 2, 1.1, 40);
        addBidirectionalRoad("IncidentScene", "TraumaCenter", 6, 4.0, 60);
        addBidirectionalRoad("IncidentScene", "MetroGeneral", 8, 5.2, 60);
        addBidirectionalRoad("IncidentScene", "CityHeart", 7, 4.8, 60);

        equipment.add(new KnapsackPayload.MedicalItem("Portable ventilator", 12, 85));
        equipment.add(new KnapsackPayload.MedicalItem("Defibrillator unit", 8, 95));
        equipment.add(new KnapsackPayload.MedicalItem("Portable ECMO", 25, 90));
        equipment.add(new KnapsackPayload.MedicalItem("Pediatric trauma kit", 5, 45));
        equipment.add(new KnapsackPayload.MedicalItem("Blood infusion cooler", 10, 75));

        triage.insert(new PatientNode("P101", "Cardiac arrest", 1, 3, 9.8, 67));
        triage.insert(new PatientNode("P102", "Minor fracture", 4, 30, 2.0, 24));
        triage.insert(new PatientNode("P103", "Acute polytrauma", 1, 1, 9.2, 38));
        long now = System.currentTimeMillis() / 1000;
        telemetry.insert(new BPlusTreeTelemetry.TelemetryRecord(now - 9, "AMB-01", 28.4712, 77.4921, "DEPOT_STANDBY"));
        telemetry.insert(new BPlusTreeTelemetry.TelemetryRecord(now - 5, "AMB-01", 28.4735, 77.4950, "EN_ROUTE"));
        telemetry.insert(new BPlusTreeTelemetry.TelemetryRecord(now - 2, "AMB-02", 28.4801, 77.5011, "PATIENT_ONBOARD"));
    }

    private void addBidirectionalRoad(String first, String second, double minutes, double km, double speed) {
        roads.addRoadSegment(first, second, minutes, km, speed);
        roads.addRoadSegment(second, first, minutes, km, speed);
    }

    private static String chooseSpecialty(String condition) {
        String normalized = condition.toLowerCase(java.util.Locale.ROOT);
        if (normalized.contains("burn")) return "BURN";
        if (normalized.contains("cardiac") || normalized.contains("heart")) return "CATH LAB";
        return "TRAUMA";
    }
}