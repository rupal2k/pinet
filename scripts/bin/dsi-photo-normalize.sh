#!/bin/bash
# Fit every photo in the slideshow folder on PINET storage inside the DSI
# panel (800x480) as JPEGs in the cache folder. The whole photo is always
# shown -- never cropped; leftover space (sides for portrait photos,
# top/bottom for wide ones) shows a darkened, blurred copy of the same photo
# stretched to fill the panel. Small photos are scaled up. The blur runs on a
# tiny thumbnail that is then scaled up: smooth, and cheap on the Pi 3.
# Skips photos already done and unchanged (mtime), drops cache entries whose
# photo was removed, and skips files that fail to convert (e.g. still being
# copied) -- the watcher re-runs this once they change again.
set -uo pipefail

PANEL_SIZE="800x480"
BLUR_SIZE="80x48"      # thumbnail the background is blurred at
BLUR_SIGMA="5"
BG_BRIGHTNESS="50"     # % -- keeps the background behind the photo
SRC="/mnt/pinet-media/slideshow"
DST="/mnt/pinet-media/slideshow-cache"
# Changes whenever the rendering does, so existing cache entries get redone.
RENDER_MODE="fit-$PANEL_SIZE-blur-$BLUR_SIZE-$BLUR_SIGMA-$BG_BRIGHTNESS"

[ -d "$SRC" ] || exit 0
mkdir -p "$DST"

if [ "$(cat "$DST/.render-mode" 2>/dev/null)" != "$RENDER_MODE" ]; then
    rm -f "$DST"/*.jpg
    echo "$RENDER_MODE" > "$DST/.render-mode"
fi

shopt -s nullglob nocaseglob
for src in "$SRC"/*.{jpg,jpeg,png,webp,heic,heif,bmp,tif,tiff}; do
    dst="$DST/$(basename "$src").jpg"
    [ -f "$dst" ] && [ "$dst" -nt "$src" ] && continue
    # jpeg:size lets libjpeg decode big JPEGs at a reduced scale (faster).
    if ! convert -define jpeg:size=1600x960 "${src}[0]" -auto-orient \
            -background black -alpha remove \
            \( -clone 0 -resize "${BLUR_SIZE}^" -gravity center -extent "$BLUR_SIZE" \
               -blur "0x$BLUR_SIGMA" -resize "${PANEL_SIZE}!" -modulate "$BG_BRIGHTNESS" \) \
            \( -clone 0 -resize "$PANEL_SIZE" \) \
            -delete 0 -gravity center -composite \
            -quality 90 "$dst.tmp.jpg" 2>/dev/null; then
        rm -f "$dst.tmp.jpg"
        echo "skipped (unreadable or still copying): $(basename "$src")" >&2
        continue
    fi
    mv -f "$dst.tmp.jpg" "$dst"
done
shopt -u nocaseglob

for dst in "$DST"/*.jpg; do
    [ -f "$SRC/$(basename "$dst" .jpg)" ] || rm -f "$dst"
done
