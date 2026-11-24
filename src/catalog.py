# SPDX-License-Identifier: GPL-3.0-or-later
"""Vista Control Panel catalog: Windows Vista Control Panel structure mapped onto
KDE settings modules (KCMs) and Linux tools.

Actions (strings):
  kcm:<name>        open one settings module in its own window (kcmshell6); on X11 the
                    <name>_x11 variant is used when it exists
  settings:<name>   open full System Settings at that module
  app:<cmd ...>     run a program
  page:<id>         internal page (a category id, "sysinfo", "admintools", "classic")
  native:<id>[#tab] native Windows-style applet dialog (applets/), e.g. native:power#buttons
  a|b               fallback chain: the first available action is used
Anything whose module/program isn't installed is hidden automatically.
"""
from dataclasses import dataclass, field
import distro


@dataclass
class Task:
    """A blue task link: its text and the action it opens."""
    label: str
    action: str


@dataclass
class Applet:
    """A Control Panel item: green title link (+ description, task links) on its category's
    page, a tile in Classic View, and a search result (name, description, keywords, tasks)."""
    id: str
    name: str
    icon: str
    action: str
    category: str
    description: str = ""
    tasks: list = field(default_factory=list)
    keywords: str = ""


@dataclass
class Category:
    """A home page category; its page lists the applets whose `category` is its id."""
    id: str
    name: str
    icon: str
    tasks: list = field(default_factory=list)   # shown under the heading on the home page
    hidden: bool = False                       # pages that aren't on the home page
    describe: bool = False                     # show each applet's description on its page
    subtitle: str = ""                         # explanation under the page heading


T = Task      # short alias for the tables below

CATEGORIES = [
    Category("system", "System and Maintenance", "preferences-system-performance", [
        T(f"Get started with {distro.NAME}", "app:plasma-welcome"),
        T("Back up your computer", "page:backup"),
        T("View basic information about your computer", "page:sysinfo"),
    ]),
    Category("security", "Security", "preferences-security", [
        T("Check for updates", "app:plasma-discover --mode Update"),
        T("Allow a program through the firewall", "kcm:kcm_firewall"),
    ]),
    Category("network", "Network and Internet", "preferences-system-network", [
        T("View network status and tasks", "native:network|kcm:kcm_networkmanagement"),
        T("Set up file sharing", "page:sharing"),
    ]),
    Category("hardware", "Hardware and Sound", "preferences-desktop-peripherals", [
        T("Play CDs or other media automatically", "kcm:kcm_solid_actions"),
        T("Printer", "kcm:kcm_printer_manager"),
        T("Mouse", "native:mouse|kcm:kcm_mouse"),
    ]),
    Category("programs", "Programs", "system-software-install", [
        T("Uninstall a program", "native:programs|app:plasma-discover --mode Installed"),
        T("Change startup programs", "kcm:kcm_autostart"),
    ]),
    Category("users", "User Accounts", "system-users", [
        T("Add or remove user accounts", "native:useraccounts#manage|kcm:kcm_users"),
        T("Change your password", "native:useraccounts#password|kcm:kcm_users"),
    ]),
    Category("appearance", "Appearance and Personalization", "preferences-desktop-theme", [
        T("Change desktop background", "native:background|kcm:kcm_wallpaper"),
        T("Customize colors", "native:windowcolor|kcm:kcm_colors"),
        T("Adjust screen resolution", "native:display|kcm:kcm_kscreen"),
    ]),
    Category("clock", "Clock, Language, and Region", "preferences-desktop-locale", [
        T("Change keyboards or other input methods", "native:keyboard#languages|kcm:kcm_keyboard"),
        T("Change display language", "native:region#languages|kcm:kcm_regionandlang"),
    ]),
    Category("access", "Ease of Access", "preferences-desktop-accessibility", [
        T(f"Let {distro.NAME} suggest settings", "kcm:kcm_access"),
        T("Optimize visual display", "kcm:kcm_access"),
    ]),
    Category("other", "Additional Options", "preferences-other", [
        T("Open all settings", "app:systemsettings"),
    ]),
    Category("admintools", "Administrative Tools", "preferences-system-services", hidden=True, describe=True),
    Category("personalize", "Personalization", "preferences-desktop-theme", hidden=True, describe=True,
             subtitle="Personalize appearance and sounds"),
]

APPLETS = [
    # --- System and Maintenance -----------------------------------------------------
    Applet("welcome", "Welcome Center", "plasma-welcome", "app:plasma-welcome", "system",
           f"Get started with {distro.NAME}", [
               T(f"Get started with {distro.NAME}", "app:plasma-welcome"),
           ], "welcome tour introduction getting started"),
    Applet("backup", "Backup and Restore Center", "preferences-system-backup", "page:backup", "system",
           "Back up files or restore your computer to an earlier point", [
               T("Back up your files", "kcm:kcm_kup"),
               T("Restore your computer to an earlier time (System Restore)", "app:timeshift-launcher"),
           ], "backup restore system restore snapshot timeshift kup recovery"),
    Applet("system", "System", "computer", "page:sysinfo", "system",
           "View basic information about your computer", [
               T("View amount of RAM and processor speed", "page:sysinfo"),
               T("See the name of this computer", "page:sysinfo"),
               T("Change the computer name", "native:sysprops"),
               T("Device Manager", "app:kinfocenter"),
           ], "system information computer name processor memory ram about"),
    Applet("update", f"{distro.NAME} Update", "system-software-update", "app:plasma-discover --mode Update", "system",
           "Check for and install software and security updates", [
               T("Check for updates", "app:plasma-discover --mode Update"),
               T("Turn automatic updating on or off", "kcm:kcm_updates"),
           ], "windows update updates upgrade patches security"),
    Applet("power", "Power Options", "preferences-system-power-management", "native:power|kcm:kcm_powerdevilprofilesconfig", "system",
           "Conserve energy or maximize performance", [
               T("Change battery settings", "native:power|kcm:kcm_powerdevilprofilesconfig"),
               T("Require a password when the computer wakes", "kcm:kcm_screenlocker"),
               T("Change what the power buttons do", "native:power#buttons|kcm:kcm_powerdevilprofilesconfig"),
               T("Change when the computer sleeps", "native:power|kcm:kcm_powerdevilprofilesconfig"),
           ], "power battery sleep hibernate energy laptop lid"),
    Applet("indexing", "Indexing Options", "preferences-desktop-baloo", "kcm:kcm_baloofile", "system",
           f"Change how {distro.NAME} indexes files for faster searching", [], "search index baloo files"),
    Applet("performance", "Performance Information and Tools", "preferences-system-performance",
           "app:plasma-systemmonitor", "system", "See what is using your computer's resources", [
               T("Open Task Manager", "app:plasma-systemmonitor"),
               T("Free up disk space", "app:filelight"),
           ], "task manager performance cpu memory processes system monitor"),
    Applet("devicemanager", "Device Manager", "preferences-desktop-peripherals", "app:kinfocenter", "system",
           "View hardware and device information", [
               T("View devices and drivers", "app:kinfocenter"),
               T("Find additional drivers", "app:software-properties-qt --open-tab=4"),
           ], "device manager hardware drivers pci usb"),
    Applet("admintools", "Administrative Tools", "preferences-system-services", "page:admintools", "system",
           "Manage your computer's disks, logs, scheduled tasks and services", [
               T("Free up disk space", "app:filelight"),
               T("Manage disks and partitions", "app:partitionmanager"),
               T("Schedule tasks", "kcm:kcm_cron"),
               T("View event logs", "app:ksystemlog"),
           ], "administrative tools admin management"),

    # --- Administrative Tools (page) -------------------------------------------------
    Applet("eventviewer", "Event Viewer", "preferences-log", "app:ksystemlog", "admintools",
           "View system logs and error messages", [], "event viewer logs journal errors"),
    Applet("taskscheduler", "Task Scheduler", "preferences-system-time", "kcm:kcm_cron", "admintools",
           "Run programs automatically at set times", [], "task scheduler cron scheduled tasks"),
    Applet("diskmgmt", "Disk Management", "drive-harddisk", "app:partitionmanager", "admintools",
           "Create, format and resize partitions", [], "disk management partitions format drives"),
    Applet("diskcleanup", "Disk Cleanup", "drive-harddisk", "app:filelight", "admintools",
           "See what is using space on your disks", [], "disk cleanup space usage"),
    Applet("diskhealth", "Disk Health", "preferences-smart-status", "kcm:kcm_disks", "admintools",
           "Monitor your disks for problems (SMART)", [], "disk health smart failure"),
    Applet("taskmanager", "Task Manager", "utilities-system-monitor", "app:plasma-systemmonitor", "admintools",
           "See running programs and resource usage", [], "task manager processes end task"),
    Applet("services", "Background Services", "preferences-system-session-services", "kcm:kcm_kded", "admintools",
           "Turn desktop background services on or off", [], "services background daemons"),
    Applet("startup", "Startup Programs", "preferences-system-startup", "kcm:kcm_autostart", "admintools",
           "Choose which programs start when you log on", [], "startup autostart msconfig"),
    Applet("sysinfo", "System Information", "help-about", "app:kinfocenter", "admintools",
           "Detailed information about your hardware", [], "msinfo system information hardware"),

    # --- Security ----------------------------------------------------------------------
    Applet("firewall", f"{distro.NAME} Firewall", "preferences-security-firewall", "kcm:kcm_firewall", "security",
           "Protect your computer from unwanted network connections", [
               T("Turn the firewall on or off", "kcm:kcm_firewall"),
               T("Allow a program through the firewall", "kcm:kcm_firewall"),
           ], "windows firewall firewall ufw ports"),
    Applet("update-sec", f"{distro.NAME} Update", "system-software-update", "app:plasma-discover --mode Update", "security",
           "Keep your computer up to date", [
               T("Check for updates", "app:plasma-discover --mode Update"),
               T("Turn automatic updating on or off", "kcm:kcm_updates"),
           ], "updates security"),
    Applet("passwords", "Credential Manager", "preferences-desktop-user-password", "app:kwalletmanager5", "security",
           "Manage saved passwords (KDE Wallet)", [
               T("Manage saved passwords", "app:kwalletmanager5"),
               T("Wallet settings", "kcm:kcm_kwallet5"),
           ], "passwords credential manager wallet keyring"),
    Applet("lockscreen", "Screen Lock", "preferences-desktop-screensaver", "kcm:kcm_screenlocker", "security",
           "Require a password after the screen turns off", [], "screen lock screensaver password"),
    Applet("firmware", "Firmware Security", "preferences-security", "kcm:kcm_firmware_security", "security",
           "Check Secure Boot and firmware security", [], "secure boot firmware tpm"),

    # --- Network and Internet ---------------------------------------------------------------
    Applet("netcenter", "Network and Sharing Center", "preferences-system-network-connection",
           "native:network|kcm:kcm_networkmanagement", "network", "Connect to networks and manage connections", [
               T("View network status and tasks", "native:network|kcm:kcm_networkmanagement"),
               T("Manage network connections", "native:network#connections|kcm:kcm_networkmanagement"),
               T("Connect to a network", "kcm:kcm_networkmanagement"),
               T("Set up a mobile hotspot", "kcm:kcm_mobile_hotspot"),
           ], "network wifi wireless ethernet vpn connections"),
    Applet("sharing", "File Sharing", "preferences-system-network-share-windows", "page:sharing", "network",
           "Share folders with other computers on your network", [
               T("Share a folder (right-click it in Dolphin > Properties > Share)", "app:dolphin"),
               T("See who is using your shared folders", "kcm:kcm_samba"),
           ], "file sharing samba smb share folder network windows"),
    Applet("internet", "Internet Options", "preferences-system-network", "kcm:kcm_proxy", "network",
           "Proxy settings and your default web browser", [
               T("Change proxy settings", "kcm:kcm_proxy"),
               T("Change your default web browser", "native:defaults|kcm:kcm_componentchooser"),
               T("Web search shortcuts", "kcm:kcm_webshortcuts"),
           ], "internet options proxy browser"),
    Applet("phone", "Phone and Devices", "preferences-kde-connect", "app:kdeconnect-app", "network",
           "Connect your phone (KDE Connect)", [], "phone android iphone kde connect sms"),

    # --- Hardware and Sound -------------------------------------------------------------------
    Applet("printers", "Printers", "preferences-devices-printer", "kcm:kcm_printer_manager", "hardware",
           "Add, remove and manage printers", [
               T("Add a printer", "kcm:kcm_printer_manager"),
               T("Change default printer", "kcm:kcm_printer_manager"),
           ], "printers printing scanner"),
    Applet("autoplay", "AutoPlay", "preferences-desktop-multimedia", "native:autoplay|kcm:kcm_solid_actions", "hardware",
           "Choose what happens when you insert a disc or USB drive", [
               T("Change default settings for media or devices", "native:autoplay|kcm:kcm_solid_actions"),
               T("Play CDs or other media automatically", "native:autoplay|kcm:kcm_device_automounter"),
           ], "autoplay usb removable cd dvd automount"),
    Applet("sound", "Sound", "preferences-desktop-sound", "native:sound|kcm:kcm_pulseaudio", "hardware",
           "Change speakers, microphones and volume", [
               T("Adjust system volume", "native:sound|kcm:kcm_pulseaudio"),
               T("Change system sounds", "native:sound#sounds|kcm:kcm_soundtheme"),
               T("Manage audio devices", "native:sound|kcm:kcm_pulseaudio"),
           ], "sound audio volume speakers microphone headphones"),
    Applet("mouse", "Mouse", "preferences-desktop-mouse", "native:mouse|kcm:kcm_mouse", "hardware",
           "Change button, pointer and scrolling settings", [
               T("Change mouse settings", "native:mouse|kcm:kcm_mouse"),
               T("Change how the mouse pointer looks", "native:mouse#pointers|kcm:kcm_cursortheme"),
               T("Change the double-click speed", "native:mouse#buttons|kcm:kcm_mouse"),
           ], "mouse pointer cursor double-click scrolling"),
    Applet("touchpad", "Touchpad", "preferences-desktop-touchpad", "kcm:kcm_touchpad", "hardware",
           "Tap-to-click, scrolling and gestures", [], "touchpad trackpad tap"),
    Applet("keyboard", "Keyboard", "preferences-desktop-keyboard", "native:keyboard|kcm:kcm_keyboard", "hardware",
           "Layouts, repeat rate and NumLock", [
               T("Change keyboard layout", "native:keyboard#languages|kcm:kcm_keyboard"),
               T("Change the repeat rate", "native:keyboard#speed|kcm:kcm_keyboard"),
               T("Change keyboard shortcuts", "kcm:kcm_keys"),
           ], "keyboard layout language numlock shortcuts"),
    Applet("display", "Display Settings", "preferences-desktop-display", "native:display|kcm:kcm_kscreen", "hardware",
           "Resolution, scaling, refresh rate and multiple monitors", [
               T("Adjust screen resolution", "native:display|kcm:kcm_kscreen"),
               T("Connect to an external display", "native:display|kcm:kcm_kscreen"),
               T("Make text and other items larger or smaller", "native:display#textsize|kcm:kcm_kscreen"),
               T("Reduce blue light at night", "kcm:kcm_nightlight"),
           ], "display monitor resolution scaling dpi refresh night light"),
    Applet("bluetooth", "Bluetooth Devices", "preferences-system-bluetooth", "kcm:kcm_bluetooth", "hardware",
           "Pair headphones, mice, phones and other devices", [
               T("Add a Bluetooth device", "kcm:kcm_bluetooth"),
           ], "bluetooth pair headphones"),
    Applet("power-hw", "Power Options", "preferences-system-power-management", "native:power|kcm:kcm_powerdevilprofilesconfig",
           "hardware", "Battery and sleep settings", [], "power battery sleep"),
    Applet("gamecontrollers", "Game Controllers", "preferences-desktop-gaming", "kcm:kcm_gamecontroller", "hardware",
           "Test and configure joysticks and gamepads", [], "gamepad joystick controller"),
    Applet("tablet", "Pen and Tablet", "preferences-desktop-tablet", "kcm:kcm_tablet", "hardware",
           "Drawing tablets and pens", [], "tablet pen wacom"),
    Applet("cameras", "Scanners and Cameras", "preferences-devices-scanner", "kcm:kcm_kamera", "hardware",
           "Digital cameras", [], "camera scanner"),
    Applet("thunderbolt", "Thunderbolt", "preferences-desktop-thunderbolt", "kcm:kcm_bolt", "hardware",
           "Authorize Thunderbolt devices", [], "thunderbolt"),
    Applet("devicemanager-hw", "Device Manager", "preferences-desktop-peripherals", "app:kinfocenter", "hardware",
           "View hardware and device information", [
               T("Find additional drivers", "app:software-properties-qt --open-tab=4"),
           ], "device manager drivers"),

    # --- Programs ---------------------------------------------------------------------------------
    Applet("programs", "Programs and Features", "system-software-install",
           "native:programs|app:plasma-discover --mode Installed",
           "programs", "Uninstall or change programs on your computer", [
               T("Uninstall a program", "native:programs|app:plasma-discover --mode Installed"),
               T("View installed updates", "app:plasma-discover --mode Update"),
           ], "programs and features uninstall add remove programs apps installed"),
    Applet("getprograms", "Get Programs", "plasma-discover", "app:plasma-discover", "programs",
           "Find and install new programs", [
               T("Get new programs online", "app:plasma-discover"),
           ], "install software store apps get programs discover"),
    Applet("defaults", "Default Programs", "preferences-desktop-default-applications", "native:defaults|kcm:kcm_componentchooser",
           "programs", f"Choose the programs {distro.NAME} uses by default", [
               T("Set your default programs", "native:defaults|kcm:kcm_componentchooser"),
               T("Always use a specific program to open a file type", "kcm:kcm_filetypes"),
           ], "default programs browser email file associations open with"),
    Applet("startup-prog", "Startup Programs", "preferences-system-startup", "kcm:kcm_autostart", "programs",
           "Choose which programs start when you log on", [], "startup autostart"),
    Applet("permissions", "App Permissions", "preferences-security", "kcm:kcm_flatpak", "programs",
           "Control what Flatpak apps are allowed to do", [], "flatpak permissions sandbox"),
    Applet("wine", "Windows Programs", "wine", "app:winecfg", "programs",
           "Settings for running Windows programs (Wine)", [
               T("Configure Windows program support", "app:winecfg"),
           ], "wine windows exe programs compatibility"),
    Applet("sources", "Software Sources", "system-software-update", "app:software-properties-qt", "programs",
           "Choose where updates and programs come from", [
               T("Find additional drivers", "app:software-properties-qt --open-tab=4"),
           ], "repositories sources ppa drivers"),

    # --- User Accounts --------------------------------------------------------------------------------
    Applet("accounts", "User Accounts", "system-users", "native:useraccounts|kcm:kcm_users", "users",
           "Change your account picture, name and password", [
               T("Change your password", "native:useraccounts#password|kcm:kcm_users"),
               T("Change your picture", "native:useraccounts#picture|kcm:kcm_users"),
               T("Change your account type", "native:useraccounts#type|kcm:kcm_users"),
               T("Add or remove user accounts", "native:useraccounts#manage|kcm:kcm_users"),
           ], "user accounts password picture add user administrator"),
    Applet("logonscreen", "Logon Screen", "preferences-system-login", "kcm:kcm_sddm", "users",
           "Change the logon screen and automatic logon", [
               T("Log on automatically", "kcm:kcm_sddm"),
           ], "login logon screen sddm autologin"),
    Applet("session", "Log On and Log Off", "preferences-system-session-services", "kcm:kcm_smserver", "users",
           "What happens when you log on, log off or shut down", [], "session logoff shutdown restore"),
    Applet("passwords-u", "Credential Manager", "preferences-desktop-user-password", "app:kwalletmanager5", "users",
           "Manage saved passwords", [], "passwords wallet"),

    # --- Appearance and Personalization -------------------------------------------------------------
    Applet("personalization", "Personalization", "preferences-desktop-theme", "page:personalize", "appearance",
           "Change the look of your desktop", [
               T("Change desktop background", "native:background|kcm:kcm_wallpaper"),
               T("Change desktop icons", "native:desktopicons"),
               T("Change window color and glass", "native:windowcolor|kcm:kcm_colors"),
               T("Change the color scheme", "kcm:kcm_colors"),
               T("Change screen saver and lock screen", "kcm:kcm_screenlocker"),
               T("Change sound effects", "kcm:kcm_soundtheme"),
               T("Change mouse pointers", "native:mouse#pointers|kcm:kcm_cursortheme"),
               T("Change the theme", "kcm:kcm_lookandfeel"),
               T("Adjust screen resolution", "native:display|kcm:kcm_kscreen"),
           ], "personalization theme background wallpaper colors"),
    Applet("windowcolor", "Window Color and Appearance", "preferences-desktop-color", "native:windowcolor|kcm:kcm_kwin_effects",
           "appearance", "Glass, transparency and window effects", [
               T("Change the color of windows", "native:windowcolor|kcm:kcm_colors"),
               T("Change window effects", "kcm:kcm_kwin_effects"),
               T("Change window borders and buttons", "kcm:kcm_kwindecoration"),
               T("Change application style", "kcm:kcm_style"),
           ], "aero glass transparency window color effects"),
    Applet("fonts", "Fonts", "preferences-desktop-font", "kcm:kcm_fontinst", "appearance",
           "Install, remove and preview fonts", [
               T("Install or remove a font", "kcm:kcm_fontinst"),
               T("Change font size and smoothing", "kcm:kcm_fonts"),
           ], "fonts font size cleartype"),
    Applet("icons", "Icons", "preferences-desktop-icons", "kcm:kcm_icons", "appearance",
           "Change the icon theme", [], "icons"),
    Applet("folderoptions", "Folder Options", "folder", "native:folderoptions|kcm:kcm_desktoppaths", "appearance",
           "Hidden files, single or double click, and how folders look", [
               T("Show hidden files and folders", "native:folderoptions#view|app:dolphin"),
               T("Specify single- or double-click to open", "native:folderoptions#general|kcm:kcm_workspace"),
               T("Change where personal folders are stored", "kcm:kcm_desktoppaths"),
               T("Show recent files", "kcm:kcm_recentFiles"),
           ], "folder options documents pictures downloads explorer"),
    Applet("startmenu", "Taskbar and Start Menu", "preferences-desktop-plasma", "kcm:kcm_workspace", "appearance",
           "Clicking, tooltips and desktop behavior", [
               T("Customize the taskbar (right-click it > Edit Panel)", "kcm:kcm_workspace"),
               T("Customize icons on the taskbar", "native:notifyicons|kcm:kcm_notifications"),
           ], "taskbar start menu panel notification area"),
    Applet("notifyicons", "Notification Area Icons", "preferences-desktop-notification", "native:notifyicons",
           "appearance", "Choose which icons appear next to the clock", [
               T("Hide inactive icons", "native:notifyicons"),
               T("Turn system icons on or off", "native:notifyicons"),
           ], "tray notification area icons system tray hide show volume network power battery"),
    Applet("bootscreen", "Startup Screen", "preferences-system-splash", "kcm:kcm_plymouth", "appearance",
           "Change the boot and loading screens", [
               T("Change the boot screen", "kcm:kcm_plymouth"),
               T("Change the loading screen after logon", "kcm:kcm_splashscreen"),
           ], "boot splash plymouth startup"),
    Applet("animations", "Animations", "preferences-desktop-effects", "kcm:kcm_animations", "appearance",
           "Speed and style of animations", [], "animations speed"),

    # --- Personalization (Vista's hub page) --------------------------------------------------------------
    Applet("p-windowcolor", "Window Color and Appearance", "preferences-desktop-color",
           "native:windowcolor|kcm:kcm_colors", "personalize",
           "Fine tune the color and style of your windows."),
    Applet("p-background", "Desktop Background", "preferences-desktop-wallpaper",
           "native:background|kcm:kcm_wallpaper", "personalize",
           "Choose from available backgrounds or colors, or use one of your own pictures to decorate the desktop."),
    Applet("p-screensaver", "Screen Saver", "preferences-desktop-screensaver",
           "native:screensaver|kcm:kcm_screenlocker", "personalize",
           "Choose when your screen locks and what it shows. A screen saver also protects your privacy."),
    Applet("p-sounds", "Sounds", "preferences-desktop-sound", "native:sound#sounds|kcm:kcm_soundtheme", "personalize",
           "Change which sounds are heard when you do everything from getting e-mail to emptying your Recycle Bin."),
    Applet("p-pointers", "Mouse Pointers", "preferences-desktop-cursors", "native:mouse#pointers|kcm:kcm_cursortheme",
           "personalize", "Pick a different mouse pointer. You can also change how the mouse pointer looks."),
    Applet("p-theme", "Theme", "preferences-desktop-theme-global", "kcm:kcm_lookandfeel", "personalize",
           "Change the theme. Themes can change a wide range of visual and auditory elements at one time."),
    Applet("p-display", "Display Settings", "preferences-desktop-display", "native:display|kcm:kcm_kscreen",
           "personalize", "Adjust your monitor resolution, which changes the view so more or fewer items fit on the screen."),

    # --- Clock, Language, and Region -------------------------------------------------------------------
    Applet("datetime", "Date and Time", "preferences-system-time", "native:datetime|kcm:kcm_clock", "clock",
           "Set the date, time and time zone", [
               T("Set the time and date", "native:datetime|kcm:kcm_clock"),
               T("Change the time zone", "native:datetime|kcm:kcm_clock"),
               T("Synchronize with an Internet time server", "native:datetime#internettime|kcm:kcm_clock"),
           ], "date time clock time zone ntp"),
    Applet("region", "Regional and Language Options", "preferences-desktop-locale", "native:region|kcm:kcm_regionandlang",
           "clock", "Language, number, currency and date formats", [
               T("Change display language", "native:region#languages|kcm:kcm_regionandlang"),
               T("Change the format of dates and numbers", "native:region#formats|kcm:kcm_regionandlang"),
               T("Change keyboards or other input methods", "native:keyboard#languages|kcm:kcm_keyboard"),
           ], "language region locale formats currency"),
    Applet("spelling", "Spell Checking", "tools-check-spelling", "kcm:kcmspellchecking", "clock",
           "Dictionaries and spell checking", [], "spelling dictionary"),

    # --- Ease of Access ------------------------------------------------------------------------------------
    Applet("easeofaccess", "Ease of Access Center", "preferences-desktop-accessibility", "kcm:kcm_access", "access",
           "Make your computer easier to see, hear and use", [
               T("Optimize visual display", "kcm:kcm_access"),
               T("Use the on-screen keyboard", "kcm:kcm_virtualkeyboard"),
               T("Make the mouse easier to use", "kcm:kcm_access"),
           ], "accessibility ease of access magnifier sticky keys screen reader"),
    Applet("screenedges", "Screen Edges and Corners", "preferences-desktop-gestures-screenedges",
           "kcm:kcm_kwinscreenedges", "access", "Actions when the mouse touches a screen edge", [], "hot corners edges"),
    Applet("speech", "Text to Speech", "preferences-desktop-text-to-speech", "app:jovie", "access",
           "Read text aloud", [], "speech narrator"),

    # --- Additional Options ------------------------------------------------------------------------------------
    Applet("allsettings", "All Settings", "preferences-system", "app:systemsettings", "other",
           "Every setting, in System Settings", [], "system settings all"),
    Applet("notifications", "Notifications", "preferences-desktop-notification", "kcm:kcm_notifications", "other",
           "Choose which notifications you see", [], "notifications action center"),
    Applet("shortcuts", "Keyboard Shortcuts", "preferences-desktop-keyboard-shortcuts", "kcm:kcm_keys", "other",
           "Change keyboard shortcuts", [], "shortcuts hotkeys"),
    Applet("windows", "Window Behavior", "preferences-system-windows-actions", "kcm:kcm_kwinoptions", "other",
           "Focus, snapping and title bar actions", [
               T("Window snapping and title bar actions", "kcm:kcm_kwinoptions"),
               T("Alt+Tab switcher", "kcm:kcm_kwintabbox"),
               T("Rules for specific windows", "kcm:kcm_kwinrules"),
           ], "windows snap focus alt tab"),
    Applet("desktops", "Virtual Desktops", "preferences-desktop", "kcm:kcm_kwin_virtualdesktops", "other",
           "Use several desktops", [], "virtual desktops workspaces"),
    Applet("search", "Search", "preferences-desktop-search", "kcm:kcm_plasmasearch", "other",
           "Start menu search settings", [], "search krunner"),
    Applet("feedback", "Feedback", "preferences-desktop-feedback", "kcm:kcm_feedback", "other",
           "Usage statistics sent to KDE", [], "feedback telemetry privacy"),
]

# Applets that appear in more than one category share a name; Classic View shows each
# name once.
CLASSIC_EXCLUDE = {"update-sec", "power-hw", "devicemanager-hw", "startup-prog", "passwords-u",
                   "diskcleanup", "taskmanager", "startup", "sysinfo",
                   "p-windowcolor", "p-screensaver", "p-sounds", "p-pointers", "p-theme", "p-display"}

# Extra pages (Vista shows these as task pages): id -> (title, icon, text, tasks).
PAGES = {
    "backup": ("Backup and Restore Center", "preferences-system-backup",
               "Protect your files and your computer by making backups.", [
                   T("Back up files (choose folders, schedule, destination)", "kcm:kcm_kup"),
                   T("Restore files from a backup", "kcm:kcm_kup"),
                   T("Create a restore point (System Restore)", "app:timeshift-launcher"),
                   T("Restore your computer to an earlier time", "app:timeshift-launcher"),
               ]),
    "sharing": ("File Sharing", "preferences-system-network-share-windows",
                "To share a folder with Windows PCs on your network, right-click it in Dolphin, "
                "choose Properties, then the Share tab.", [
                    T("Open Dolphin", "app:dolphin"),
                    T("See who is using your shared folders", "kcm:kcm_samba"),
                    T("Network connections", "kcm:kcm_networkmanagement"),
                ]),
}


def merge_extensions(modules):
    """Merge catalog entries from extension modules (see applets/__init__.py):
    new categories go before "Additional Options"; an applet with an existing id
    replaces the built-in one; PAGES are added/overridden. Entries of the wrong type are
    skipped, so a broken extension can't stop the Control Panel from starting."""
    for m in modules:
        for c in getattr(m, "CATEGORIES", []):
            if not isinstance(c, Category) or any(x.id == c.id for x in CATEGORIES):
                continue
            pos = next((i for i, x in enumerate(CATEGORIES) if x.id == "other"), len(CATEGORIES))
            CATEGORIES.insert(pos, c)
        for a in getattr(m, "APPLETS", []):
            if not isinstance(a, Applet):
                continue
            i = next((i for i, x in enumerate(APPLETS) if x.id == a.id), None)
            if i is None:
                APPLETS.append(a)
            else:
                APPLETS[i] = a
        pages = getattr(m, "PAGES", {})
        if isinstance(pages, dict):
            PAGES.update(pages)
