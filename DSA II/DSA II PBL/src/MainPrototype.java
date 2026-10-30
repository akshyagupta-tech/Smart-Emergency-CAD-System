import java.util.*;

public class MainPrototype {
    private static DynamicTriageHeap triageQueue = new DynamicTriageHeap();
    private static EmergencyNetwork cityGrid = new EmergencyNetwork();
    private static BPlusTreeTelemetry telemetryStore = new BPlusTreeTelemetry();
    private static List<KnapsackPayload.MedicalItem> equipmentCatalog = new ArrayList<>();
    private static Scanner scanner = new Scanner(System.in);

    // Track hospital bed capacities
    private static Map<String, Integer> hospitalIcuBeds = new HashMap<>();

    public static void main(String[] args) {
        initializeCityInfrastructure();

        while (true) {
            System.out.println("\n======================================================================");
            System.out.println("  SMART EMERGENCY RESPONSE DISPATCH SYSTEM (SDG 3) - OPERATIONAL CONSOLE");
            System.out.println("  Candidate: Akshya Gupta | Course: CCSE0301 (DSA-II)");
            System.out.println("======================================================================");
            System.out.println("1. Register & Triage Incoming Emergency Patient (Unit 1: Max-Heap)");
            System.out.println("2. Dispatch Next Highest-Acuity Patient & Route Ambulance (Units 1 & 2)");
            System.out.println("3. Optimize Outbound Ambulance Equipment Loadout (Unit 3: 0/1 Knapsack)");
            System.out.println("4. Plan Multi-Scene Mass Casualty Tour (Unit 4: Branch & Bound TSP)");
            System.out.println("5. Query Fleet Telemetry & Audit Logs (Unit 5: B+ Tree)");
            System.out.println("6. Simulate Traffic Congestion Spike & Reroute");
            System.out.println("7. Exit System");
            System.out.print("\nSelect Operation [1-7]: ");

            String choice = scanner.nextLine().trim();

            switch (choice) {
                case "1":
                    registerPatient();
                    break;
                case "2":
                    dispatchNextEmergency();
                    break;
                case "3":
                    optimizeGear();
                    break;
                case "4":
                    runMciTour();
                    break;
                case "5":
                    queryTelemetry();
                    break;
                case "6":
                    simulateTrafficCongestion();
                    break;
                case "7":
                    System.out.println("\nShutting down Emergency Response Console. System Offline.");
                    return;
                default:
                    System.out.println("Invalid selection. Please choose an option from 1 to 7.");
            }
        }
    }

    private static void initializeCityInfrastructure() {
        // Initialize Bed Availability
        hospitalIcuBeds.put("TraumaCenter", 3);
        hospitalIcuBeds.put("MetroGeneral", 1);

        // Build City Transit Road Network
        cityGrid.addRoadSegment("AmbulanceDepot", "Inter_A", 4);
        cityGrid.addRoadSegment("AmbulanceDepot", "Inter_B", 3);
        cityGrid.addRoadSegment("Inter_A", "IncidentScene", 5);
        cityGrid.addRoadSegment("Inter_B", "Inter_C", 1);
        cityGrid.addRoadSegment("Inter_C", "IncidentScene", 2);
        cityGrid.addRoadSegment("IncidentScene", "TraumaCenter", 6);
        cityGrid.addRoadSegment("IncidentScene", "MetroGeneral", 8);

        // Standard Equipment Inventory
        equipmentCatalog.add(new KnapsackPayload.MedicalItem("Portable Ventilator", 12, 85));
        equipmentCatalog.add(new KnapsackPayload.MedicalItem("Defibrillator Unit", 8, 95));
        equipmentCatalog.add(new KnapsackPayload.MedicalItem("Portable ECMO", 25, 90));
        equipmentCatalog.add(new KnapsackPayload.MedicalItem("Pediatric Trauma Kit", 5, 45));
        equipmentCatalog.add(new KnapsackPayload.MedicalItem("Blood Infusion Cooler", 10, 75));

        // Seed initial patients
        triageQueue.insert(new PatientNode("P101", "Cardiac Arrest", 1, 3, 9.8, 67));
        triageQueue.insert(new PatientNode("P102", "Minor Fracture", 4, 30, 2.0, 24));
        triageQueue.insert(new PatientNode("P103", "Acute Polytrauma", 1, 1, 9.2, 38));

        // Seed initial telemetry frames
        telemetryStore.insert(new BPlusTreeTelemetry.TelemetryRecord(1001, "AMB-01", 28.4712, 77.4921, "DEPOT_STANDBY"));
        telemetryStore.insert(new BPlusTreeTelemetry.TelemetryRecord(1005, "AMB-01", 28.4735, 77.4950, "EN_ROUTE"));
        telemetryStore.insert(new BPlusTreeTelemetry.TelemetryRecord(1010, "AMB-02", 28.4801, 77.5011, "PATIENT_ONBOARD"));
    }

    private static void registerPatient() {
        System.out.println("\n--- [PATIENT INTAKE & DYNAMIC SCORING] ---");
        System.out.print("Enter Patient ID (e.g., P105): ");
        String id = scanner.nextLine().trim();
        System.out.print("Enter Condition / Chief Complaint: ");
        String desc = scanner.nextLine().trim();
        System.out.print("Enter ESI Level (1=Resuscitation, 2=Emergent, 3=Urgent, 4=Less-Urgent, 5=Non-Urgent): ");
        int esi = Integer.parseInt(scanner.nextLine().trim());
        System.out.print("Enter Patient Age: ");
        int age = Integer.parseInt(scanner.nextLine().trim());
        System.out.print("Enter Vitals Risk Anomaly Score [0.0 - 10.0]: ");
        double vitals = Double.parseDouble(scanner.nextLine().trim());

        PatientNode p = new PatientNode(id, desc, esi, 0, vitals, age);
        triageQueue.insert(p);

        System.out.printf("Patient registered successfully. Calculated Priority Score: %.2f%n", p.getPriorityScore());
        triageQueue.printQueue();
    }

    private static void dispatchNextEmergency() {
        System.out.println("\n--- [AUTOMATED PIPELINE: TRIAGE -> DISPATCH -> ROUTING] ---");
        if (triageQueue.isEmpty()) {
            System.out.println("Triage Queue is currently empty. No active dispatch required.");
            return;
        }

        PatientNode patient = triageQueue.extractMax();
        System.out.printf("HIGHEST ACUITY CASE EXTRACTED: %s | Complaint: %s | Priority: %.2f%n",
                patient.getPatientId(), patient.getName(), patient.getPriorityScore());

        // Check destination hospital capacity
        String assignedHospital = "TraumaCenter";
        int availableBeds = hospitalIcuBeds.getOrDefault(assignedHospital, 0);
        if (availableBeds <= 0) {
            System.out.printf("ALERT: %s ICU at capacity! Diverting to secondary facility 'MetroGeneral'...%n", assignedHospital);
            assignedHospital = "MetroGeneral";
        } else {
            hospitalIcuBeds.put(assignedHospital, availableBeds - 1);
            System.out.printf("Bed Confirmed at %s (Beds remaining: %d)%n", assignedHospital, availableBeds - 1);
        }

        // Real-time navigation
        System.out.println("\nPhase A: Ambulance Depot -> Patient Scene:");
        cityGrid.findShortestPath("AmbulanceDepot", "IncidentScene");

        System.out.printf("\nPhase B: Incident Scene -> %s:%n", assignedHospital);
        cityGrid.findShortestPath("IncidentScene", assignedHospital);

        // Log telemetry frame
        long currentTs = System.currentTimeMillis() / 1000;
        telemetryStore.insert(new BPlusTreeTelemetry.TelemetryRecord(currentTs, "AMB-01", 28.4795, 77.4980, "EN_ROUTE_HOSPITAL"));
        System.out.println("\nDispatch event committed to B+ Tree index with timestamp: " + currentTs);
    }

    private static void optimizeGear() {
        System.out.println("\n--- [UNIT 3: 0/1 KNAPSACK GEAR ALLOCATION] ---");
        System.out.print("Enter outbound vehicle payload capacity in kg (default: 30): ");
        String input = scanner.nextLine().trim();
        int cap = input.isEmpty() ? 30 : Integer.parseInt(input);

        KnapsackPayload.optimizePayload(equipmentCatalog, cap);
    }

    private static void runMciTour() {
        System.out.println("\n--- [UNIT 4: BRANCH & BOUND MULTI-SCENE MCI ROUTING] ---");
        int[][] mciCluster = {
            { 0,   10,  15,  20 },
            { 10,  0,   35,  25 },
            { 15,  35,  0,   30 },
            { 20,  25,  30,  0  }
        };
        MCIRoutingTSP mciSolver = new MCIRoutingTSP(mciCluster);
        mciSolver.solve();
    }

    private static void queryTelemetry() {
        System.out.println("\n--- [UNIT 5: B+ TREE TIME-SERIES RANGE QUERY] ---");
        System.out.print("Enter Start Timestamp (e.g., 1000): ");
        long start = Long.parseLong(scanner.nextLine().trim());
        System.out.print("Enter End Timestamp (e.g., 1020): ");
        long end = Long.parseLong(scanner.nextLine().trim());

        List<BPlusTreeTelemetry.TelemetryRecord> records = telemetryStore.rangeQuery(start, end);
        System.out.printf("\nRecords retrieved from linked leaves [%d to %d]:%n", start, end);
        if (records.isEmpty()) {
            System.out.println("No telemetry records found within the specified interval.");
        } else {
            for (BPlusTreeTelemetry.TelemetryRecord r : records) {
                System.out.println("  • " + r);
            }
        }
    }

    private static void simulateTrafficCongestion() {
        System.out.println("\n--- [TRAFFIC DYNAMICS SIMULATION] ---");
        System.out.println("Applying peak congestion on primary artery (Inter_B <---> Inter_C: 1 min -> 12 mins)");
        cityGrid.addRoadSegment("Inter_B", "Inter_C", 12);

        System.out.println("\nRecalculating optimal path from AmbulanceDepot -> IncidentScene under congestion:");
        cityGrid.findShortestPath("AmbulanceDepot", "IncidentScene");
    }
}
