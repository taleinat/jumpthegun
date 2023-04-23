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

function get_service_runtime_dir() {
  runtime_dir="${XDG_RUNTIME_DIR:-}"
  if [ -n "$runtime_dir" ]; then
    echo -n "$runtime_dir/jumpthegun"
  else
    temp_dir="${TMPDIR:-/tmp}"
    shopt -s nullglob
    service_runtime_dirs=("$temp_dir/jumpthegun-$USER"-??????)
    shopt -u nullglob
    if [[ ${#service_runtime_dirs[@]} -eq 1 ]]; then
      echo -n "${service_runtime_dirs[0]}"
    elif [[ ${#service_runtime_dirs[@]} -gt 1 ]]; then
      err_exit "Error: Multiple service runtime dirs found."
    fi
  fi
}

function hash_str() {
  if [[ $OSTYPE == "darwin"* ]]; then
    echo -n "$1" | shasum -a 256 - | head -c 8
  else
    echo -n "$1" | sha256sum - | head -c 8
  fi
}

autorun=1
case "${1:-}" in
-h|--help)
  usage && exit 0 ;;
start|stop|restart|version|--version)
  [[ "$2" =~ -h|--help ]] && usage && exit 0
  tool_name="$2"

  # Find the tool's Python executable and check if it has JumpTheGun installed.
  tool_path="$(command -v -- "$tool_name")"
  shebang="$(head -n 1 -- "$tool_path")"
  if ! python_executable="$(${shebang#\#!} -c 'import sys; print(sys.executable); import jumpthegun' 2>/dev/null)"; then
    # Find JumpTheGun's code.
    SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
    jumpthegunctl_path="$SCRIPT_DIR/jumpthegunctl"
    jumpthegunctl_shebang="$(head -n 1 -- "$jumpthegunctl_path")"
    jumpthegunctl_python_executable="$(${jumpthegunctl_shebang#\#!} -c 'import sys; print(sys.executable)')"
    jumpthegun_lib_dir="$("$jumpthegunctl_python_executable" -c 'import jumpthegun, os; print(os.path.dirname(jumpthegun.__file__))')"

    # Make a copy of this version of JumpTheGun's code in a cache directory.
    dir_name="lib-$(hash_str "$python_executable|$(head -n 1 "$jumpthegun_lib_dir/__version__.py")")"
    cache_home=${XDG_CACHE_HOME:-"$HOME/.cache"}
    cache_dir="$cache_home/jumpthegun/$dir_name"
    if [ ! -d "$cache_dir" ]; then
      mkdir -p "$cache_dir"
      cp -r -- "$jumpthegun_lib_dir" "$cache_dir/jumpthegun"
      find "$cache_dir/jumpthegun" -type f -not -name '*.py' -exec rm {} +
    fi

    # Add the cache directory to PYTHONPATH.
    if [[ -n "${PYTHONPATH:-}" ]]; then
      export PYTHONPATH="$cache_dir:$PYTHONPATH"
    else
      export PYTHONPATH="$cache_dir"
    fi
  fi

  # Run JumpTheGun.
  exec "$python_executable" -c "from jumpthegun.jumpthegunctl import main; main()" "$@"
  ;;
run)
  shift
  [[ $# -eq 0 ]] && usage && exit 1
  if [[ "$1" == "--no-autorun" ]]; then
    autorun=0
    shift
  fi
  [[ "$1" =~ -h|--help ]] && usage && exit 0
  tool_name="$1"
  shift
  ;;
*)
  usage && exit 1 ;;
esac

# Find service runtime directory.
service_runtime_dir="$(get_service_runtime_dir)"
if [[ -z "$service_runtime_dir" ]]; then
  [[ autorun -eq 1 ]] && "${BASH_SOURCE[0]}" start "$tool_name" &>/dev/null &
  exec "$tool_name" "$@"
fi

# Calculate the isolated path for pid and port files.
isolated_root="$(dirname "$(command -v -- "$tool_name")")"
isolated_root_hash="$(hash_str "$isolated_root")"
isolated_path="$service_runtime_dir/$isolated_root_hash"

# Check that port file exists.
if [[ ! -f "$isolated_path/$tool_name.port" ]]; then
  [[ autorun -eq 1 ]] && "${BASH_SOURCE[0]}" start "$tool_name" &>/dev/null &
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
