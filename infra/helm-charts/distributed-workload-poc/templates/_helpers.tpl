{{/*
Common labels for all distributed-workload-poc resources.
*/}}
{{- define "distributed-workload-poc.labels" -}}
app.kubernetes.io/name: distributed-workload-poc
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}
