{{/*
Common labels for resources rendered directly by this (parent) chart —
the workloads ConfigMaps and the Ray shared-data PV/PVC. The mlflow and
prefect subcharts define their own label helpers.
*/}}
{{- define "distributed-workload-poc.labels" -}}
app.kubernetes.io/name: distributed-workload-poc
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}
