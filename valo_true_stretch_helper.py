
import argparse, os, re, sys, difflib
from pathlib import Path

FULLSCREEN_KEY = "FullscreenMode"
HDR_KEY = "HDRDisplayOutputNits"

def parse_whx(s):
    m = re.fullmatch(r"\s*(\d+)\s*[xX]\s*(\d+)\s*", s)
    if not m:
        raise ValueError("Use format WxH (e.g., 2560x1440)")
    return int(m.group(1)), int(m.group(2))

def read_lines(path: Path):
    return path.read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True)

def write_lines(path: Path, lines):
    path.write_text("".join(lines), encoding="utf-8")

def update_kv_lines(lines, updates: dict):
    changed = False
    found = set()
    out = []
    for ln in lines:
        m = re.match(r"^\s*([A-Za-z0-9_]+)\s*=\s*(.*)\s*$", ln)
        if m:
            k = m.group(1)
            if k in updates and updates[k] is not None:
                v = str(updates[k])
                new_ln = f"{k}={v}\n"
                if ln != new_ln:
                    changed = True
                    ln = new_ln
                found.add(k)
        out.append(ln)
    for k, v in updates.items():
        if v is None: continue
        if k not in found:
            out.append(f"{k}={v}\n")
            changed = True
    return out, changed

def ensure_hdr_and_fullscreen(lines, hdr_val="1000", fs_val="2"):
    """
    Guarantee HDRDisplayOutputNits=hdr_val and FullscreenMode=fs_val
    with FullscreenMode placed directly below HDR.
    If HDR line missing entirely, append both HDR + Fullscreen at EOF.
    """
    out = []
    seen_hdr = False
    inserted_fs = False

    for ln in lines:
        if re.match(rf"^\s*{HDR_KEY}\s*=\s*\d+\s*$", ln):
            seen_hdr = True
            ln = f"{HDR_KEY}={hdr_val}\n"
            out.append(ln)
            out.append(f"{FULLSCREEN_KEY}={fs_val}\n")
            inserted_fs = True
        elif re.match(rf"^\s*{FULLSCREEN_KEY}\s*=\s*\d+\s*$", ln):
            # skip old FullscreenMode lines, since we'll reinsert
            continue
        else:
            out.append(ln)

    if not seen_hdr:
        if len(out) == 0 or not out[-1].endswith("\n"):
            out.append("\n")
        out.append(f"{HDR_KEY}={hdr_val}\n")
        out.append(f"{FULLSCREEN_KEY}={fs_val}\n")
        inserted_fs = True

    return out, inserted_fs

def file_diff(old_lines, new_lines, label):
    return "".join(
        difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"{label} (current)",
            tofile=f"{label} (new)",
            n=3
        )
    )

def get_base_config_dir():
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        print("Couldn't resolve %LOCALAPPDATA%. Are you on Windows?", file=sys.stderr)
        sys.exit(1)
    return Path(local) / "VALORANT" / "Saved" / "Config"

def get_last_known_user(windows_client_dir: Path):
    rlmi = windows_client_dir / "RiotLocalMachine.ini"
    if not rlmi.is_file():
        return None
    txt = rlmi.read_text(encoding="utf-8", errors="ignore").splitlines()
    for ln in txt:
        m = re.match(r"^\s*LastKnownUser\s*=\s*([A-Za-z0-9\-]+)\s*$", ln)
        if m:
            return m.group(1)
    return None

def find_user_folder(base: Path, last_known: str):
    if not last_known:
        return None
    candidates = [p for p in base.iterdir()
                  if p.is_dir() and p.name.lower().startswith(last_known.lower() + "-")]
    def score(p):
        s = 0
        if (p / "Windows").is_dir(): s += 1
        if (p / "WindowsClient").is_dir(): s += 1
        return s
    if not candidates:
        return None
    candidates.sort(key=score, reverse=True)
    return candidates[0]

def native_check_ok(lines, native_x, native_y):
    want = {
        "ResolutionSizeX": str(native_x),
        "ResolutionSizeY": str(native_y),
        "LastUserConfirmedResolutionSizeX": str(native_x),
        "LastUserConfirmedResolutionSizeY": str(native_y),
        "bShouldLetterbox": "False",
        "bLastConfirmedShouldLetterbox": "False",
    }
    got = {}
    for ln in lines:
        m = re.match(r"^\s*([A-Za-z0-9_]+)\s*=\s*(.*)\s*$", ln)
        if m:
            got[m.group(1)] = m.group(2).strip()
    for k, v in want.items():
        if got.get(k) != v:
            return False, k, got.get(k)
    return True, None, None

def make_updates_for_target(target_x, target_y):
    return {
        "ResolutionSizeX": str(target_x),
        "ResolutionSizeY": str(target_y),
        "LastUserConfirmedResolutionSizeX": str(target_x),
        "LastUserConfirmedResolutionSizeY": str(target_y),
        "bShouldLetterbox": "False",
        "bLastConfirmedShouldLetterbox": "False",
    }

def process_gus(path: Path, target_x, target_y, apply_changes, label):
    if not path.is_file():
        print(f"- Skipping (not found): {label} -> {path}")
        return
    old = read_lines(path)

    # 1) Update res + flags
    updates = make_updates_for_target(target_x, target_y)
    temp, changed_a = update_kv_lines(old, updates)

    # 2) Ensure HDR=1000 + FullscreenMode=2 together
    temp2, inserted = ensure_hdr_and_fullscreen(temp, "1000", "2")
    changed = changed_a or (temp2 != old)

    if not changed:
        print(f"- No changes needed: {label}")
        return

    diff = file_diff(old, temp2, str(path))
    print(f"\n>>> {label}\n{diff if diff.strip() else '(content replaced)'}")
    if apply_changes:
        write_lines(path, temp2)
        print(f"-> Updated {label}.")
    else:
        print("-> Dry run (no write).")

def main():
    ap = argparse.ArgumentParser(
        description="Valorant true-stretch helper (Windows). Close Valorant/Riot first."
    )
    ap.add_argument("--native", required=True, help="Your desktop native res, e.g. 2560x1440")
    ap.add_argument("--target", required=True, help="The res you want in Valorant, e.g. 1280x1024")
    ap.add_argument("--yes", action="store_true", help="Apply without confirmation")
    ap.add_argument("--force", action="store_true", help="Apply even if native-check fails")
    args = ap.parse_args()

    try:
        nx, ny = parse_whx(args.native)
        tx, ty = parse_whx(args.target)
    except ValueError as e:
        print(e); sys.exit(1)

    base = get_base_config_dir()
    winclient = base / "WindowsClient"
    gus_root = winclient / "GameUserSettings.ini"

    if not gus_root.is_file():
        print("Missing GameUserSettings.ini in WindowsClient. Launch Valorant once (native Fullscreen+Fill), then close.", file=sys.stderr)
        sys.exit(1)

    # Native check
    root_lines = read_lines(gus_root)
    ok, bad_key, bad_val = native_check_ok(root_lines, nx, ny)
    if not ok and not args.force:
        print(f"[!] Native check failed on {gus_root}")
        print(f"    Expected {bad_key} to match native {args.native} / flags False. Got '{bad_val}'.")
        print("    -> Open Valorant on Fullscreen+Fill at native, then close and rerun.")
        sys.exit(2)
    elif not ok and args.force:
        print(f"[!] Native check failed but continuing (--force). Key {bad_key} got '{bad_val}'")

    last_user = get_last_known_user(winclient)
    user_dir = find_user_folder(base, last_user) if last_user else None

    print(f"Base config: {base}")
    print(f"LastKnownUser: {last_user or '??'}")
    print(f"User folder: {user_dir if user_dir else 'NOT FOUND (will still update root)'}")

    targets = [(gus_root, "Root WindowsClient/GameUserSettings.ini")]
    if user_dir:
        targets += [
            (user_dir / "WindowsClient" / "GameUserSettings.ini", f"{user_dir.name}/WindowsClient/GameUserSettings.ini"),
            (user_dir / "Windows"       / "GameUserSettings.ini", f"{user_dir.name}/Windows/GameUserSettings.ini"),
        ]

    print("\nPlanned updates:")
    for p, lbl in targets:
        print(" -", lbl, "->", p)

    apply_changes = args.yes
    if not apply_changes:
        resp = input("\nApply changes? [y/N]: ").strip().lower()
        apply_changes = (resp == "y")

    for p, lbl in targets:
        if p.exists():
            process_gus(p, tx, ty, apply_changes, lbl)
        else:
            print(f"- Not found: {lbl} -> {p} (skipped)")

    print("\nDone.")
    print(f"Next steps:")
    print(f"  1) Change your Windows desktop resolution to {tx}x{ty}.")
    print("  2) Launch Valorant.")

if __name__ == "__main__":
    main()
