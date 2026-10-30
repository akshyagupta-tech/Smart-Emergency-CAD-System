import cad.ThreadSafeDispatchEngine;
import logistics.KnapsackPayload;
import model.PatientNode;
import routing.EmergencyNetwork;
import routing.MCIRoutingTSP;
import server.CADHttpServer;
import storage.BPlusTreeTelemetry;
import stream.SimulatedCallGenerator;
import triage.DynamicTriageHeap;

import java.io.IOException;
import java.util.List;
import java.util.Map;
import java.util.Scanner;

/** CLI and embedded dashboard share one lock-protected CAD engine. */
public final class MainCADConsole {
    private final Scanner scanner = new Scanner(System.in);
    private final ThreadSafeDispatchEngine engine;

    private MainCADConsole(ThreadSafeDispatchEngine engine) { this.engine = engine; }

    public static void main(String[] args) {
        ThreadSafeDispatchEngine engine = new ThreadSafeDispatchEngine();
        CADHttpServer webServer = new CADHttpServer(engine, 8080);
        SimulatedCallGenerator callGenerator = new SimulatedCallGenerator(engine);
        try {
            webServer.start();
            System.out.println("Dispatcher dashboard available at http://localhost:8080");
        } catch (IOException exception) {
            System.err.println("Dashboard could not bind to port 8080: " + exception.getMessage());
            System.err.println("The CLI will continue; stop the process using port 8080 to enable the dashboard.");
        }
        callGenerator.start();
        try {
            new MainCADConsole(engine).run();
        } finally {
            callGenerator.close();
            webServer.close();
        }
    }

    private void run() {
        while (true) {
            printMenu();
            String choice = prompt("Select operation [1-8]: ");
            if (choice.equalsIgnoreCase("EXIT")) { System.out.println("CAD console closed."); return; }
            try {
                switch (choice) {
                    case "1" -> patientIntake();
                    case "2" -> dispatchPipeline();
                    case "3" -> payloadConsole();
                    case "4" -> planMciTour();
                    case "5" -> telemetryAudit();
                    case "6" -> simulateCongestion();
                    case "7" -> runBenchmarks();
                    case "8" -> disasterSimulation();
                    default -> System.out.println("Choose a menu option from 1 to 8.");
                }
            } catch (IllegalArgumentException | IllegalStateException | ArithmeticException exception) {
                System.out.println("Operation error: " + exception.getMessage());
            }
        }
    }

    private void printMenu() {
        System.out.println("\n============================================================");
        System.out.println(" SMART EMERGENCY RESPONSE PRIORITIZATION SYSTEM | CCSE0301");
        System.out.println("============================================================");
        System.out.println("1. Patient Intake & Dynamic Triage");
        System.out.println("2. Automated Emergency Dispatch Pipeline");
        System.out.println("3. 0/1 Knapsack Payload Loading Console");
        System.out.println("4. Mass Casualty Branch & Bound MCI Tour Planner");
        System.out.println("5. B+ Tree Historical Telemetry Audit Range Query");
        System.out.println("6. Dynamic Traffic Congestion Simulator");
        System.out.println("7. Run Full Automated Benchmark Suite");
        System.out.println("8. Disaster Simulation Mode (Earthquake / Collapse / Field Hospital Fallback)");
        System.out.println("Web dashboard: http://localhost:8080 | Type EXIT to quit");
    }

    private void disasterSimulation() {
        System.out.println("\n--- Disaster Simulation Mode ---");
        System.out.println("1. Earthquake / building collapse");
        System.out.println("2. Tsunami / flood inundation");
        System.out.println("3. Reset to normal operations");
        int choice = readInt("Select scenario [1-3]: ", 1, 3);
        Map<String, Object> state = switch (choice) {
            case 1 -> engine.activateDisasterScenario("EARTHQUAKE_COLLAPSE");
            case 2 -> engine.activateDisasterScenario("TSUNAMI_FLOOD_INUNDATION");
            default -> engine.resetDisasterScenario();
        };
        System.out.println("Active scenario: " + state.get("scenario"));
        System.out.println("Preferred hospital: " + state.get("preferredHospital"));
        engine.printTriageQueue();
    }

    private void patientIntake() {
        System.out.println("\n--- Patient Intake & Dynamic Triage ---");
        PatientNode patient = engine.admit(readNonBlank("Patient ID: "), readNonBlank("Condition / chief complaint: "),
                readInt("ESI level (1-5): ", 1, 5), readInt("Wait time in minutes: ", 0, Integer.MAX_VALUE),
                readDouble("Vitals risk score (0-10): ", 0, 10), readInt("Age (0-130): ", 0, 130));
        System.out.println("Added: " + patient);
        engine.printTriageQueue();
    }

    private void dispatchPipeline() {
        System.out.println("\n--- Automated Emergency Dispatch Pipeline ---");
        Map<String, Object> result = engine.executeDispatch();
        Map<?, ?> patient = asMap(result.get("patient"));
        Map<?, ?> route = asMap(result.get("route"));
        Map<?, ?> payload = asMap(result.get("payload"));
        System.out.printf("Dispatch %s: %s (%s), assigned to %s%s.%n", result.get("dispatchId"),
                patient.get("patientId"), patient.get("condition"), result.get("hospital"),
                Boolean.TRUE.equals(result.get("diverted")) ? " after diversion" : "");
        System.out.println("Depot -> scene: " + formatPath(asMap(route.get("toScene"))));
        System.out.println("Scene -> hospital: " + formatPath(asMap(route.get("toHospital"))));
        System.out.printf("Vehicle %s | Total route %.2f min | Payload %s/%s kg, utility %s.%n",
                result.get("vehicleId"), route.get("totalMinutes"), payload.get("weightKg"),
                payload.get("capacityKg"), payload.get("utilityScore"));
        System.out.println("Telemetry committed: " + result.get("telemetry"));
    }

    private void payloadConsole() {
        int capacity = readInt("Payload capacity in kg: ", 0, 100000);
        KnapsackPayload.Result result = engine.optimizePayload(capacity);
        System.out.printf("Maximum utility: %d | Payload: %d/%d kg%n", result.getMaxUtility(),
                result.getTotalWeightKg(), capacity);
        for (KnapsackPayload.MedicalItem item : result.getSelectedItems()) System.out.println("  " + item);
        System.out.println("Rolling-array cross-check: "
                + KnapsackPayload.optimizePayloadRolling(result.getSelectedItems(), capacity));
    }

    private void planMciTour() {
        System.out.println("\n--- Mass Casualty Branch & Bound MCI Tour ---");
        int[][] costs = {{0, 10, 15, 20}, {10, 0, 35, 25}, {15, 35, 0, 30}, {20, 25, 30, 0}};
        MCIRoutingTSP.Result result = new MCIRoutingTSP(costs,
                new String[]{"Command Post", "Scene Alpha", "Scene Bravo", "Scene Charlie"}).solve();
        if (result.hasTour()) System.out.println("Tour sequence: " + String.join(" -> ", result.getTour()));
    }

    private void telemetryAudit() {
        long start = readLong("Start timestamp (Unix seconds): ", 0, Long.MAX_VALUE);
        long end = readLong("End timestamp (Unix seconds): ", 0, Long.MAX_VALUE);
        List<Map<String, Object>> records = engine.telemetryQuery(start, end);
        System.out.printf("%d record(s) in inclusive range [%d, %d]:%n", records.size(), start, end);
        if (records.isEmpty()) System.out.println("No matching telemetry.");
        for (Map<String, Object> record : records) System.out.println("  " + record);
    }

    private void simulateCongestion() {
        System.out.println("Baseline route: " + formatPath(engine.routeSnapshot("AmbulanceDepot", "IncidentScene")));
        Map<String, Object> result = engine.spikeCongestion("Inter_B", "Inter_C", 12.0,
                "AmbulanceDepot", "IncidentScene");
        System.out.println("Congestion applied to Inter_B -> Inter_C (12x).");
        System.out.println("Rerouted route: " + formatPath(asMap(result.get("reroutedPath"))));
    }

    private void runBenchmarks() {
        System.out.println("\n--- Automated DSA Benchmark Suite ---");
        DynamicTriageHeap heap = new DynamicTriageHeap();
        heap.insert(new PatientNode("B1", "Benchmark low", 5, 0, 0, 30));
        heap.insert(new PatientNode("B2", "Benchmark critical", 1, 0, 9, 70));
        if (!"B2".equals(heap.extractMax().getPatientId())) throw new IllegalStateException("Heap benchmark failed.");
        System.out.println("1. Dynamic triage max-heap: PASS");

        EmergencyNetwork graph = new EmergencyNetwork();
        graph.addRoadSegment("A", "B", 2, 1, 30);
        graph.addRoadSegment("B", "A", 2, 1, 30);
        graph.addRoadSegment("B", "C", 3, 2, 40);
        graph.addRoadSegment("C", "B", 3, 2, 40);
        if (!graph.findShortestPath("A", "C").isReachable() || !graph.computeKruskalMST().isConnected())
            throw new IllegalStateException("Road graph benchmark failed.");
        graph.updateCongestion("A", "B", 3);
        System.out.println("2. Directed Dijkstra + congestion + Kruskal: PASS");

        List<KnapsackPayload.MedicalItem> items = List.of(
                new KnapsackPayload.MedicalItem("Airway Kit", 5, 20),
                new KnapsackPayload.MedicalItem("Monitor", 8, 30),
                new KnapsackPayload.MedicalItem("Blood Cooler", 7, 25));
        KnapsackPayload.Result payload = KnapsackPayload.optimizePayload(items, 13);
        if (payload.getMaxUtility() != KnapsackPayload.optimizePayloadRolling(items, 13))
            throw new IllegalStateException("Knapsack benchmark failed.");
        System.out.println("3. 0/1 Knapsack 2D and rolling DP: PASS");

        MCIRoutingTSP.Result tour = new MCIRoutingTSP(new int[][]{
                {0, 10, 15, 20}, {10, 0, 35, 25}, {15, 35, 0, 30}, {20, 25, 30, 0}
        }).solve();
        if (!tour.hasTour() || tour.getTotalLatency() != 80) throw new IllegalStateException("MCI tour benchmark failed.");
        System.out.println("4. Reduced-cost MCI TSP: PASS");

        BPlusTreeTelemetry index = new BPlusTreeTelemetry();
        for (int timestamp = 20; timestamp >= 1; timestamp--)
            index.insert(new BPlusTreeTelemetry.TelemetryRecord(timestamp, "BENCH-01", 0, 0, "OK"));
        if (index.rangeQuery(5, 10).size() != 6 || index.size() != 20)
            throw new IllegalStateException("B+ tree benchmark failed.");
        System.out.println("5. Order-4 B+ tree range query: PASS");
        System.out.println("All five benchmark units passed.");
    }

    private static String formatPath(Map<?, ?> path) {
        if (!Boolean.TRUE.equals(path.get("reachable"))) return "No route available.";
        return String.join(" -> ", ((List<?>) path.get("nodes")).stream().map(String::valueOf).toList())
                + " (" + String.format("%.2f", ((Number) path.get("totalMinutes")).doubleValue()) + " min)";
    }

    private static Map<?, ?> asMap(Object value) {
        if (!(value instanceof Map<?, ?> map)) throw new IllegalStateException("Unexpected engine result.");
        return map;
    }

    private String readNonBlank(String label) {
        while (true) {
            String value = prompt(label);
            if (!value.isBlank()) return value;
            System.out.println("A value is required.");
        }
    }

    private int readInt(String label, int minimum, int maximum) {
        while (true) try {
            int value = Integer.parseInt(prompt(label));
            if (value >= minimum && value <= maximum) return value;
            System.out.printf("Enter a value from %d to %d.%n", minimum, maximum);
        } catch (NumberFormatException exception) { System.out.println("Enter a whole number."); }
    }

    private long readLong(String label, long minimum, long maximum) {
        while (true) try {
            long value = Long.parseLong(prompt(label));
            if (value >= minimum && value <= maximum) return value;
            System.out.println("Value is outside the permitted range.");
        } catch (NumberFormatException exception) { System.out.println("Enter a valid integer timestamp."); }
    }

    private double readDouble(String label, double minimum, double maximum) {
        while (true) try {
            double value = Double.parseDouble(prompt(label));
            if (Double.isFinite(value) && value >= minimum && value <= maximum) return value;
            System.out.printf("Enter a finite value from %.1f to %.1f.%n", minimum, maximum);
        } catch (NumberFormatException exception) { System.out.println("Enter a valid decimal number."); }
    }

    private String prompt(String label) {
        System.out.print(label);
        return scanner.nextLine().trim();
    }
}