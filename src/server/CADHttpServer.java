package server;

import cad.ThreadSafeDispatchEngine;
import stream.SimulatedCallGenerator;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

/** Embedded zero-dependency REST server. Run with {@code java -cp bin server.CADHttpServer}. */
public final class CADHttpServer implements AutoCloseable {
    private static final int MAX_REQUEST_BYTES = 64 * 1024;
    private final ThreadSafeDispatchEngine engine;
    private final int port;
    private HttpServer server;
    private ThreadPoolExecutor executor;

    public CADHttpServer(ThreadSafeDispatchEngine engine) { this(engine, 8080); }

    public CADHttpServer(ThreadSafeDispatchEngine engine, int port) {
        if (engine == null) throw new IllegalArgumentException("Dispatch engine is required.");
        if (port < 1 || port > 65535) throw new IllegalArgumentException("Port must be from 1 to 65535.");
        this.engine = engine;
        this.port = port;
    }

    public synchronized void start() throws IOException {
        if (server != null) return;
        server = HttpServer.create(new InetSocketAddress("0.0.0.0", port), 0);
        ThreadFactory factory = task -> {
            Thread thread = new Thread(task, "cad-http-worker");
            thread.setDaemon(true);
            return thread;
        };
        executor = new ThreadPoolExecutor(4, 8, 30, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(128), factory, new ThreadPoolExecutor.CallerRunsPolicy());
        server.setExecutor(executor);
        server.createContext("/", this::handle);
        server.start();
    }

    public int getPort() { return port; }

    @Override
    public synchronized void close() {
        if (server != null) {
            server.stop(1);
            server = null;
        }
        if (executor != null) {
            executor.shutdownNow();
            executor = null;
        }
    }

    private void handle(HttpExchange exchange) throws IOException {
        try {
            String method = exchange.getRequestMethod();
            String path = exchange.getRequestURI().getPath();
            if (("GET".equals(method) || "HEAD".equals(method)) && "/".equals(path)) {
                String dashboard = loadDashboard();
                if (dashboard == null) {
                    String message = "Dashboard HTML not found. Checked src/server/web/index.html, web/index.html, and index.html.";
                    if ("HEAD".equals(method)) {
                        sendHeadersOnly(exchange, 404, "text/plain; charset=UTF-8");
                    } else {
                        sendText(exchange, 404, "text/plain; charset=UTF-8", message);
                    }
                } else {
                    if ("HEAD".equals(method)) {
                        sendHeadersOnly(exchange, 200, "text/html; charset=UTF-8");
                    } else {
                        sendText(exchange, 200, "text/html; charset=UTF-8", dashboard);
                    }
                }
                return;
            }
            if ("GET".equals(method) && "/api/health".equals(path)) {
                sendJson(exchange, 200, Map.of("status", "ok", "service", "Smart Emergency Response Prioritization System"));
                return;
            }
            if ("GET".equals(method) && "/api/disaster/status".equals(path)) {
                sendJson(exchange, 200, engine.disasterSnapshot());
                return;
            }
            if ("POST".equals(method) && "/api/disaster/scenario".equals(path)) {
                Map<String, Object> input = readJsonObject(exchange);
                sendJson(exchange, 200, engine.activateDisasterScenario(string(input, "scenarioName")));
                return;
            }
            if ("POST".equals(method) && "/api/disaster/reset".equals(path)) {
                sendJson(exchange, 200, engine.resetDisasterScenario());
                return;
            }
            if ("POST".equals(method) && "/api/disaster/casualties".equals(path)) {
                sendJson(exchange, 200, engine.loadEarthquakeCasualties());
                return;
            }
            if ("POST".equals(method) && "/api/disaster/sever-main-bridge".equals(path)) {
                sendJson(exchange, 200, engine.severMainBridge());
                return;
            }
            if ("POST".equals(method) && "/api/disaster/divert-field-hospital".equals(path)) {
                sendJson(exchange, 200, engine.divertToFieldHospital());
                return;
            }
            if ("GET".equals(method) && "/api/network".equals(path)) {
                sendJson(exchange, 200, engine.networkSnapshot());
                return;
            }
            if ("GET".equals(method) && "/api/triage/queue".equals(path)) {
                List<Map<String, Object>> patients = new ArrayList<>();
                engine.triageSnapshot().forEach(patient -> patients.add(ThreadSafeDispatchEngine.patientMap(patient)));
                sendJson(exchange, 200, Map.of("count", patients.size(), "patients", patients));
                return;
            }
            if ("POST".equals(method) && "/api/triage/admit".equals(path)) {
                Map<String, Object> input = readJsonObject(exchange);
                Object patient = engine.admit(string(input, "patientId"), string(input, "condition"),
                        integer(input, "esiLevel"), integer(input, "waitTimeMinutes", 0),
                        decimal(input, "vitalsRiskScore"), integer(input, "age"));
                sendJson(exchange, 201, Map.of("accepted", true,
                        "patient", ThreadSafeDispatchEngine.patientMap((model.PatientNode) patient)));
                return;
            }
            if ("POST".equals(method) && "/api/dispatch/execute".equals(path)) {
                sendJson(exchange, 200, engine.executeDispatch());
                return;
            }
            if ("POST".equals(method) && "/api/congestion/spike".equals(path)) {
                Map<String, Object> input = readJsonObject(exchange);
                sendJson(exchange, 200, engine.spikeCongestion(string(input, "from"), string(input, "to"),
                        decimal(input, "congestionMultiplier"), optionalString(input, "source", "AmbulanceDepot"),
                        optionalString(input, "destination", "IncidentScene")));
                return;
            }
            if ("GET".equals(method) && "/api/telemetry/query".equals(path)) {
                Map<String, String> query = parseQuery(exchange.getRequestURI().getRawQuery());
                long start = queryLong(query, "start");
                long end = queryLong(query, "end");
                sendJson(exchange, 200, Map.of("start", start, "end", end,
                        "records", engine.telemetryQuery(start, end)));
                return;
            }
            if ("GET".equals(method) && "/api/mci/solve".equals(path)) {
                Map<String, Object> result = new LinkedHashMap<>(engine.solveMci());
                List<String> locations = List.of("Command Post", "Scene Alpha", "Scene Bravo", "Scene Charlie");
                List<Integer> tourIndices = new ArrayList<>();
                Object tourValue = result.get("tour");
                if (tourValue instanceof List<?> tour) {
                    for (Object location : tour) {
                        int index = locations.indexOf(location);
                        if (index < 0) {
                            tourIndices.clear();
                            break;
                        }
                        tourIndices.add(index);
                    }
                }
                long totalPermutations = ((Number) result.get("totalPermutations")).longValue();
                long prunedBranches = ((Number) result.get("prunedBranches")).longValue();
                result.put("tourIndices", tourIndices);
                result.put("prunedPercent", totalPermutations == 0
                        ? 0.0 : prunedBranches * 100.0 / totalPermutations);
                sendJson(exchange, 200, result);
                return;
            }
            if ("GET".equals(method) && "/api/resources/payload".equals(path)) {
                Map<String, String> query = parseQuery(exchange.getRequestURI().getRawQuery());
                int capacity = query.containsKey("capacity") ? Integer.parseInt(query.get("capacity")) : 30;
                sendJson(exchange, 200, engine.payloadSnapshot(capacity));
                return;
            }
            sendJson(exchange, 404, Map.of("error", "Endpoint not found."));
        } catch (IllegalArgumentException exception) {
            sendJson(exchange, 400, Map.of("error", safeMessage(exception)));
        } catch (IllegalStateException exception) {
            sendJson(exchange, 409, Map.of("error", safeMessage(exception)));
        } catch (Exception exception) {
            sendJson(exchange, 500, Map.of("error", "Internal server error."));
            System.err.println("CAD HTTP request failed: " + exception.getClass().getSimpleName() + ": " + safeMessage(exception));
        } finally {
            exchange.close();
        }
    }

    private static Map<String, Object> readJsonObject(HttpExchange exchange) throws IOException {
        byte[] bytes;
        try (InputStream input = exchange.getRequestBody()) { bytes = input.readNBytes(MAX_REQUEST_BYTES + 1); }
        if (bytes.length > MAX_REQUEST_BYTES) throw new IllegalArgumentException("Request body exceeds 64 KiB.");
        Object parsed = Json.parse(new String(bytes, StandardCharsets.UTF_8));
        if (!(parsed instanceof Map<?, ?> map)) throw new IllegalArgumentException("Request body must be a JSON object.");
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : map.entrySet()) {
            if (!(entry.getKey() instanceof String key)) throw new IllegalArgumentException("JSON object keys must be strings.");
            result.put(key, entry.getValue());
        }
        return result;
    }

    private static String string(Map<String, Object> object, String key) {
        Object value = object.get(key);
        if (!(value instanceof String text) || text.isBlank()) throw new IllegalArgumentException("Field '" + key + "' must be a non-empty string.");
        return text.trim();
    }

    private static String optionalString(Map<String, Object> object, String key, String fallback) {
        Object value = object.get(key);
        if (value == null) return fallback;
        if (!(value instanceof String text) || text.isBlank()) throw new IllegalArgumentException("Field '" + key + "' must be a non-empty string.");
        return text.trim();
    }

    private static int integer(Map<String, Object> object, String key) { return integer(object, key, Integer.MIN_VALUE); }

    private static int integer(Map<String, Object> object, String key, int fallback) {
        Object value = object.get(key);
        if (value == null && fallback != Integer.MIN_VALUE) return fallback;
        if (!(value instanceof Number number) || number.doubleValue() != number.intValue())
            throw new IllegalArgumentException("Field '" + key + "' must be an integer.");
        return number.intValue();
    }

    private static double decimal(Map<String, Object> object, String key) {
        Object value = object.get(key);
        if (!(value instanceof Number number) || !Double.isFinite(number.doubleValue()))
            throw new IllegalArgumentException("Field '" + key + "' must be a finite number.");
        return number.doubleValue();
    }

    private static long queryLong(Map<String, String> query, String key) {
        try { return Long.parseLong(query.get(key)); }
        catch (RuntimeException exception) { throw new IllegalArgumentException("Query parameter '" + key + "' must be an integer."); }
    }

    private static Map<String, String> parseQuery(String rawQuery) {
        Map<String, String> query = new LinkedHashMap<>();
        if (rawQuery == null || rawQuery.isBlank()) return query;
        for (String part : rawQuery.split("&")) {
            String[] pair = part.split("=", 2);
            String key = URLDecoder.decode(pair[0], StandardCharsets.UTF_8);
            String value = pair.length == 2 ? URLDecoder.decode(pair[1], StandardCharsets.UTF_8) : "";
            if (query.putIfAbsent(key, value) != null) throw new IllegalArgumentException("Duplicate query parameter: " + key);
        }
        return query;
    }

    private static void sendJson(HttpExchange exchange, int status, Object value) throws IOException {
        sendText(exchange, status, "application/json; charset=utf-8", Json.stringify(value));
    }

    private static void sendText(HttpExchange exchange, int status, String contentType, String text) throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", contentType);
        exchange.getResponseHeaders().set("X-Content-Type-Options", "nosniff");
        exchange.getResponseHeaders().set("Cache-Control", "no-store");
        exchange.sendResponseHeaders(status, bytes.length);
        exchange.getResponseBody().write(bytes);
    }

    private static void sendHeadersOnly(HttpExchange exchange, int status, String contentType) throws IOException {
        exchange.getResponseHeaders().set("Content-Type", contentType);
        exchange.getResponseHeaders().set("X-Content-Type-Options", "nosniff");
        exchange.getResponseHeaders().set("Cache-Control", "no-store");
        exchange.sendResponseHeaders(status, -1);
    }

    private static String loadDashboard() throws IOException {
        Path[] candidates = {
                Path.of("src", "server", "web", "index.html"),
                Path.of("web", "index.html"),
                Path.of("index.html")
        };
        for (Path candidate : candidates)
            if (Files.isRegularFile(candidate)) return Files.readString(candidate, StandardCharsets.UTF_8);
        return null;
    }

    private static String safeMessage(Throwable exception) {
        String message = exception.getMessage();
        return message == null || message.isBlank() ? exception.getClass().getSimpleName() : message;
    }

    public static void main(String[] args) throws Exception {
        int port = args.length == 0 ? 8080 : Integer.parseInt(args[0]);
        ThreadSafeDispatchEngine engine = new ThreadSafeDispatchEngine();
        CADHttpServer server = new CADHttpServer(engine, port);
        SimulatedCallGenerator generator = new SimulatedCallGenerator(engine);
        server.start();
        generator.start();
        System.out.println("CAD HTTP server and call simulator listening at http://localhost:" + port);
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            generator.close();
            server.close();
        }, "cad-shutdown"));
        new CountDownLatch(1).await();
    }

    private static final class Json {
        private final String source;
        private int index;
        private Json(String source) { this.source = source; }

        private static Object parse(String source) {
            Json parser = new Json(source);
            Object value = parser.readValue();
            parser.skipWhitespace();
            if (parser.index != source.length()) parser.fail("Unexpected trailing content.");
            return value;
        }

        private static String stringify(Object value) {
            StringBuilder output = new StringBuilder();
            writeValue(output, value);
            return output.toString();
        }

        private static void writeValue(StringBuilder output, Object value) {
            if (value == null) output.append("null");
            else if (value instanceof String text) writeString(output, text);
            else if (value instanceof Boolean || value instanceof Integer || value instanceof Long) output.append(value);
            else if (value instanceof Number number) {
                double numeric = number.doubleValue();
                if (!Double.isFinite(numeric)) output.append("null");
                else output.append(number);
            } else if (value instanceof Map<?, ?> map) {
                output.append('{');
                boolean first = true;
                for (Map.Entry<?, ?> entry : map.entrySet()) {
                    if (!(entry.getKey() instanceof String key)) throw new IllegalArgumentException("JSON map keys must be strings.");
                    if (!first) output.append(',');
                    first = false;
                    writeString(output, key);
                    output.append(':');
                    writeValue(output, entry.getValue());
                }
                output.append('}');
            } else if (value instanceof Iterable<?> values) {
                output.append('[');
                boolean first = true;
                for (Object item : values) {
                    if (!first) output.append(',');
                    first = false;
                    writeValue(output, item);
                }
                output.append(']');
            } else throw new IllegalArgumentException("Unsupported JSON value: " + value.getClass().getName());
        }

        private static void writeString(StringBuilder output, String value) {
            output.append('"');
            for (int i = 0; i < value.length(); i++) {
                char character = value.charAt(i);
                switch (character) {
                    case '"' -> output.append("\\\"");
                    case '\\' -> output.append("\\\\");
                    case '\b' -> output.append("\\b");
                    case '\f' -> output.append("\\f");
                    case '\n' -> output.append("\\n");
                    case '\r' -> output.append("\\r");
                    case '\t' -> output.append("\\t");
                    default -> {
                        if (character < 0x20 || Character.isSurrogate(character)) {
                            output.append(String.format("\\u%04x", (int) character));
                        } else output.append(character);
                    }
                }
            }
            output.append('"');
        }

        private Object readValue() {
            skipWhitespace();
            if (index >= source.length()) return fail("Expected a JSON value.");
            return switch (source.charAt(index)) {
                case '{' -> readObject();
                case '[' -> readArray();
                case '"' -> readString();
                case 't' -> readLiteral("true", Boolean.TRUE);
                case 'f' -> readLiteral("false", Boolean.FALSE);
                case 'n' -> readLiteral("null", null);
                default -> readNumber();
            };
        }

        private Map<String, Object> readObject() {
            index++;
            skipWhitespace();
            Map<String, Object> result = new LinkedHashMap<>();
            if (consume('}')) return result;
            while (true) {
                skipWhitespace();
                if (index >= source.length() || source.charAt(index) != '"') return fail("Expected a quoted object key.");
                String key = readString();
                skipWhitespace();
                if (!consume(':')) return fail("Expected ':' after object key.");
                Object value = readValue();
                if (result.containsKey(key)) return fail("Duplicate JSON object key: " + key);
                result.put(key, value);
                skipWhitespace();
                if (consume('}')) return result;
                if (!consume(',')) return fail("Expected ',' or '}' in object.");
            }
        }

        private List<Object> readArray() {
            index++;
            skipWhitespace();
            List<Object> result = new ArrayList<>();
            if (consume(']')) return result;
            while (true) {
                result.add(readValue());
                skipWhitespace();
                if (consume(']')) return result;
                if (!consume(',')) return fail("Expected ',' or ']' in array.");
            }
        }

        private String readString() {
            index++;
            StringBuilder result = new StringBuilder();
            while (index < source.length()) {
                char character = source.charAt(index++);
                if (character == '"') return result.toString();
                if (character < 0x20) return fail("Unescaped control character in string.");
                if (character != '\\') { result.append(character); continue; }
                if (index >= source.length()) return fail("Incomplete string escape.");
                char escape = source.charAt(index++);
                switch (escape) {
                    case '"', '\\', '/' -> result.append(escape);
                    case 'b' -> result.append('\b');
                    case 'f' -> result.append('\f');
                    case 'n' -> result.append('\n');
                    case 'r' -> result.append('\r');
                    case 't' -> result.append('\t');
                    case 'u' -> result.append(readUnicodeEscape());
                    default -> { return fail("Invalid string escape."); }
                }
            }
            return fail("Unterminated string.");
        }

        private char readUnicodeEscape() {
            if (index + 4 > source.length()) return fail("Incomplete Unicode escape.");
            int value = 0;
            for (int i = 0; i < 4; i++) {
                int digit = Character.digit(source.charAt(index++), 16);
                if (digit < 0) return fail("Invalid Unicode escape.");
                value = (value << 4) | digit;
            }
            return (char) value;
        }

        private Object readNumber() {
            int start = index;
            if (consume('-') && index >= source.length()) return fail("Incomplete number.");
            if (consume('0')) {
                if (index < source.length() && Character.isDigit(source.charAt(index))) return fail("Leading zero in number.");
            } else {
                if (index >= source.length() || source.charAt(index) < '1' || source.charAt(index) > '9')
                    return fail("Invalid JSON value.");
                while (index < source.length() && Character.isDigit(source.charAt(index))) index++;
            }
            boolean decimal = false;
            if (consume('.')) {
                decimal = true;
                int digits = index;
                while (index < source.length() && Character.isDigit(source.charAt(index))) index++;
                if (digits == index) return fail("Fraction requires digits.");
            }
            if (index < source.length() && (source.charAt(index) == 'e' || source.charAt(index) == 'E')) {
                decimal = true;
                index++;
                if (index < source.length() && (source.charAt(index) == '+' || source.charAt(index) == '-')) index++;
                int digits = index;
                while (index < source.length() && Character.isDigit(source.charAt(index))) index++;
                if (digits == index) return fail("Exponent requires digits.");
            }
            String number = source.substring(start, index);
            try {
                if (!decimal) return Long.parseLong(number);
                double parsed = Double.parseDouble(number);
                if (!Double.isFinite(parsed)) return fail("Number is outside supported finite range.");
                return parsed;
            } catch (NumberFormatException exception) { return fail("Invalid or out-of-range number."); }
        }

        private Object readLiteral(String text, Object value) {
            if (!source.startsWith(text, index)) return fail("Invalid JSON literal.");
            index += text.length();
            return value;
        }

        private void skipWhitespace() {
            while (index < source.length()) {
                char character = source.charAt(index);
                if (character != ' ' && character != '\n' && character != '\r' && character != '\t') return;
                index++;
            }
        }

        private boolean consume(char expected) {
            if (index < source.length() && source.charAt(index) == expected) { index++; return true; }
            return false;
        }

        private <T> T fail(String message) { throw new IllegalArgumentException(message + " At JSON offset " + index + "."); }
    }
}