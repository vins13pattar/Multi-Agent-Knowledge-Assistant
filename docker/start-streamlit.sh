#!/bin/sh
set -e

echo "Waiting for API..."
i=0
until curl -sf "http://127.0.0.1:8000/api/v1/health/live" >/dev/null 2>&1; do
  i=$((i + 1))
  if [ "$i" -ge 60 ]; then
    echo "API did not become ready in time, starting Streamlit anyway."
    break
  fi
  sleep 1
done

exec streamlit run apps/streamlit/app.py --server.port=8501 --server.address=0.0.0.0
