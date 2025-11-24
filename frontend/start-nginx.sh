#!/bin/sh
# Replace BACKEND_URL placeholder in nginx config
# Default to http://localhost:8000 if not set
BACKEND_URL=${BACKEND_URL:-http://localhost:8000}

# Use sed to replace the ${BACKEND_URL} placeholder
sed -i "s|\${BACKEND_URL}|$BACKEND_URL|g" /etc/nginx/conf.d/default.conf

# Start nginx
exec nginx -g 'daemon off;'

