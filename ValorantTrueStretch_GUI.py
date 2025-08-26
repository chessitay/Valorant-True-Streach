# ValorantTrueStretch_GUI.py
# Tool to speed up "true stretch" config for VALORANT on Windows.
# Made by GlitchFL (credit required if you share)

import os, re, sys, difflib
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, font
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
import threading

APP_TITLE = "VALORANT Configuration Tool"
VERSION = "2.0"

FULLSCREEN_KEY = "FullscreenMode"
HDR_KEY = "HDRDisplayOutputNits"

COLORS = {
    'bg': '#1a1a1a',
    'bg_secondary': '#242424',
    'bg_tertiary': '#2d2d2d',
    'accent': '#4a9eff',
    'accent_hover': '#357dd8',
    'text': '#e0e0e0',
    'text_secondary': '#999999',
    'border': '#333333',
    'success': '#4ade80',
    'warning': '#fbbf24',
    'error': '#f87171'
}

RESOLUTIONS = {
    "native": ["3840x2160", "2560x1440", "1920x1080", "2560x1080", "3440x1440"],
    "target": ["1920x1080", "1680x1050", "1440x1080", "1280x1024", "1100x1080", "1080x1080", "1280x960", "1024x768"]
}

def parse_whx(s):
    s = s.strip()
    m = re.fullmatch(r"(\d+)[xX](\d+)", s)
    if not m:
        raise ValueError("Invalid format. Use WIDTHxHEIGHT (e.g., 2560x1440)")
    return int(m.group(1)), int(m.group(2))

def read_lines(path: Path):
    return path.read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True)

def write_lines(path: Path, lines):
    path.write_text("".join(lines), encoding="utf-8")

def update_kv_lines(lines, updates: dict):
    """Replace/add key=value pairs while preserving other content/formatting."""
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
    return "".join(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"{label} (current)",
        tofile=f"{label} (new)",
        n=3
    ))

def get_base_config_dir():
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise RuntimeError("Couldn't resolve %LOCALAPPDATA%. Are you on Windows?")
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



def process_gus(path: Path, target_x, target_y, apply_changes, label, log_func):
    if not path.is_file():
        log_func(f"- Skipping (not found): {label} -> {path}")
        return
    
    old = read_lines(path)

    # 1) Update res + flags
    updates = make_updates_for_target(target_x, target_y)
    temp, changed_a = update_kv_lines(old, updates)

    # 2) Ensure HDR=1000 + FullscreenMode=2 together
    temp2, inserted = ensure_hdr_and_fullscreen(temp, "1000", "2")
    changed = changed_a or (temp2 != old)

    if not changed:
        log_func(f"- No changes needed: {label}")
        return

    diff = file_diff(old, temp2, str(path))
    log_func(f"\n>>> {label}\n{diff if diff.strip() else '(content replaced)'}")
    if apply_changes:
        write_lines(path, temp2)
        log_func(f"-> Updated {label}.")
    else:
        log_func("-> Dry run (no write).")

# -------------------- Professional GUI --------------------

class ProfessionalApp(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.title(APP_TITLE)
        self.geometry("900x700")
        self.minsize(800, 600)
        self.configure(bg=COLORS['bg'])
        
        # Configure window
        self.resizable(True, True)
        
        # Set up main layout
        self.setup_ui()
        self.center_window()
        
    def center_window(self):
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (900 // 2)
        y = (self.winfo_screenheight() // 2) - (700 // 2)
        self.geometry(f"900x700+{x}+{y}")
        
    def setup_ui(self):
        main = tk.Frame(self, bg=COLORS['bg'])
        main.pack(fill='both', expand=True, padx=2, pady=2)
        
        self.create_title_section(main)
        self.create_instructions_section(main)
        self.create_config_section(main)
        self.create_action_section(main)
        self.create_output_section(main)
        self.create_status_line(main)
        
    def create_title_section(self, parent):
        title_frame = tk.Frame(parent, bg=COLORS['bg'], height=40)
        title_frame.pack(fill='x', pady=(15, 5))
        title_frame.pack_propagate(False)
        
        # Title
        title = tk.Label(
            title_frame,
            text="VALORANT TRUE STRETCH CONFIGURATION",
            bg=COLORS['bg'],
            fg=COLORS['text'],
            font=('Arial', 14, 'bold')
        )
        title.pack(side='left', padx=30)
        
        # Version
        version = tk.Label(
            title_frame,
            text=f"v{VERSION} | by GlitchFL",
            bg=COLORS['bg'],
            fg=COLORS['text_secondary'],
            font=('Arial', 9)
        )
        version.pack(side='right', padx=30)
        
    def create_instructions_section(self, parent):
        # Instructions frame
        inst_frame = tk.Frame(parent, bg=COLORS['bg_secondary'])
        inst_frame.pack(fill='x', padx=30, pady=(0, 10))
        
        # Inner padding
        inner = tk.Frame(inst_frame, bg=COLORS['bg_secondary'])
        inner.pack(fill='x', padx=15, pady=12)
        
        # Instructions text
        instructions = tk.Label(
            inner,
            text="SETUP: 1) Open VALORANT → Settings → Video → Display Mode: Fullscreen, Aspect Ratio: Fill → Apply → Close VALORANT\n"
                 "USAGE: 2) Enter your native resolution (monitor) and target resolution (stretched) → Click VERIFY → PREVIEW → APPLY\n"
                 "AFTER: 3) Change Windows desktop resolution to target → Launch VALORANT",
            bg=COLORS['bg_secondary'],
            fg=COLORS['text_secondary'],
            font=('Arial', 9),
            justify='left',
            anchor='w'
        )
        instructions.pack(fill='x')
        
    def create_config_section(self, parent):
        # Container
        config_frame = tk.Frame(parent, bg=COLORS['bg_secondary'])
        config_frame.pack(fill='x', padx=30, pady=(0, 10))
        
        # Inner padding
        inner = tk.Frame(config_frame, bg=COLORS['bg_secondary'])
        inner.pack(fill='x', padx=25, pady=15)
        
        # Grid layout
        inner.columnconfigure(1, weight=1)
        inner.columnconfigure(3, weight=1)
        
        # Native resolution
        tk.Label(
            inner,
            text="Native Resolution",
            bg=COLORS['bg_secondary'],
            fg=COLORS['text'],
            font=('Arial', 10),
            anchor='w'
        ).grid(row=0, column=0, sticky='w', pady=(0, 5))
        
        self.native_var = tk.StringVar(value="2560x1440")
        self.native_entry = self.create_styled_combobox(inner, self.native_var, RESOLUTIONS["native"])
        self.native_entry.grid(row=1, column=0, sticky='ew', padx=(0, 20))
        
        # Target resolution
        tk.Label(
            inner,
            text="Target Resolution",
            bg=COLORS['bg_secondary'],
            fg=COLORS['text'],
            font=('Arial', 10),
            anchor='w'
        ).grid(row=0, column=2, sticky='w', pady=(0, 5))
        
        self.target_var = tk.StringVar(value="1280x1024")
        self.target_entry = self.create_styled_combobox(inner, self.target_var, RESOLUTIONS["target"])
        self.target_entry.grid(row=1, column=2, sticky='ew', padx=(0, 20))
        
        # Force checkbox
        self.chk_force = tk.BooleanVar(value=False)
        check = tk.Checkbutton(
            inner,
            text="Force apply (skip native check)",
            variable=self.chk_force,
            bg=COLORS['bg_secondary'],
            fg=COLORS['text_secondary'],
            activebackground=COLORS['bg_secondary'],
            activeforeground=COLORS['text'],
            selectcolor=COLORS['bg_tertiary'],
            font=('Arial', 9),
            bd=0,
            highlightthickness=0
        )
        check.grid(row=2, column=0, columnspan=3, sticky='w', pady=(12, 0))
        
    def create_styled_combobox(self, parent, var, values):
        style = ttk.Style()
        style.configure('Custom.TCombobox',
                       fieldbackground=COLORS['bg'],
                       background=COLORS['bg_tertiary'],
                       foreground=COLORS['text'],
                       arrowcolor=COLORS['text_secondary'])
        
        combo = ttk.Combobox(
            parent,
            textvariable=var,
            values=values,
            style='Custom.TCombobox',
            font=('Arial', 10),
            width=18
        )
        return combo
        
    def create_action_section(self, parent):
        action_frame = tk.Frame(parent, bg=COLORS['bg'])
        action_frame.pack(fill='x', padx=30, pady=(0, 10))
        
        # Button container
        btn_container = tk.Frame(action_frame, bg=COLORS['bg'])
        btn_container.pack()
        
        # Create buttons
        self.create_button(btn_container, "VERIFY", self.preflight, False).pack(side='left', padx=5)
        self.create_button(btn_container, "PREVIEW", self.dry_run, False).pack(side='left', padx=5)
        self.create_button(btn_container, "APPLY", self.apply, True).pack(side='left', padx=5)
        
    def create_button(self, parent, text, command, primary=False):
        frame = tk.Frame(parent, bg=COLORS['bg'])
        
        if primary:
            bg = COLORS['accent']
            hover_bg = COLORS['accent_hover']
            fg = '#ffffff'
        else:
            bg = COLORS['bg_tertiary']
            hover_bg = COLORS['border']
            fg = COLORS['text']
        
        btn = tk.Label(
            frame,
            text=text,
            bg=bg,
            fg=fg,
            font=('Arial', 9, 'bold'),
            padx=30,
            pady=8,
            cursor='hand2'
        )
        btn.pack()
        
        def on_enter(e):
            btn.config(bg=hover_bg)
        def on_leave(e):
            btn.config(bg=bg)
        def on_click(e):
            command()
            
        btn.bind('<Enter>', on_enter)
        btn.bind('<Leave>', on_leave)
        btn.bind('<Button-1>', on_click)
        
        return frame
        
    def create_output_section(self, parent):
        # Container
        output_frame = tk.Frame(parent, bg=COLORS['bg_secondary'])
        output_frame.pack(fill='both', expand=True, padx=30, pady=(0, 10))
        
        # Header
        header = tk.Frame(output_frame, bg=COLORS['bg_tertiary'], height=32)
        header.pack(fill='x')
        header.pack_propagate(False)
        
        tk.Label(
            header,
            text="OUTPUT",
            bg=COLORS['bg_tertiary'],
            fg=COLORS['text'],
            font=('Arial', 9, 'bold')
        ).pack(side='left', padx=15, pady=8)
        
        clear_btn = tk.Label(
            header,
            text="Clear",
            bg=COLORS['bg_tertiary'],
            fg=COLORS['text_secondary'],
            font=('Arial', 9),
            cursor='hand2'
        )
        clear_btn.pack(side='right', padx=15, pady=8)
        clear_btn.bind('<Button-1>', lambda e: self.clear_log())
        
        # Text area
        text_frame = tk.Frame(output_frame, bg=COLORS['bg'])
        text_frame.pack(fill='both', expand=True)
        
        self.output = tk.Text(
            text_frame,
            bg=COLORS['bg'],
            fg=COLORS['text'],
            font=('Consolas', 9),
            wrap='word',
            relief='flat',
            padx=15,
            pady=10,
            insertbackground=COLORS['text']
        )
        self.output.pack(side='left', fill='both', expand=True)
        
        # Scrollbar
        scrollbar = tk.Scrollbar(text_frame, command=self.output.yview, bg=COLORS['bg_secondary'])
        scrollbar.pack(side='right', fill='y')
        self.output.config(yscrollcommand=scrollbar.set)
        
        # Configure tags
        self.output.tag_config('success', foreground=COLORS['success'])
        self.output.tag_config('warning', foreground=COLORS['warning'])
        self.output.tag_config('error', foreground=COLORS['error'])
        self.output.tag_config('dim', foreground=COLORS['text_secondary'])
        
        # Initial message
        self.log("Ready. Make sure VALORANT is completely closed (Riot Client can remain open).\n", 'dim')
        
    def create_status_line(self, parent):
        self.status = tk.Label(
            parent,
            text="Ready",
            bg=COLORS['bg'],
            fg=COLORS['text_secondary'],
            font=('Arial', 8),
            anchor='w'
        )
        self.status.pack(fill='x', padx=30, pady=(0, 10))
        
    def log(self, msg, tag=None):
        self.output.insert('end', msg + '\n', tag)
        self.output.see('end')
        self.update_idletasks()
        
    def clear_log(self):
        self.output.delete('1.0', 'end')
        
    def set_status(self, msg):
        self.status.config(text=msg)
        self.update_idletasks()
        
    def parse_inputs(self):
        try:
            nx, ny = parse_whx(self.native_var.get())
            tx, ty = parse_whx(self.target_var.get())
            return nx, ny, tx, ty
        except ValueError as e:
            messagebox.showerror("Input Error", str(e))
            return None
            
    def get_targets_and_check(self, nx, ny, force=False):
        base = get_base_config_dir()
        winclient = base / "WindowsClient"
        gus_root = winclient / "GameUserSettings.ini"

        if not gus_root.is_file():
            raise RuntimeError("Missing GameUserSettings.ini in WindowsClient. Launch Valorant once (native Fullscreen+Fill), then close.")

        # Native check
        root_lines = read_lines(gus_root)
        ok, bad_key, bad_val = native_check_ok(root_lines, nx, ny)
        if not ok and not force:
            self.log(f"[!] Native check failed on {gus_root}", 'error')
            self.log(f"    Expected {bad_key} to match native {nx}x{ny} / flags False. Got '{bad_val}'.", 'error')
            self.log("    -> Open Valorant on Fullscreen+Fill at native, then close and rerun.", 'warning')
            self.set_status("Native check failed")
            return None
        elif not ok and force:
            self.log(f"[!] Native check failed but continuing (--force). Key {bad_key} got '{bad_val}'", 'warning')

        last_user = get_last_known_user(winclient)
        user_dir = find_user_folder(base, last_user) if last_user else None

        self.log(f"Base config: {base}", 'dim')
        self.log(f"LastKnownUser: {last_user or '??'}", 'dim')
        self.log(f"User folder: {user_dir if user_dir else 'NOT FOUND (will still update root)'}", 'dim')

        targets = [(gus_root, "Root WindowsClient/GameUserSettings.ini")]
        if user_dir:
            targets += [
                (user_dir / "WindowsClient" / "GameUserSettings.ini", f"{user_dir.name}/WindowsClient/GameUserSettings.ini"),
                (user_dir / "Windows" / "GameUserSettings.ini", f"{user_dir.name}/Windows/GameUserSettings.ini"),
            ]

        return targets
        
    def run_async(self, func):
        thread = threading.Thread(target=func, daemon=True)
        thread.start()
        
    def preflight(self):
        def _run():
            self.clear_log()
            self.set_status("Verifying configuration...")
            
            parsed = self.parse_inputs()
            if not parsed:
                self.set_status("Invalid input")
                return
            nx, ny, tx, ty = parsed
            
            try:
                targets = self.get_targets_and_check(nx, ny, force=self.chk_force.get())
                if targets is None:
                    return
                    
                self.log("\nPlanned updates:")
                for p, lbl in targets:
                    self.log(f" - {lbl} -> {p}")
                    
                self.log("\nVerification complete.", 'success')
                self.set_status("Verification complete")
            except Exception as e:
                self.log(f"Error: {e}", 'error')
                self.set_status("Error occurred")
                
        self.run_async(_run)
        
    def dry_run(self):
        def _run():
            self.clear_log()
            self.set_status("Running preview...")
            
            parsed = self.parse_inputs()
            if not parsed:
                self.set_status("Invalid input")
                return
            nx, ny, tx, ty = parsed
            
            try:
                targets = self.get_targets_and_check(nx, ny, force=self.chk_force.get())
                if targets is None:
                    return
                    
                self.log("\nPlanned updates:")
                for p, lbl in targets:
                    self.log(f" - {lbl} -> {p}")
                    
                # Process each target with dry run
                for p, lbl in targets:
                    if p.exists():
                        process_gus(p, tx, ty, apply_changes=False, label=lbl, log_func=self.log)
                    else:
                        self.log(f"- Not found: {lbl} -> {p} (skipped)")
                        
                self.log("\nDry run complete.", 'success')
                self.set_status("Preview complete")
            except Exception as e:
                self.log(f"Error: {e}", 'error')
                self.set_status("Error occurred")
                
        self.run_async(_run)
        
    def apply(self):
        def _run():
            self.clear_log()
            self.set_status("Applying configuration...")
            
            parsed = self.parse_inputs()
            if not parsed:
                self.set_status("Invalid input")
                return
            nx, ny, tx, ty = parsed
            
            try:
                targets = self.get_targets_and_check(nx, ny, force=self.chk_force.get())
                if targets is None:
                    return
                    
                self.log("\nPlanned updates:")
                for p, lbl in targets:
                    self.log(f" - {lbl} -> {p}")
                    
                # Process each target with actual writes
                for p, lbl in targets:
                    if p.exists():
                        process_gus(p, tx, ty, apply_changes=True, label=lbl, log_func=self.log)
                    else:
                        self.log(f"- Not found: {lbl} -> {p} (skipped)")
                        
                self.log("\nDone.", 'success')
                self.log(f"Next steps:", 'success')
                self.log(f"  1) Change your Windows desktop resolution to {tx}x{ty}.")
                self.log(f"  2) Launch Valorant.")
                
                self.set_status("Configuration applied successfully")
            except Exception as e:
                self.log(f"Error: {e}", 'error')
                self.set_status("Error occurred")
                
        result = messagebox.askquestion(
            "Confirm",
            "This will modify VALORANT configuration files.\n\n"
            "Make sure VALORANT is completely closed.\n"
            "(Riot Client can remain open)\n\n"
            "Proceed?",
            icon='warning'
        )
        if result == 'yes':
            self.run_async(_run)

if __name__ == "__main__":
    app = ProfessionalApp()
    app.mainloop()