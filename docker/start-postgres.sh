#!/bin/sh
set -e

# Debian's postgresql package auto-creates a default cluster at build time
# (data in /var/lib/postgresql/<ver>/main, config in /etc/postgresql/<ver>/main).
PG_VERSION=$(ls /etc/postgresql/ | sort -n | tail -1)
PG_BIN="/usr/lib/postgresql/$PG_VERSION/bin"
PGDATA="/var/lib/postgresql/$PG_VERSION/main"
PGCONF="/etc/postgresql/$PG_VERSION/main/postgresql.conf"
LOGDIR="/var/log/postgresql"
LOGFILE="$LOGDIR/postgres-bootstrap.log"

mkdir -p "$LOGDIR"
chown postgres:postgres "$LOGDIR"
chown -R postgres:postgres /var/lib/postgresql

if [ ! -s "$PGDATA/PG_VERSION" ]; then
  echo "Initializing new PostgreSQL data directory at $PGDATA"
  su postgres -c "$PG_BIN/initdb -D $PGDATA --auth-local=peer --auth-host=scram-sha-256"
fi

# Start temporarily to run bootstrap SQL (create role password + app database),
# then hand off to the real foreground process for supervisord to supervise.
su postgres -c "$PG_BIN/pg_ctl -D $PGDATA -o \"-c config_file=$PGCONF -c listen_addresses=*\" -l $LOGFILE -w start"

su postgres -c "psql -c \"ALTER USER postgres WITH PASSWORD 'postgres';\"" >/dev/null
su postgres -c "psql -tc \"SELECT 1 FROM pg_database WHERE datname = 'knowledge_db'\"" | grep -q 1 \
  || su postgres -c "createdb knowledge_db"

su postgres -c "$PG_BIN/pg_ctl -D $PGDATA -w stop"

exec su postgres -c "$PG_BIN/postgres -D $PGDATA -c config_file=$PGCONF -c listen_addresses='*' -c port=5432"
