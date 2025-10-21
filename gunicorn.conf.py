# Gunicorn configuration for production deployment

import os
import multiprocessing

# Server socket
bind = "0.0.0.0:5001"
backlog = 2048

# Worker processes
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50
preload_app = True
timeout = 120  # Increased from 30 to handle batch operations
keepalive = 2

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "braindumpster-api"

# Server mechanics
daemon = False
pidfile = "/tmp/braindumpster.pid"
user = None
group = None
tmp_upload_dir = None

# SSL (for HTTPS in production)
# keyfile = "/path/to/ssl/private.key"
# certfile = "/path/to/ssl/certificate.crt"

# Security
limit_request_line = 4096
limit_request_fields = 100
limit_request_field_size = 8190

def when_ready(server):
    server.log.info("🚀 Braindumpster API server is ready!")

def worker_int(worker):
    worker.log.info("⚠️  Worker received INT or QUIT signal")

def pre_fork(server, worker):
    server.log.info("🔄 Worker spawned (pid: %s)", worker.pid)

def post_fork(server, worker):
    server.log.info("✅ Worker spawned (pid: %s)", worker.pid)

def worker_abort(worker):
    worker.log.info("❌ Worker received SIGABRT signal")