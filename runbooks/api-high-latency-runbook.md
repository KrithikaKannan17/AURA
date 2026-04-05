# API High Latency & Error Rate Runbook

**Version:** 1.4  
**Owner:** Backend Engineering  
**Last Updated:** 2024-03-10  
**Severity:** P2 / P3

---

## Overview

This runbook covers diagnosis and resolution of elevated API response times, increased HTTP 5xx error rates, and downstream service degradation affecting user-facing APIs.

---

## Section 1: Identifying the Problem

### 1.1 Key Metrics to Check

| Metric | Normal | Warning | Critical |
|--------|--------|---------|----------|
| p99 latency | < 200ms | 200–500ms | > 500ms |
| Error rate (5xx) | < 0.1% | 0.1–1% | > 1% |
| Request queue depth | < 100 | 100–500 | > 500 |
| CPU utilization | < 70% | 70–85% | > 85% |

### 1.2 Monitoring Dashboards

- **Datadog APM:** `https://app.datadoghq.com/apm/services/api-service`
- **Grafana:** Dashboard `API Performance Overview`
- **CloudWatch:** Namespace `AURA/API` — metrics `Latency`, `5xxError`

### 1.3 Quick Health Check

```bash
# Check API server process
systemctl status api-service

# Test endpoint directly
curl -w "\n%{time_total}s\n" -o /dev/null -s https://api.example.com/health

# Check active connections
ss -tuln | grep :8000
netstat -an | grep :8000 | wc -l
```

---

## Section 2: Root Cause Analysis

### 2.1 Database Slow Queries

**Symptoms:** API latency high but CPU/memory normal; DB query time elevated.

**Diagnosis:**
```bash
# Check slow query log
tail -f /var/log/mysql/slow-query.log

# PostgreSQL: active slow queries
psql -U admin -c "
  SELECT pid, now() - query_start AS duration, query
  FROM pg_stat_activity
  WHERE state = 'active'
    AND now() - query_start > interval '2 seconds'
  ORDER BY duration DESC;"

# Check for missing indexes
psql -U admin -c "
  SELECT schemaname, tablename, attname, n_distinct, correlation
  FROM pg_stats
  WHERE tablename = 'orders'
  ORDER BY n_distinct;"
```

**Remediation:**
1. Add a temporary index for the slow query (no downtime):
   ```sql
   CREATE INDEX CONCURRENTLY idx_orders_user_id ON orders(user_id);
   ```
2. Kill blocking queries:
   ```sql
   SELECT pg_cancel_backend(<pid>);
   ```
3. Scale read replicas if read load is the issue.

### 2.2 Memory Pressure / GC Pauses (JVM/Node.js)

**Symptoms:** Latency spikes correlated with GC activity; heap usage near max.

**Diagnosis:**

For Node.js:
```bash
# Check heap usage
kubectl exec -it <pod-name> -n production -- node -e "
  const v8 = require('v8');
  console.log(v8.getHeapStatistics());"

# Enable GC logging
NODE_OPTIONS="--expose-gc --trace-gc" node server.js
```

For JVM:
```bash
# Check GC logs
grep "GC pause" /var/log/app/gc.log | tail -20

# Heap dump (safe, read-only analysis)
jcmd <pid> GC.heap_info
```

**Remediation:**
1. Increase heap size:
   ```bash
   # Node.js
   kubectl set env deployment/api-service NODE_OPTIONS="--max-old-space-size=2048"
   # JVM
   kubectl set env deployment/api-service JAVA_OPTS="-Xmx4g -Xms2g"
   ```
2. Trigger garbage collection (Node.js, if GC exposed):
   ```bash
   # Safe — only exposes existing GC, does not force
   kubectl exec <pod> -- node -e "global.gc && global.gc()"
   ```

### 2.3 Downstream Service Dependency Timeout

**Symptoms:** Specific endpoints slow; upstream service calls timing out.

**Diagnosis:**
```bash
# Check service mesh / proxy stats (Istio)
istioctl proxy-config cluster <pod-name> -n production | grep <service-name>

# Check circuit breaker state (if using Hystrix/Resilience4j)
curl http://localhost:8080/actuator/circuitbreakers

# Trace a slow request
curl -H "X-Request-ID: debug-$(date +%s)" https://api.example.com/endpoint
grep "debug-" /var/log/app/traces.log
```

**Remediation:**
1. Enable circuit breaker for the flaky service:
   ```yaml
   circuitBreaker:
     slidingWindowSize: 10
     failureRateThreshold: 50
     waitDurationInOpenState: 30s
   ```
2. Temporarily bypass degraded downstream service (feature flag):
   ```bash
   curl -X POST https://api.example.com/admin/flags \
     -d '{"flag": "enable_payment_service", "value": false}'
   ```
3. Scale up downstream service:
   ```bash
   kubectl scale deployment payment-service -n production --replicas=10
   ```

### 2.4 Thread Pool / Worker Exhaustion

**Symptoms:** Requests queuing; worker thread count maxed out; connection timeout errors.

**Diagnosis:**
```bash
# Check thread count
ps -eLf | grep api-service | wc -l

# Nginx worker connections
nginx -T | grep worker_connections
cat /proc/<nginx-pid>/status | grep Threads
```

**Remediation:**
1. Scale horizontally immediately:
   ```bash
   kubectl scale deployment api-service -n production --replicas=20
   ```
2. Increase worker pool size (requires redeploy):
   ```bash
   kubectl set env deployment/api-service WORKER_THREADS=32
   ```
3. Shed load via rate limiting if queue is unbounded:
   ```bash
   # Nginx rate limit
   kubectl apply -f rate-limit-configmap.yaml
   kubectl rollout restart deployment/nginx-ingress -n ingress-nginx
   ```

### 2.5 Elevated 5xx Errors from Uncaught Exceptions

**Symptoms:** Error rate spike; logs show unhandled exceptions or panics.

**Diagnosis:**
```bash
# Aggregate error types from logs
kubectl logs deployment/api-service -n production --since=30m | \
  grep -E "ERROR|PANIC|FATAL" | \
  awk '{print $NF}' | sort | uniq -c | sort -rn | head -20

# Check Sentry / error tracking
# Navigate to: https://sentry.io/organizations/your-org/issues/
```

**Remediation:**
1. If deployment caused the spike, roll back:
   ```bash
   kubectl rollout undo deployment/api-service -n production
   kubectl rollout status deployment/api-service -n production
   ```
2. If 3rd-party API rate-limited, add exponential backoff and retry.

---

## Section 3: Traffic Management

### 3.1 Enable Maintenance Mode

```bash
# Set upstream to maintenance page (Nginx)
kubectl set configmap nginx-config maintenance_mode="true" -n production
kubectl rollout restart deployment/nginx -n production
```

### 3.2 Traffic Shifting (Canary)

```bash
# Shift 10% traffic to new version for validation
kubectl apply -f - <<EOF
apiVersion: networking.istio.io/v1alpha3
kind: VirtualService
spec:
  http:
  - route:
    - destination:
        host: api-service
        subset: stable
      weight: 90
    - destination:
        host: api-service
        subset: canary
      weight: 10
EOF
```

---

## Section 4: Escalation Criteria

Escalate to Backend Engineering on-call if:
- p99 latency > 2 seconds sustained for > 5 minutes
- Error rate > 5% for > 2 minutes
- Rollback does not resolve the issue
- Revenue-impacting endpoints (checkout, payment) affected

**Escalation channel:** `#backend-oncall`  
**PagerDuty policy:** `api-critical`

---

## Section 5: Post-Incident

1. Export APM traces from the incident window for analysis
2. Review and tighten SLO thresholds if alert was too slow
3. Add relevant metrics to dashboard
4. Update this runbook with new findings
