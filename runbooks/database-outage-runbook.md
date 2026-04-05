# Database Outage Runbook

**Version:** 2.1  
**Owner:** Platform Engineering  
**Last Updated:** 2024-01-15  
**Severity:** P1 / P2

---

## Overview

This runbook covers diagnosis and remediation steps for PostgreSQL and MySQL database outages, connection pool exhaustion, replication lag, and disk space issues.

---

## Section 1: Identifying the Issue

### 1.1 Symptoms
- Application returning 500 errors with "connection refused" or "timeout" messages
- Monitoring alerts: `db_connections_available < 10%`
- Slow query logs showing queries exceeding 30 seconds
- Replication lag > 60 seconds on read replicas

### 1.2 Initial Health Check

Run the following commands to assess database health:

```bash
# Check if database process is running
systemctl status postgresql
# OR for containerized environments:
kubectl get pods -n database -l app=postgres

# Check connection count
psql -U admin -c "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';"

# Check for long-running queries
psql -U admin -c "SELECT pid, now() - pg_stat_activity.query_start AS duration, query, state FROM pg_stat_activity WHERE state != 'idle' AND (now() - pg_stat_activity.query_start) > interval '5 minutes';"

# Check disk usage
df -h /var/lib/postgresql/data
```

### 1.3 Connection Pool Status
```bash
# PgBouncer stats (if used)
psql -U pgbouncer -p 6432 pgbouncer -c "SHOW STATS;"
psql -U pgbouncer -p 6432 pgbouncer -c "SHOW POOLS;"
```

---

## Section 2: Common Root Causes

### 2.1 Connection Pool Exhaustion
**Cause:** Too many idle or long-running connections consuming the pool.  
**Confidence Indicators:** `pg_stat_activity` shows > 90% connections in use; application logs show "too many clients."

**Remediation:**
1. Identify and terminate idle connections:
   ```sql
   SELECT pg_terminate_backend(pid)
   FROM pg_stat_activity
   WHERE state = 'idle'
   AND query_start < NOW() - INTERVAL '10 minutes';
   ```
2. Increase `max_connections` in `postgresql.conf` (requires restart):
   ```
   max_connections = 200
   ```
3. Configure PgBouncer pool size:
   ```ini
   [pgbouncer]
   pool_mode = transaction
   max_client_conn = 500
   default_pool_size = 25
   ```
4. Restart PgBouncer (no downtime):
   ```bash
   systemctl reload pgbouncer
   ```

### 2.2 Database Process Crashed
**Cause:** OOM kill, storage corruption, or kernel panic.

**Remediation:**
1. Check system logs:
   ```bash
   journalctl -u postgresql --since "1 hour ago"
   dmesg | grep -i "oom\|killed"
   ```
2. Attempt restart:
   ```bash
   systemctl restart postgresql
   ```
3. If data corruption suspected, check PostgreSQL logs:
   ```bash
   tail -n 200 /var/log/postgresql/postgresql-*.log
   ```
4. Run consistency check (read-only, safe):
   ```bash
   pg_dump -U admin --schema-only mydb > /dev/null && echo "Schema OK"
   ```

### 2.3 Disk Space Full
**Cause:** WAL logs, table bloat, or log files consuming all disk space.

**Remediation:**
1. Identify large files:
   ```bash
   du -sh /var/lib/postgresql/data/pg_wal/
   find /var/lib/postgresql -name "*.log" -size +100M
   ```
2. Archive or delete old WAL segments (CAUTION — only after verifying replication is healthy):
   ```bash
   # Check replication status first
   psql -U admin -c "SELECT * FROM pg_stat_replication;"
   # Manually archive old WAL (safe)
   pg_archivecleanup /var/lib/postgresql/data/pg_wal/ $(ls -t /var/lib/postgresql/data/pg_wal/ | head -1)
   ```
3. Run VACUUM to reclaim bloat:
   ```sql
   VACUUM ANALYZE;
   ```

### 2.4 Replication Lag
**Cause:** Heavy write load, network issues, or replica falling behind.

**Remediation:**
1. Check replication lag:
   ```sql
   SELECT client_addr, state, sent_lsn, write_lsn, flush_lsn, replay_lsn,
          (sent_lsn - replay_lsn) AS replication_lag
   FROM pg_stat_replication;
   ```
2. Redirect read traffic away from lagging replica:
   ```bash
   # Update load balancer health check threshold
   kubectl annotate service db-replica "health-check-lag-threshold=120s"
   ```
3. If lag > 10 minutes, consider replica rebuild.

---

## Section 3: Escalation Criteria

Escalate to Database Engineering on-call if:
- Database cannot be restarted after 2 attempts
- Data loss is suspected
- Replication lag > 30 minutes
- Disk usage > 95% and cannot be freed

**On-call contact:** `#db-oncall` Slack channel or PagerDuty policy `database-critical`

---

## Section 4: Post-Incident

1. Capture `pg_stat_statements` snapshot for performance analysis
2. Update capacity planning if connection exhaustion was the cause
3. File incident report within 24 hours
4. Schedule postmortem within 48 hours for P1 incidents
