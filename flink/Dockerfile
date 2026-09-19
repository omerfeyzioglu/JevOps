FROM maven:3.9.9-eclipse-temurin-17 AS build
WORKDIR /build
COPY pom.xml .
COPY src src
RUN mvn -B -DskipTests package

FROM flink:1.20.2-scala_2.12-java17
COPY --from=build /build/target/streamguard-flink-0.1.0.jar /opt/flink/usrlib/streamguard-flink.jar
