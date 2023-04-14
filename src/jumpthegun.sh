#!/bin/bash
set -eEu -o pipefail

function usage() {
  echo "Usage: $0 command tool_name ..."
  echo
  echo "Available commands:"
  echo
  echo "run tool_name [OPTIONS] [arg ...]    Run a CLI tool."
  echo "start tool_name                      Start a daemon for a CLI tool."
  echo "stop tool_name                       Stop a daemon for a CLI tool."
  echo "restart tool_name                    Restart a daemon for a CLI tool."
  echo
}

function err_exit() {
  err_msg="$1"
  echo "$err_msg" >&2
  exit 1
}

autorun=1
case "${1:-}" in
-h|--help)
  usage && exit 0 ;;
start|stop|restart|version|--version)
  exec jumpthegunctl "$@" ;;
run)
  shift
  [[ $# -eq 0 ]] && usage && exit 1
  if [[ "$1" == "--no-autorun" ]]; then
    autorun=0
    shift
  fi
  ([[ "$1" == "-h" ]] || [[ "$1" == "--help" ]]) && usage && exit 0
  tool_name="$1"
  shift
  ;;
*)
  usage && exit 1 ;;
esac

# Find service runtime directory.
runtime_dir="${XDG_RUNTIME_DIR:-}"
if [ -n "$runtime_dir" ]; then
  service_runtime_dir="$runtime_dir/jumpthegun"
else
  temp_dir="${TMPDIR:-/tmp}"
  shopt -s nullglob
  service_runtime_dirs=("$temp_dir/jumpthegun-$USER"-??????)
  shopt -u nullglob
  if [[ ${#service_runtime_dirs[@]} -eq 0 ]]; then
    [[ autorun -eq 1 ]] && jumpthegunctl start "$tool_name" >/dev/null 2>&1
    exec "$tool_name" "$@"
  elif [[ ${#service_runtime_dirs[@]} -gt 1 ]]; then
    err_exit "Error: Multiple service runtime dirs found."
  fi
  service_runtime_dir="${service_runtime_dirs[0]}"
fi

# Calculate the isolated path for pid and port files.
isolated_root="$(dirname "$(command -v "$tool_name")")"
if [[ $OSTYPE == "darwin"* ]]; then
  isolated_root_hash="$(echo -n "$isolated_root" | shasum -a 256 - | head -c 8)"
else
  isolated_root_hash="$(echo -n "$isolated_root" | sha256sum - | head -c 8)"
fi
isolated_path="$service_runtime_dir/$isolated_root_hash/"

# Check that port file exists.
if [[ ! -f "$isolated_path/$tool_name.port" ]]; then
  [[ autorun -eq 1 ]] && jumpthegunctl start "$tool_name" >/dev/null 2>&1
  exec "$tool_name" "$@"
fi

# Read port from port file.
IFS= read -r port <"$isolated_path/$tool_name.port"

# Open TCP connection.
exec 3<>"/dev/tcp/127.0.0.1/$port"

# Close TCP connection upon exit.
function close_connection {
  exec 3<&-
}
trap close_connection EXIT


# Read companion process PID.
read -r -u 3 pid

# Forward some signals.
function forward_signal() {
  kill -s "$1" "$pid"
}
for sig in INT TERM USR1 USR2; do
  trap "forward_signal $sig" "$sig"
done


# Send cmdline arguments.
echo "$@" >&3


# Read stdout and stderr from connection, line by line, and echo them.
IFS=
while read -r -u 3 line; do
  case "$line" in
    1*)
      # stdout
      n_newlines="${line:1}"
      for (( i=1; i <= n_newlines; i++ )); do
        read -r -u 3 line
        echo "$line"
      done
      read -r -u 3 line
      echo -n "$line"
      ;;
    2*)
      # stderr
      n_newlines="${line:1}"
      for (( i=1; i <= n_newlines; i++ )); do
        read -r -u 3 line
        echo "$line" >&2
      done
      read -r -u 3 line
      echo -n "$line" >&2
      ;;
    3*)
      # stdin
      read -r line2
      echo "$line2" >&3
      ;;
    rc=*)
      # exit
      rc="${line:3}"
      exit "$rc"
      ;;
    *)
      echo "Error: Unexpected output from jumpthegun daemon." >&2
      exit 1
      ;;
  esac
done
