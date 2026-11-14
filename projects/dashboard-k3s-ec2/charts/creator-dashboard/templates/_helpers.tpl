{{- define "cd.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "cd.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- include "cd.name" . -}}
{{- end -}}
{{- end -}}

{{- define "cd.labels" -}}
app.kubernetes.io/name: {{ include "cd.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{- define "cd.selectorLabels" -}}
app.kubernetes.io/name: {{ include "cd.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/* Shared container hardening. */}}
{{- define "cd.containerSecurity" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
runAsNonRoot: true
capabilities:
  drop: ["ALL"]
{{- end -}}

{{- define "cd.syncEnv" -}}
- name: BUCKET
  value: {{ required "sync.bucket is required (terraform output -raw bucket_name)" .Values.sync.bucket | quote }}
- name: PREFIX
  value: {{ .Values.sync.prefix | quote }}
- name: AWS_REGION
  value: {{ .Values.sync.region | quote }}
- name: INTERVAL
  value: {{ .Values.sync.intervalSeconds | quote }}
- name: SITE_ROOT
  value: /srv
- name: HOME
  value: /tmp
- name: AWS_PAGER
  value: ""
{{- end -}}
