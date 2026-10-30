package stream;

import cad.ThreadSafeDispatchEngine;
import model.PatientNode;

import java.util.Objects;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.ThreadLocalRandom;

/** Generates synthetic emergency calls and ages the waiting queue on a daemon thread. */
public final class SimulatedCallGenerator implements Runnable, AutoCloseable {
    private static final long CALL_INTERVAL_NANOS = TimeUnit.SECONDS.toNanos(12);
    private static final long AGING_INTERVAL_NANOS = TimeUnit.SECONDS.toNanos(20);
    private static final String[] COMPLAINTS = {
            "Severe Stroke", "Fractured Arm", "Respiratory Distress", "Chest Pain",
            "Road Trauma", "Severe Burn", "Pediatric Fever"
    };

    private final ThreadSafeDispatchEngine engine;
    private final boolean debug;
    private volatile boolean running;
    private volatile Thread worker;
    private int patientSequence;

    public SimulatedCallGenerator(ThreadSafeDispatchEngine engine) {
        this(engine, false);
    }

    public SimulatedCallGenerator(ThreadSafeDispatchEngine engine, boolean debug) {
        this.engine = Objects.requireNonNull(engine, "engine");
        this.debug = debug;
    }

    public synchronized void start() {
        if (running) return;
        Thread current = worker;
        if (current != null && current.isAlive()) return;
        running = true;
        worker = new Thread(this, "cad-simulated-call-generator");
        worker.setDaemon(true);
        worker.start();
    }

    public void stop() {
        Thread current;
        synchronized (this) {
            running = false;
            current = worker;
            if (current != null) current.interrupt();
        }
        if (current != null && current != Thread.currentThread()) {
            try {
                current.join();
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
            }
            synchronized (this) {
                if (worker == current) worker = null;
            }
        }
    }

    @Override
    public void close() {
        stop();
    }

    @Override
    public void run() {
        long nextCall = System.nanoTime() + CALL_INTERVAL_NANOS;
        long nextAging = System.nanoTime() + AGING_INTERVAL_NANOS;
        try {
            while (running) {
                long now = System.nanoTime();
                if (now >= nextCall) {
                    generateCallSafely();
                    nextCall = System.nanoTime() + CALL_INTERVAL_NANOS;
                }
                now = System.nanoTime();
                if (now >= nextAging) {
                    agePatientsSafely();
                    nextAging = System.nanoTime() + AGING_INTERVAL_NANOS;
                }
                long untilNextTask = Math.min(nextCall, nextAging) - System.nanoTime();
                if (untilNextTask > 0) TimeUnit.NANOSECONDS.sleep(untilNextTask);
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
        } finally {
            running = false;
        }
    }

    private void generateCallSafely() {
        try {
            ThreadLocalRandom random = ThreadLocalRandom.current();
            String patientId = String.format("P-%03d", ++patientSequence);
            String complaint = COMPLAINTS[random.nextInt(COMPLAINTS.length)];
            int esiLevel = random.nextInt(1, 6);
            double vitalsRisk = Math.round(random.nextDouble(1.0, 10.1) * 10.0) / 10.0;
            int age = random.nextInt(1, 91);
            PatientNode patient = engine.admit(patientId, complaint, esiLevel, 0, vitalsRisk, age);
            if (debug) {
                System.out.println("[STREAM] Injected patient " + patient.getPatientId()
                        + " (ESI " + patient.getEsiLevel() + ") | Queue size: " + engine.triageSize());
            }
        } catch (RuntimeException exception) {
            if (debug) System.err.println("[STREAM] Patient injection skipped: " + exception.getMessage());
        }
    }

    private void agePatientsSafely() {
        try {
            engine.ageWaitingPatients(1);
            if (debug) System.out.println("[AGING] Incremented wait times by 1m");
        } catch (RuntimeException exception) {
            if (debug) System.err.println("[AGING] Wait-time aging skipped: " + exception.getMessage());
        }
    }
}