import cad.ThreadSafeDispatchEngine;
import server.CADHttpServer;
import stream.SimulatedCallGenerator;

public class ServerMain {
    public static void main(String[] args) {
        int port = 8080;
        String envPort = System.getenv("PORT");
        if (envPort != null && !envPort.isEmpty()) {
            try {
                port = Integer.parseInt(envPort);
            } catch (NumberFormatException ignored) {}
        }

        System.out.println("Starting Emergency CAD Cloud Server on port: " + port);

        ThreadSafeDispatchEngine engine = new ThreadSafeDispatchEngine();

        try {
            CADHttpServer server = new CADHttpServer(engine, port);
            server.start();
            System.out.println("HTTP Server is live on port " + port);
        } catch (Exception e) {
            e.printStackTrace();
            System.exit(1);
        }

        SimulatedCallGenerator stream = new SimulatedCallGenerator(engine);
        Thread streamThread = new Thread(stream, "CallGeneratorStream");
        streamThread.setDaemon(false);
        streamThread.start();

        System.out.println("System operational. Cloud dispatch endpoints ready.");
    }
}
