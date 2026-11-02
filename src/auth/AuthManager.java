package auth;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/** In-memory demo authentication with opaque UUID bearer tokens and a fixed two-hour TTL. */
public final class AuthManager {
    public static final long SESSION_TTL_MILLIS = 2L * 60 * 60 * 1000;

    private record Account(String password, UserRole role) { }

    public static final class AuthToken {
        private final String token;
        private final UserRole role;
        private final long expiresAtEpochMillis;

        private AuthToken(String token, UserRole role, long expiresAtEpochMillis) {
            this.token = token;
            this.role = role;
            this.expiresAtEpochMillis = expiresAtEpochMillis;
        }

        public String getToken() { return token; }
        public UserRole getRole() { return role; }
        public long getExpiresAtEpochMillis() { return expiresAtEpochMillis; }
    }

    public static final class UserSession {
        private final String username;
        private final UserRole role;
        private final long expiresAtEpochMillis;

        private UserSession(String username, UserRole role, long expiresAtEpochMillis) {
            this.username = username;
            this.role = role;
            this.expiresAtEpochMillis = expiresAtEpochMillis;
        }

        public String getUsername() { return username; }
        public UserRole getRole() { return role; }
        public long getExpiresAtEpochMillis() { return expiresAtEpochMillis; }
    }

    private final Map<String, Account> accounts = Map.of(
            "dispatcher", new Account("dispatch123", UserRole.DISPATCHER),
            "doctor", new Account("trauma123", UserRole.DOCTOR),
            "director", new Account("admin123", UserRole.MEDICAL_DIRECTOR),
            "paramedic", new Account("crew123", UserRole.PARAMEDIC));
    private final ConcurrentHashMap<String, UserSession> sessions = new ConcurrentHashMap<>();

    /** Returns an opaque token on valid credentials, otherwise null. */
    public AuthToken login(String username, String password) {
        if (username == null || password == null) return null;
        Account account = accounts.get(username.trim());
        byte[] supplied = password.getBytes(StandardCharsets.UTF_8);
        byte[] expected = account == null ? new byte[0] : account.password.getBytes(StandardCharsets.UTF_8);
        if (account == null || !MessageDigest.isEqual(supplied, expected)) return null;

        long expiresAt = System.currentTimeMillis() + SESSION_TTL_MILLIS;
        String token = UUID.randomUUID().toString();
        sessions.put(token, new UserSession(username.trim(), account.role, expiresAt));
        purgeExpiredSessions();
        return new AuthToken(token, account.role, expiresAt);
    }

    /** Returns null for unknown, malformed, or expired tokens. */
    public UserSession validateToken(String token) {
        if (token == null || token.isBlank()) return null;
        UserSession session = sessions.get(token);
        if (session == null) return null;
        if (System.currentTimeMillis() >= session.expiresAtEpochMillis) {
            sessions.remove(token, session);
            return null;
        }
        return session;
    }

    public boolean hasPermission(String token, UserRole requiredRole) {
        if (requiredRole == null) return false;
        UserSession session = validateToken(token);
        return session != null && session.role == requiredRole;
    }

    public boolean logout(String token) {
        return token != null && sessions.remove(token) != null;
    }

    private void purgeExpiredSessions() {
        long now = System.currentTimeMillis();
        sessions.entrySet().removeIf(entry -> now >= entry.getValue().expiresAtEpochMillis);
    }
}