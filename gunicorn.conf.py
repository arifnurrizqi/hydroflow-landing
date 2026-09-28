# Deliberately process one request at a time on the 2 GB ARM host.
# In particular, do not decode multiple uploaded images concurrently.
bind = '0.0.0.0:8000'
workers = 1
worker_class = 'sync'
threads = 1
timeout = 90
graceful_timeout = 20
max_requests = 200
max_requests_jitter = 20
worker_tmp_dir = '/tmp'
accesslog = '-'
errorlog = '-'
limit_request_line = 4094
