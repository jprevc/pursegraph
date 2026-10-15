#!/bin/sh
# The backup sidecar: a nightly pg_dump of the database into /backups, keeping the newest
# 14 daily and 6 monthly dumps. Runs in the postgres image, so pg_dump matches the server.
#
#   /backups/daily/pursegraph-YYYY-MM-DD.dump    one per night
#   /backups/monthly/pursegraph-YYYY-MM.dump     the month's first daily dump (a hard link)
#
# Dumps are in pg_dump's custom format; the README describes restoring one.
# `backup.sh once` takes one dump now and exits.
set -eu

BACKUP_DIR=${BACKUP_DIR:-/backups}
# The hour (in TZ) of the nightly dump.
BACKUP_HOUR=${BACKUP_HOUR:-3}
KEEP_DAILY=14
KEEP_MONTHLY=6

# The dumps hold every Member's finances: readable by their owner only.
umask 077
if ! mkdir -p "$BACKUP_DIR/daily" "$BACKUP_DIR/monthly"; then
    echo "Can't write to $BACKUP_DIR: create the host directory, owned by PURSEGRAPH_BACKUP_USER ($(id -u):$(id -g))." >&2
    exit 1
fi

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $*"
}

# Keeps the newest $2 dumps in directory $1; the names sort by date.
prune() {
    ls -1 "$1" | grep '^pursegraph-.*\.dump$' | sort -r | tail -n "+$(($2 + 1))" | while read -r old; do
        rm -f "$1/$old"
        log "Removed $1/$old"
    done
}

dump() {
    daily="$BACKUP_DIR/daily/pursegraph-$(date +%Y-%m-%d).dump"
    monthly="$BACKUP_DIR/monthly/pursegraph-$(date +%Y-%m).dump"
    # Written under a temporary name, so a failed dump never replaces a good one.
    if ! pg_dump --format=custom --file="$daily.partial"; then
        rm -f "$daily.partial"
        log "Backup FAILED"
        return 1
    fi
    mv "$daily.partial" "$daily"
    [ -e "$monthly" ] || ln "$daily" "$monthly"
    log "Backed up to $daily ($(du -h "$daily" | cut -f1))"
    prune "$BACKUP_DIR/daily" "$KEEP_DAILY"
    prune "$BACKUP_DIR/monthly" "$KEEP_MONTHLY"
}

if [ "${1:-}" = once ]; then
    dump
    exit
fi

log "Backing up nightly at $BACKUP_HOUR:00 into $BACKUP_DIR"
while true; do
    now=$(date +%s)
    next=$(date -d "today $BACKUP_HOUR:00" +%s)
    [ "$next" -gt "$now" ] || next=$(date -d "tomorrow $BACKUP_HOUR:00" +%s)
    sleep $((next - now))
    # A failed night is logged and retried the next night; the older dumps stay.
    dump || true
done
