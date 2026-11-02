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

        CADHttpServer server = new CADHttpServer(engine, port);
        SimulatedCallGenerator stream = new SimulatedCallGenerator(engine);
        try {
            server.start();
            stream.start();
            System.out.println("HTTP Server is live on port " + port);
        } catch (Exception e) {
            stream.close();
            server.close();
            e.printStackTrace();
            System.exit(1);
        }

        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            stream.close();
            server.close();
        }, "cad-shutdown"));

        System.out.println("System operational. Cloud dispatch endpoints ready.");
    }
}
