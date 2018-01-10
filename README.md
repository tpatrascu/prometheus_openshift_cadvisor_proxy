# Prometheus Openshift User Proxy

Use oauth-proxy to expose various metrics only for projects that the user has access to. It filters metrics by their "job" and  "namespace" labels.

Set PROMETHEUS_JOBS env var to a space separated list of prometheus jobs to expose to users.
