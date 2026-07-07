import multiprocessing
import os

# ============================================
# Server
# ============================================

bind = "0.0.0.0:8000"

# ============================================
# Workers
# ============================================

workers = (multiprocessing.cpu_count() * 2) + 1

worker_class = "gthread"

threads = 2

# ============================================
# Performance
# ============================================

timeout = 120

graceful_timeout = 30

keepalive = 5

worker_connections = 1000

# ============================================
# Memory Management
# ============================================

max_requests = 1000

max_requests_jitter = 100

preload_app = True

# ============================================
# Logging
# ============================================

accesslog = "-"

errorlog = "-"

loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")

capture_output = True

access_log_format = (
    '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s '
    '"%(f)s" "%(a)s" %(D)s'
)

# ============================================
# Security
# ============================================

limit_request_line = 4094

limit_request_fields = 100

limit_request_field_size = 8190