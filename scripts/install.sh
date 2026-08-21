#!/usr/bin/env sh
set -eu

# Official macOS/Linux installer for the checksum-verified wheel release.
# Download this file, inspect it, then execute it; avoid piping an unreviewed
# remote script directly to a shell in production environments.

repo_url=${KITCLI_REPOSITORY:-https://github.com/zhouhanker/agent-kits}
release_version=${KITCLI_VERSION:-latest}
install_root=${KITCLI_INSTALL_ROOT:-"$HOME/.local/share/kitcli"}
bin_dir=${KITCLI_BIN_DIR:-"$HOME/.local/bin"}

case "$repo_url" in
  https://*) ;;
  *) echo "kitcli installer: KITCLI_REPOSITORY must use HTTPS" >&2; exit 2 ;;
esac
command -v curl >/dev/null 2>&1 || { echo "kitcli installer: curl is required" >&2; exit 3; }

python_cmd=${KITCLI_PYTHON:-}
if [ -z "$python_cmd" ]; then
  if command -v python3 >/dev/null 2>&1; then python_cmd=python3
  elif command -v python >/dev/null 2>&1; then python_cmd=python
  else echo "kitcli installer: Python 3.11+ is required" >&2; exit 3
  fi
fi

python_version=$($python_cmd -c 'import sys; print("%d.%d" % sys.version_info[:2])')
$python_cmd -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || {
  echo "kitcli installer: found Python $python_version, need Python 3.11+" >&2
  exit 3
}

tmp_dir=$(mktemp -d "${TMPDIR:-/tmp}/kitcli-install.XXXXXX")
cleanup() { rm -rf "$tmp_dir"; }
trap cleanup EXIT INT TERM

if [ -n "${KITCLI_WHEEL_URL:-}" ]; then
  wheel_url=$KITCLI_WHEEL_URL
  wheel_name=${KITCLI_WHEEL_NAME:-$(basename "$wheel_url")}
  checksum_url=${KITCLI_CHECKSUM_URL:-}
  release_api_url=${KITCLI_RELEASE_API_URL:-}
else
  repo_path=${repo_url#https://github.com/}
  repo_path=${repo_path%/}
  api_url=${KITCLI_RELEASE_API_URL:-"https://api.github.com/repos/$repo_path/releases/latest"}
  if [ "$release_version" != "latest" ]; then
    api_url="https://api.github.com/repos/$repo_path/releases/tags/$release_version"
  fi
  curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 --max-time 120 "$api_url" -o "$tmp_dir/release.json"
  release_assets=$($python_cmd - "$tmp_dir/release.json" <<'PY'
import json
import pathlib
import sys

data = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
assets = {item["name"]: item["browser_download_url"] for item in data.get("assets", [])}
wheels = sorted(name for name in assets if name.startswith("agent_kits-") and name.endswith("-py3-none-any.whl"))
if len(wheels) != 1 or "SHA256SUMS" not in assets:
    raise SystemExit("release must contain one agent_kits wheel and SHA256SUMS")
print(wheels[0])
print(assets[wheels[0]])
print(assets["SHA256SUMS"])
PY
)
wheel_name=$(printf '%s\n' "$release_assets" | sed -n '1p')
wheel_url=$(printf '%s\n' "$release_assets" | sed -n '2p')
  checksum_url=$(printf '%s\n' "$release_assets" | sed -n '3p')
  release_api_url=$api_url
fi

case "$wheel_url" in https://github.com/*|https://objects.githubusercontent.com/*) ;; *) echo "kitcli installer: release wheel URL must use GitHub HTTPS" >&2; exit 2 ;; esac
case "$checksum_url" in https://github.com/*|https://objects.githubusercontent.com/*) ;; *) echo "kitcli installer: checksum URL must use GitHub HTTPS" >&2; exit 2 ;; esac

curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 --max-time 120 "$wheel_url" -o "$tmp_dir/$wheel_name"
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 --max-time 120 "$checksum_url" -o "$tmp_dir/SHA256SUMS"
$python_cmd - "$tmp_dir/$wheel_name" "$tmp_dir/SHA256SUMS" "$wheel_name" <<'PY'
import hashlib
import pathlib
import sys

wheel, checksums = map(pathlib.Path, sys.argv[1:3])
name = sys.argv[3]
expected = None
for line in checksums.read_text(encoding="utf-8").splitlines():
    fields = line.split()
    if len(fields) >= 2 and pathlib.Path(fields[-1].lstrip("*?")).name == name:
        expected = fields[0].lower()
        break
if not expected or len(expected) != 64:
    raise SystemExit(f"checksum missing for {name}")
actual = hashlib.sha256(wheel.read_bytes()).hexdigest()
if actual != expected:
    raise SystemExit("SHA-256 verification failed")
PY

mkdir -p "$install_root" "$bin_dir"
venv_dir="$install_root/venv"
if [ ! -x "$venv_dir/bin/python" ]; then
  "$python_cmd" -m venv "$venv_dir"
fi
"$venv_dir/bin/python" -m pip install --upgrade --no-deps "$tmp_dir/$wheel_name" >/dev/null
ln -sf "$venv_dir/bin/kitcli" "$bin_dir/kitcli"
ln -sf "$venv_dir/bin/agent-kits" "$bin_dir/agent-kits"

$python_cmd - "$install_root/install.json" "$venv_dir/bin/python" "$wheel_url" "$checksum_url" "$release_api_url" "$install_root" "$bin_dir" <<'PY'
import json
import pathlib
import sys

output, python, wheel_url, checksum_url, release_api_url, install_root, bin_dir = sys.argv[1:]
pathlib.Path(output).write_text(json.dumps({
    "schema_version": 1,
    "method": "official-isolated-installer",
    "package": "agent-kits",
    "python": python,
    "wheel_url": wheel_url,
    "checksum_url": checksum_url,
    "release_api_url": release_api_url,
    "install_root": install_root,
    "bin_dir": bin_dir,
}, indent=2) + "\n", encoding="utf-8")
PY

echo "kitcli installed in $venv_dir"
if [ -x "$bin_dir/kitcli" ]; then
  case ":$PATH:" in *":$bin_dir:"*) ;; *) echo "Add $bin_dir to PATH, then run: kitcli doctor" ;; esac
fi
