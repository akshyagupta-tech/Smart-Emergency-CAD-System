# Stage 1: Build Java Bytecode
FROM eclipse-temurin:17-jdk-alpine AS builder
WORKDIR /app
COPY src/ ./src/
RUN mkdir -p bin && javac -d bin $(find src -name "*.java")

# Stage 2: Minimal Production JRE Runtime (< 120MB)
FROM eclipse-temurin:17-jre-alpine
WORKDIR /app
COPY --from=builder /app/bin ./bin
COPY src/server/web/ ./src/server/web/

ENV PORT=8080
EXPOSE 8080

CMD ["java", "-cp", "bin", "ServerMain"]
