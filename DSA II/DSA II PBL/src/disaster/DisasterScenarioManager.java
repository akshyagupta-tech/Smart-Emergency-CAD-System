package disaster;

import cad.HospitalRegistry;
import model.PatientNode;
import routing.EmergencyNetwork;
import triage.DynamicTriageHeap;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Coordinates disaster state across the road graph, hospital registry, and triage heap. */
public final class DisasterScenarioManager {
    public static final String NORMAL = "NORMAL_OPERATIONS";
    public static final String EARTHQUAKE_COLLAPSE = "EARTHQUAKE_COLLAPSE";
    public static final String TSUNAMI_FLOOD_INUNDATION = "TSUNAMI_FLOOD_INUNDATION";
    public static final String FIELD_HOSPITAL_NORTH = "FieldHospital_North";
    public static final String HELIPAD_ALPHA = "HeliPad_Alpha";
    public static final String DISASTER_ZONE_SECTOR_4 = "DisasterZone_Sector4";
    public static final String PERIPHERAL_RING_ROAD = "Peripheral Ring Road";
    public static final String EMERGENCY_AIRWAY_CORRIDOR = "Emergency Airway Corridor";

    private static final String TRAUMA_CENTER = "TraumaCenter";
    private static final List<String> TEMPORARY_NODES = List.of(FIELD_HOSPITAL_NORTH, HELIPAD_ALPHA,
            DISASTER_ZONE_SECTOR_4, PERIPHERAL_RING_ROAD, EMERGENCY_AIRWAY_CORRIDOR);
        private static final List<String> CORRIDOR_NODES = List.of(DISASTER_ZONE_SECTOR_4,
            PERIPHERAL_RING_ROAD, EMERGENCY_AIRWAY_CORRIDOR);
    private static final List<String> CASUALTY_CONDITIONS = List.of(
            "Crush Syndrome", "Traumatic Amputation", "Tension Pneumothorax", "Severe Concussion",
            "Traumatic Hemorrhagic Shock", "Crush Syndrome", "Acute Asphyxiation / Dust Inhalation",
            "Compound Pelvic Fracture", "Compartment Syndrome", "Severe Debris Lacerations");

    private final EmergencyNetwork network;
    private final HospitalRegistry hospitals;
    private final DynamicTriageHeap triage;
    private final List<String> injectedPatientIds = new ArrayList<>();
    private String activeScenario = NORMAL;
    private String preferredHospital;

    public DisasterScenarioManager(EmergencyNetwork network, HospitalRegistry hospitals, DynamicTriageHeap triage) {
        this.network = network;
        this.hospitals = hospitals;
        this.triage = triage;
        registerTemporaryFacilities();
        registerDisasterCorridors();
        resetToNormal();
    }

    public synchronized void activateScenario(String scenarioName) {
        if (scenarioName == null) throw new IllegalArgumentException("Scenario name is required.");
        String normalized = scenarioName.trim().toUpperCase(java.util.Locale.ROOT);
        if (NORMAL.equals(normalized) || "NORMAL".equals(normalized)) {
            resetToNormal();
            return;
        }
        if (!EARTHQUAKE_COLLAPSE.equals(normalized) && !TSUNAMI_FLOOD_INUNDATION.equals(normalized))
            throw new IllegalArgumentException("Unknown disaster scenario: " + scenarioName);

        resetToNormal();
        activeScenario = normalized;
        activateDisasterCorridors();
        hospitals.setActive(FIELD_HOSPITAL_NORTH, true);
        network.setNodeActive(FIELD_HOSPITAL_NORTH, true);
        preferredHospital = FIELD_HOSPITAL_NORTH;

        if (EARTHQUAKE_COLLAPSE.equals(normalized)) {
            severBidirectional("Inter_B", "Inter_C");
            severBidirectional("AmbulanceDepot", "Inter_B");
            hospitals.setActive(TRAUMA_CENTER, false);
            network.setNodeActive(TRAUMA_CENTER, false);
            hospitals.setActive(HELIPAD_ALPHA, true);
            network.setNodeActive(HELIPAD_ALPHA, true);
            loadEarthquakeCasualties();
        } else {
            hospitals.setActive(HELIPAD_ALPHA, true);
            network.setNodeActive(HELIPAD_ALPHA, true);
            network.setWaterLoggingProfile("AmbulanceDepot", "Inter_B", 2.0, 8.0, 36);
            network.setWaterLoggingProfile("Inter_B", "AmbulanceDepot", 2.0, 8.0, 36);
            network.setWaterLoggingProfile("Inter_B", "Inter_C", 3.0, 18.0, 36);
            network.setWaterLoggingProfile("Inter_C", "Inter_B", 3.0, 18.0, 36);
            network.setWaterLoggingProfile("IncidentScene", "MetroGeneral", 2.0, 14.0, 36);
            network.setWaterLoggingProfile("MetroGeneral", "IncidentScene", 2.0, 14.0, 36);
        }
    }

    public synchronized void resetToNormal() {
        for (String patientId : injectedPatientIds) triage.remove(patientId);
        injectedPatientIds.clear();
        network.clearDisasterConditions();
        hospitals.restoreDefaults();
        for (String node : TEMPORARY_NODES) network.setNodeActive(node, false);
        network.setNodeActive(TRAUMA_CENTER, true);
        activeScenario = NORMAL;
        preferredHospital = null;
    }

    public synchronized boolean isNodeActive(String nodeId) {
        return hospitals.contains(nodeId)
                ? hospitals.isActive(nodeId) && network.isNodeActive(nodeId)
                : network.isNodeActive(nodeId);
    }

    public synchronized boolean isEdgePassable(String u, String v) { return network.isEdgePassable(u, v); }

    public synchronized void loadEarthquakeCasualties() {
        for (int index = 0; index < CASUALTY_CONDITIONS.size(); index++) {
            String patientId = String.format("EQ-%03d", 201 + index);
            if (injectedPatientIds.contains(patientId)) continue;
            int age = 19 + (index * 7) % 61;
            double risk = 8.0 + (index % 3) * 0.8;
            double priority = 150.0 + (9 - index) * 2.5;
            PatientNode patient = PatientNode.withPriority(patientId, "Disaster Casualty " + (index + 1),
                    CASUALTY_CONDITIONS.get(index), index < 7 ? 1 : 2, 0, risk, age,
                    index < 7 ? PatientNode.DisasterTriageTag.RED : PatientNode.DisasterTriageTag.YELLOW,
                    priority);
            triage.insert(patient);
            injectedPatientIds.add(patientId);
        }
    }

    public synchronized void severMainBridge() {
        severBidirectional("Inter_B", "Inter_C");
    }

    public synchronized void divertToFieldHospital() {
        activateDisasterCorridors();
        hospitals.setActive(FIELD_HOSPITAL_NORTH, true);
        network.setNodeActive(FIELD_HOSPITAL_NORTH, true);
        preferredHospital = FIELD_HOSPITAL_NORTH;
    }

    public synchronized String getActiveScenario() { return activeScenario; }

    public synchronized String getPreferredHospital() { return preferredHospital; }

    public synchronized Map<String, Object> snapshot() {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("scenario", activeScenario);
        result.put("preferredHospital", preferredHospital == null ? "" : preferredHospital);
        result.put("temporaryPatients", injectedPatientIds.size());
        result.put("hospitals", hospitals.snapshot());
        return Map.copyOf(result);
    }

    private void activateDisasterCorridors() {
        for (String node : CORRIDOR_NODES) network.setNodeActive(node, true);
    }

    private void severBidirectional(String first, String second) {
        network.severEdge(first, second);
        network.severEdge(second, first);
    }

    private void registerTemporaryFacilities() {
        Map<String, Integer> specialties = Map.of("TRAUMA", 20, "BURN", 8, "CATH LAB", 4);
        if (!hospitals.contains(FIELD_HOSPITAL_NORTH))
            hospitals.registerHospital(FIELD_HOSPITAL_NORTH, 15, specialties, false);
        if (!hospitals.contains(HELIPAD_ALPHA))
            hospitals.registerHospital(HELIPAD_ALPHA, 8, specialties, false);
    }

    private void registerDisasterCorridors() {
        for (String node : TEMPORARY_NODES) network.addNode(node);
        addBidirectional("IncidentScene", PERIPHERAL_RING_ROAD, 4.0, 2.5, 50);
        addBidirectional(PERIPHERAL_RING_ROAD, FIELD_HOSPITAL_NORTH, 5.0, 3.0, 50);
        addBidirectional("Inter_A", DISASTER_ZONE_SECTOR_4, 3.0, 2.0, 45);
        addBidirectional(DISASTER_ZONE_SECTOR_4, EMERGENCY_AIRWAY_CORRIDOR, 2.0, 1.2, 70);
        addBidirectional("IncidentScene", EMERGENCY_AIRWAY_CORRIDOR, 2.5, 1.5, 70);
        addBidirectional(EMERGENCY_AIRWAY_CORRIDOR, HELIPAD_ALPHA, 3.0, 1.8, 70);
    }

    private void addBidirectional(String first, String second, double minutes, double km, double speed) {
        network.addRoadSegment(first, second, minutes, km, speed);
        network.addRoadSegment(second, first, minutes, km, speed);
    }
}