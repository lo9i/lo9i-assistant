import os

# Stop onnxruntime from sending usage data to Microsoft. Its telemetry thread can also crash the
# process at exit (SIGABRT in PosixTelemetry teardown). It has to be set before onnxruntime loads.
os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")
