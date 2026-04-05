# Kubernetes Pod CrashLoopBackOff Runbook

**Version:** 3.0  
**Owner:** Infrastructure Team  
**Last Updated:** 2024-02-01  
**Severity:** P1 / P2 / P3

---

## Overview

This runbook covers diagnosis and resolution of Kubernetes pods stuck in `CrashLoopBackOff`, `OOMKilled`, `Error`, or `Pending` states. Applicable to EKS, GKE, and self-managed clusters.

---

## Section 1: Rapid Assessment

### 1.1 Identify Affected Pods

```bash
# List all non-running pods across all namespaces
kubectl get pods --all-namespaces --field-selector=status.phase!=Running

# Focus on a specific namespace
kubectl get pods -n production -o wide

# Check restart counts (high restarts = CrashLoop indicator)
kubectl get pods -n production --sort-by='.status.containerStatuses[0].restartCount'
```

### 1.2 Get Pod Details

```bash
# Describe pod for events and status
kubectl describe pod <pod-name> -n <namespace>

# Get logs from crashing container
kubectl logs <pod-name> -n <namespace> --previous

# Get logs with timestamps
kubectl logs <pod-name> -n <namespace> --previous --timestamps=true | tail -100
```

### 1.3 Check Events

```bash
# Cluster-wide events sorted by time
kubectl get events --all-namespaces --sort-by='.lastTimestamp' | tail -30

# Namespace-specific events
kubectl get events -n production --sort-by='.lastTimestamp'
```

---

## Section 2: Root Cause Analysis

### 2.1 OOMKilled (Out of Memory)

**Symptoms:** Pod exits with `OOMKilled` reason; memory usage hitting limits.

**Diagnosis:**
```bash
# Check memory limits and usage
kubectl top pods -n production
kubectl describe pod <pod-name> -n production | grep -A 5 "Limits\|Requests"

# Check node memory pressure
kubectl describe nodes | grep -A 5 "MemoryPressure"
```

**Remediation:**
1. Temporarily increase memory limit in the deployment:
   ```bash
   kubectl set resources deployment/<name> -n production --limits=memory=2Gi
   ```
2. Check for memory leaks in application logs:
   ```bash
   kubectl logs <pod-name> -n production --previous | grep -i "memory\|heap\|gc"
   ```
3. If leak confirmed, roll back to previous version:
   ```bash
   kubectl rollout undo deployment/<name> -n production
   kubectl rollout status deployment/<name> -n production
   ```

### 2.2 Application Startup Failure

**Symptoms:** Pod starts then crashes immediately; exit code 1 or 2.

**Diagnosis:**
```bash
# Check init containers
kubectl describe pod <pod-name> -n production | grep -A 20 "Init Containers"

# Check environment variables and secrets
kubectl get pod <pod-name> -n production -o jsonpath='{.spec.containers[0].env}'

# Verify secrets exist
kubectl get secrets -n production
```

**Remediation:**
1. Check for missing environment variables or secrets:
   ```bash
   kubectl get secret <secret-name> -n production -o jsonpath='{.data}' | base64 --decode
   ```
2. Recreate missing secret:
   ```bash
   kubectl create secret generic <secret-name> \
     --from-literal=key=value \
     -n production
   ```
3. Verify ConfigMap is correct:
   ```bash
   kubectl get configmap <name> -n production -o yaml
   ```

### 2.3 Image Pull Failure (ImagePullBackOff)

**Symptoms:** Pod stuck in `ImagePullBackOff` or `ErrImagePull`.

**Diagnosis:**
```bash
kubectl describe pod <pod-name> -n production | grep -A 10 "Events"
```

**Remediation:**
1. Verify image exists in registry:
   ```bash
   docker pull <image>:<tag>
   ```
2. Check image pull secret:
   ```bash
   kubectl get secret regcred -n production
   kubectl patch serviceaccount default -n production \
     -p '{"imagePullSecrets": [{"name": "regcred"}]}'
   ```
3. If image tag is wrong, update deployment:
   ```bash
   kubectl set image deployment/<name> <container>=<image>:<correct-tag> -n production
   ```

### 2.4 Liveness/Readiness Probe Failure

**Symptoms:** Pod keeps restarting due to failed health checks.

**Diagnosis:**
```bash
kubectl describe pod <pod-name> -n production | grep -A 10 "Liveness\|Readiness"
```

**Remediation:**
1. Temporarily disable probes to allow pod to stabilize (diagnostic only):
   ```bash
   kubectl patch deployment <name> -n production --type=json \
     -p='[{"op": "remove", "path": "/spec/template/spec/containers/0/livenessProbe"}]'
   ```
2. Adjust probe timing:
   ```yaml
   livenessProbe:
     initialDelaySeconds: 60
     periodSeconds: 30
     failureThreshold: 5
   ```

### 2.5 Node Resource Pressure

**Symptoms:** Pods evicted or not scheduled; node shows `DiskPressure` or `MemoryPressure`.

**Diagnosis:**
```bash
kubectl describe nodes | grep -E "Taints|Conditions|Allocated"
kubectl top nodes
```

**Remediation:**
1. Cordon pressured node:
   ```bash
   kubectl cordon <node-name>
   ```
2. Drain workloads safely:
   ```bash
   kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data
   ```
3. Clean disk on node:
   ```bash
   # SSH to node
   docker system prune -f
   journalctl --vacuum-size=500M
   ```

---

## Section 3: Rollback Procedures

```bash
# View deployment history
kubectl rollout history deployment/<name> -n production

# Rollback to previous version
kubectl rollout undo deployment/<name> -n production

# Rollback to specific revision
kubectl rollout undo deployment/<name> -n production --to-revision=3

# Monitor rollback
kubectl rollout status deployment/<name> -n production --watch
```

---

## Section 4: Escalation Criteria

Escalate to Infrastructure on-call if:
- More than 50% of pods in a critical namespace are failing
- Node failures affecting cluster quorum
- Persistent Volume data loss suspected
- Rollback fails or makes situation worse

**Escalation channel:** `#infra-oncall` on Slack  
**PagerDuty policy:** `k8s-critical`

---

## Section 5: Prevention

1. Set appropriate resource requests/limits on all deployments
2. Use `PodDisruptionBudgets` for critical services
3. Configure `HorizontalPodAutoscaler` for traffic spikes
4. Implement proper liveness/readiness probes with generous initial delays
