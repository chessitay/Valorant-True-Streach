# Valorant True Stretch Helper

A tool that automatically applies a true stretch resolution for Valorant on Windows.
By default, Valorant only stretches the UI, not the actual game world. This helper edits the configuration files so the game truly runs stretched.

There are two ways to use the tool:

- A GUI application (ValorantTrueStretch_GUI.py)
- A command-line script (valo_true_stretch_helper.py)


# Features
Automatic editing of Valorant config files
Ensures HDR and FullscreenMode settings are correct
Dry-run / preview mode before applying changes


# Usage

## GUI Version

1. Make sure **Valorant is close** (Riot Client can stay open).
2. Run "python ValorantTrueStretch_GUI.py"
3. In the GUI:
   - Select your **Native** Resolution (your monitor’s resolution).
   - Select your **Target** Resolution (the stretched res you want).
   - Click **VERIFY** → **PREVIEW** → **APPLY**.
4. Change your **Windows desktop resolution** to the same target resolution.
5. Launch Valorant.


## CLI Version

1. Make sure **Valorant is closed**.
2. Run "python valo_true_stretch_helper.py --native 2560x1440 --target 1280x1024 --yes"
   Options:
   - --native WxH → your monitor’s resolution.
   - --target WxH → resolution you want in VALORANT.
   - --force → skip native resolution check.
   - --yes → apply changes without confirmation.
  
# Notes
- Always launch VALORANT once in native fullscreen + aspect ratio fill before using this tool.
- After applying, you must set your Windows desktop resolution to match the target resolution for the stretch to work.


# Disclaimer
I’ve been using this tool myself for over a month and there’s **no reason you should get banned** for it.
It only edits **local config files**, nothing shady or external.
That said, please **use it at your own risk**.


# Credits
Made by **GlitchFL**.
Please keep credit if you share or modify this tool.
