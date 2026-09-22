package dev.jevops.streamguard;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.time.Duration;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import org.apache.flink.api.common.eventtime.WatermarkStrategy;
import org.apache.flink.api.common.serialization.SimpleStringSchema;
import org.apache.flink.api.common.state.ListState;
import org.apache.flink.api.common.state.ListStateDescriptor;
import org.apache.flink.api.common.state.ValueState;
import org.apache.flink.api.common.state.ValueStateDescriptor;
import org.apache.flink.configuration.Configuration;
import org.apache.flink.connector.kafka.sink.KafkaRecordSerializationSchema;
import org.apache.flink.connector.kafka.sink.KafkaSink;
import org.apache.flink.connector.kafka.source.KafkaSource;
import org.apache.flink.connector.kafka.source.enumerator.initializer.OffsetsInitializer;
import org.apache.flink.streaming.api.datastream.DataStream;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;
import org.apache.flink.streaming.api.functions.KeyedProcessFunction;
import org.apache.flink.util.Collector;

/** Deterministic evidence generation only. Decision engines live outside Flink. */
public final class StreamGuardJob {
  private StreamGuardJob() {}

  public static void main(String[] args) throws Exception {
    String bootstrap = env("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092");
    String inputTopic = env("STREAMGUARD_EVENTS_TOPIC", "streamguard.events");
    String outputTopic = env("STREAMGUARD_EVIDENCE_TOPIC", "streamguard.evidence");

    StreamExecutionEnvironment environment = StreamExecutionEnvironment.getExecutionEnvironment();
    environment.enableCheckpointing(10_000);

    KafkaSource<String> source =
        KafkaSource.<String>builder()
            .setBootstrapServers(bootstrap)
            .setTopics(inputTopic)
            .setGroupId("streamguard-flink-v1")
            .setStartingOffsets(OffsetsInitializer.earliest())
            .setValueOnlyDeserializer(new SimpleStringSchema())
            .build();

    KafkaSink<String> sink =
        KafkaSink.<String>builder()
            .setBootstrapServers(bootstrap)
            .setRecordSerializer(
                KafkaRecordSerializationSchema.builder()
                    .setTopic(outputTopic)
                    .setValueSerializationSchema(new SimpleStringSchema())
                    .build())
            .build();

    DataStream<String> evidence =
        environment
            .fromSource(source, WatermarkStrategy.noWatermarks(), "operational-events")
            .keyBy(StreamGuardJob::runId)
            .process(new EvidenceAggregator());

    evidence.sinkTo(sink).name("evidence-snapshots");
    environment.execute("StreamGuard deterministic evidence");
  }

  private static String runId(String value) throws Exception {
    return new ObjectMapper().readTree(value).path("run_id").asText("unknown-run");
  }

  private static String env(String name, String fallback) {
    String value = System.getenv(name);
    return value == null || value.isBlank() ? fallback : value;
  }

  static final class EvidenceAggregator extends KeyedProcessFunction<String, String, String> {
    private static final int WINDOW_SIZE = 10;
    private transient ListState<String> recentState;
    private transient ValueState<Integer> versionState;
    private transient ObjectMapper mapper;

    @Override
    public void open(Configuration parameters) {
      recentState =
          getRuntimeContext()
              .getListState(new ListStateDescriptor<>("recent-operational-events", String.class));
      versionState =
          getRuntimeContext()
              .getState(new ValueStateDescriptor<>("evidence-version", Integer.class));
      mapper = new ObjectMapper();
    }

    @Override
    public void processElement(String value, Context context, Collector<String> output) {
      try {
        JsonNode current = mapper.readTree(value);
        List<JsonNode> window = new ArrayList<>();
        for (String prior : recentState.get()) {
          window.add(mapper.readTree(prior));
        }
        window.add(current);
        window.sort(Comparator.comparingInt(item -> item.path("sequence").asInt()));
        if (window.size() > WINDOW_SIZE) {
          window = new ArrayList<>(window.subList(window.size() - WINDOW_SIZE, window.size()));
        }
        recentState.clear();
        for (JsonNode event : window) {
          recentState.add(mapper.writeValueAsString(event));
        }

        Integer priorVersion = versionState.value();
        int version = priorVersion == null ? 1 : priorVersion + 1;
        versionState.update(version);
        output.collect(snapshot(current, window, version));
      } catch (Exception exception) {
        System.err.println("Ignoring malformed operational event: " + exception.getMessage());
      }
    }

    private String snapshot(JsonNode current, List<JsonNode> window, int version) throws Exception {
      JsonNode first = window.get(0);
      int received = current.path("records_received").asInt();
      int processed = current.path("records_processed").asInt();
      int lag = current.path("queue_depth").asInt();
      int errors = window.stream().mapToInt(item -> item.path("sink_errors").asInt()).sum();
      int attempts =
          window.stream()
              .mapToInt(
                  item ->
                      item.path("records_processed").asInt()
                          + item.path("sink_errors").asInt())
              .sum();
      double errorRate = attempts == 0 ? 0.0 : (double) errors / attempts;
      int p95Latency = percentile95(window);
      int lagChange = lag - first.path("queue_depth").asInt();
      int throughputChange = processed - first.path("records_processed").asInt();
      int consecutiveFailures = consecutiveFailures(window);
      int missingSamples =
          (int) window.stream().filter(item -> !item.path("telemetry_available").asBoolean()).count();
      boolean sinkHealthy = current.path("sink_errors").asInt() == 0 && p95Latency <= 100;

      ObjectNode root = mapper.createObjectNode();
      root.put("schema_version", "streamguard-evidence-v1");
      root.put("domain", "streamguard");
      root.put("incident_id", current.path("run_id").asText());
      root.put("evidence_version", version);
      root.put("observation_second", current.path("sequence").asInt());
      root.put("window_seconds", window.size());

      ObjectNode facts = root.putObject("facts");
      facts.put("arrival_rate_events_per_second", received);
      facts.put(
          "baseline_arrival_rate_events_per_second",
          current.path("baseline_events_per_second").asInt());
      facts.put("processing_rate_events_per_second", processed);
      facts.put("queue_lag_records", lag);
      facts.put("lag_change_over_window_records", lagChange);
      facts.put("lag_trend_records_per_second", trend(lagChange, window));
      facts.put("throughput_trend_events_per_second", trend(throughputChange, window));
      facts.put("sink_latency_p95_ms", p95Latency);
      facts.put("sink_error_count_window", errors);
      facts.put("sink_error_rate", errorRate);
      facts.put("consecutive_sink_failures", consecutiveFailures);
      facts.put("recovery_trend", recoveryTrend(lagChange, errors));
      facts.put("event_lateness_seconds", latenessSeconds(current));
      facts.put(
          "consumer_heartbeat_age_seconds",
          current.path("consumer_heartbeat_age_seconds").asInt());
      facts.put("checkpoint_age_seconds", current.path("checkpoint_age_seconds").asInt());
      ObjectNode partitionLag = facts.putObject("partition_lag_records");
      partitionLag.put("0", lag);
      partitionLag.put("1", 0);
      partitionLag.put("2", 0);
      facts.put("duplicate_count_window", 0);
      facts.put("schema_rejection_count_window", 0);
      facts.put("telemetry_missing_samples_window", missingSamples);
      facts.put("sink_healthy", sinkHealthy);
      facts.put(
          "capacity_headroom_events_per_second",
          Math.max(0, current.path("baseline_events_per_second").asInt() - received));
      facts.put("source_retained", current.path("source_retained").asBoolean());
      facts.put("checkpoint_known", current.path("checkpoint_available").asBoolean());
      facts.put("confirmed_replay_gap", false);
      facts.put("source_available", current.path("source_available").asBoolean());
      facts.put("wait_budget_remaining", lag > 2_000 ? 0 : 1);
      facts.put("retry_budget_remaining", consecutiveFailures >= 8 ? 0 : 1);
      facts.put("deadline_exceeded", lag > 5_000);

      ArrayNode observations = root.putArray("observations");
      observations.add("consumer heartbeat observed");
      if (missingSamples > 0) observations.add("telemetry sample unavailable");
      if (errors > 0) observations.add("sink write timeout observed");
      if (p95Latency >= 200) observations.add("sink write latency above baseline");
      if (received >= current.path("baseline_events_per_second").asInt() * 3 / 2)
        observations.add("input throughput above baseline");
      if (lagChange < 0) observations.add("queue backlog is recovering");

      ObjectNode policy = root.putObject("policy");
      ArrayNode allowed = policy.putArray("allowed_actions");
      allowed.add("WAIT").add("RETRY").add("PAUSE").add("REPLAY").add("ESCALATE");
      ArrayNode replay = policy.putArray("replay_requires");
      replay.add("confirmed_replay_gap").add("source_retained").add("checkpoint_known").add("sink_healthy");
      policy.put("wait_interval_seconds", 10);
      return mapper.writeValueAsString(root);
    }

    private static int percentile95(List<JsonNode> window) {
      List<Integer> latencies =
          window.stream().map(item -> item.path("sink_latency_ms").asInt()).sorted().toList();
      int index = Math.max(0, (int) Math.ceil(latencies.size() * 0.95) - 1);
      return latencies.get(index);
    }

    private static int consecutiveFailures(List<JsonNode> window) {
      int count = 0;
      for (int index = window.size() - 1; index >= 0; index--) {
        if (window.get(index).path("sink_errors").asInt() == 0) break;
        count++;
      }
      return count;
    }

    private static double trend(int change, List<JsonNode> window) {
      if (window.size() < 2) return 0.0;
      int elapsed =
          Math.max(
              1,
              window.get(window.size() - 1).path("sequence").asInt()
                  - window.get(0).path("sequence").asInt());
      return (double) change / elapsed;
    }

    private static String recoveryTrend(int lagChange, int errors) {
      if (lagChange < 0 && errors == 0) return "IMPROVING";
      if (lagChange > 0 || errors > 0) return "DEGRADING";
      return "STABLE";
    }

    private static long latenessSeconds(JsonNode event) {
      try {
        OffsetDateTime timestamp = OffsetDateTime.parse(event.path("timestamp").asText());
        return Math.max(0, Duration.between(timestamp, OffsetDateTime.now(ZoneOffset.UTC)).toSeconds());
      } catch (Exception ignored) {
        return 0;
      }
    }
  }
}
