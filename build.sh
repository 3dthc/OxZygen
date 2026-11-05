#!/usr/bin/env bash
# Build, test and package an OxZygen target with the MPC VST toolchain (open-mpc/mpc-vst-plugins).
#   ./build.sh            OxZygen itself (vst/)
#   ./build.sh sdtest     the SD card access test plugin
# Needs the toolchain checked out (default ~/mpc-vst-plugins; override with MPC_VST=/path) and Docker running.
# The first OxZygen build also downloads the toolchain's skin renderer image (Chromium), which takes a while once.
# Output: dist/<Name>-<version>-mpc-armv7.zip, also copied to your Windows Desktop when run in WSL.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
MPC_VST="${MPC_VST:-$HOME/mpc-vst-plugins}"
TARGET="${1:-oxzygen}"

LICENSE_ARGS=()
EXTRA_ARGS=()
case "$TARGET" in
  oxzygen) CFG="$HERE/vst/vst.json"; VER="0.2.0"
           ABOUT="OxZygen 0.2: choir (three singers, ah/oh/ih) and winds (flute, ocarina, alto sax) with reverb"
           EXTRA_ARGS=(--extra "$HERE/vst/data:samples")
           [ -f "$HERE/vst/data/manifest.txt" ] || { echo "vst/data is missing: run samples/fetch_sources.sh, samples/trim.sh, then python3 samples/prepare.py"; exit 1; } ;;
  sdtest)  CFG="$HERE/tests/sdtest/vst.json"; VER="1.0.0"; ABOUT="OxZygen SD card access test"; LICENSE_ARGS=(--license MIT) ;;
  *) echo "Unknown target '$TARGET'. Targets: oxzygen, sdtest"; exit 1 ;;
esac

if [ ! -x "$MPC_VST/tools/build_port.sh" ]; then
  echo "Toolchain not found at $MPC_VST. Clone it there or run: MPC_VST=/path/to/mpc-vst-plugins ./build.sh $TARGET"
  exit 1
fi

DIR="$(dirname "$CFG")"
NAME="$(python3 -c 'import json,sys; c=json.load(open(sys.argv[1])); print(c["vendor"]+" - VST - "+c["name"])' "$CFG")"
SO="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["so"])' "$CFG")"

echo "== build ($TARGET)"
"$MPC_VST/tools/build_port.sh" "$CFG"
echo "== offline test"
"$MPC_VST/tools/test_port.sh" "$CFG"
echo "== package"
mkdir -p "$HERE/dist"
python3 "$MPC_VST/tools/release.py" --so "$DIR/build/$SO" --skin "$DIR/build/skin/$NAME" \
  --entry "$DIR/build/pluginlist-entry.xml" --version "$VER" --about "$ABOUT" \
  ${LICENSE_ARGS[@]+"${LICENSE_ARGS[@]}"} ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"} --repo 3dthc/OxZygen -o "$HERE/dist"

ZIP="$(ls -t "$HERE"/dist/*.zip | head -n 1)"
echo "== zip: $ZIP"

# In WSL, put a copy where Windows can see it.
if [ -d "/mnt/c/Users/$USER" ]; then
  for d in "/mnt/c/Users/$USER/OneDrive/Desktop" "/mnt/c/Users/$USER/Desktop"; do
    if [ -d "$d" ]; then cp "$ZIP" "$d/"; echo "== copied to Windows: $d/$(basename "$ZIP")"; break; fi
  done
fi
