import os, re, json, hashlib, shutil, threading, subprocess, ctypes, uuid
import tkinter as tk
from tkinter import messagebox, filedialog
import minecraft_launcher_lib as mll

APP_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "RedLauncher")
CONFIG_FILE = os.path.join(APP_DIR, "config.json")
ACCOUNTS_FILE = os.path.join(APP_DIR, "profiles.json")
DEFAULT_ROOT = os.path.join(APP_DIR, "game")
DEFAULT_VERSION = "1.21.4"

BG = "#0b0b0b"
SIDE = "#121212"
PANEL = "#171717"
FIELD = "#0f0f0f"
RED = "#d81e2b"
RED_DARK = "#7a0f17"
TEXT = "#f2f2f2"
GREY = "#7a7a7a"
FONT = "Segoe UI"


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def total_ram_mb():
    try:
        class MEMSTAT(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MEMSTAT()
        m.dwLength = ctypes.sizeof(MEMSTAT)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return int(m.ullTotalPhys // (1024 * 1024))
    except Exception:
        return 8192


def hash_password(password, salt=None):
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()
    return salt, digest


def open_folder(path):
    os.makedirs(path, exist_ok=True)
    try:
        os.startfile(path)
    except Exception:
        pass


def make_button(parent, text, cmd, color=RED, hover=RED_DARK, big=False):
    padx, pady = (60, 12) if big else (14, 7)
    font = (FONT, 14 if big else 10, "bold")
    b = tk.Button(parent, text=text, command=cmd, bg=color, fg=TEXT,
                  activebackground=hover, activeforeground=TEXT, relief="flat", bd=0,
                  font=font, padx=padx, pady=pady, cursor="hand2")
    b.bind("<Enter>", lambda e: b.config(bg=hover))
    b.bind("<Leave>", lambda e: b.config(bg=color))
    return b


class Field(tk.Frame):
    """Поле ввода с красной рамкой, которая становится ярче при фокусе."""
    def __init__(self, parent, width=30, show=None, text=""):
        super().__init__(parent, bg=RED_DARK, padx=2, pady=2)
        self.entry = tk.Entry(self, bg=FIELD, fg=TEXT, insertbackground=RED, relief="flat",
                              font=(FONT, 11), width=width, show=show or "")
        self.entry.pack(fill="x", ipady=6)
        if text:
            self.entry.insert(0, text)
        self.entry.bind("<FocusIn>", lambda e: self.config(bg=RED))
        self.entry.bind("<FocusOut>", lambda e: self.config(bg=RED_DARK))

    def get(self):
        return self.entry.get().strip()

    def raw(self):
        return self.entry.get()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("RED LAUNCHER")
        self.geometry("900x580")
        self.minsize(900, 580)
        self.configure(bg=BG)

        self.settings = load_json(CONFIG_FILE, {})
        self.settings.setdefault("root", DEFAULT_ROOT)
        self.settings.setdefault("version", DEFAULT_VERSION)
        self.settings.setdefault("ram", 4096)
        self.settings.setdefault("snapshots", False)
        self.settings.setdefault("account", None)
        self.accounts = load_json(ACCOUNTS_FILE, [])

        self.ram_var = tk.IntVar(value=self.settings["ram"])
        self.version_cache = None
        self.visible_versions = []

        self.build_layout()
        self.show_page("play")

    # ---------- общие части ----------
    def build_layout(self):
        side = tk.Frame(self, bg=SIDE, width=200)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        tk.Label(side, text="RED", bg=SIDE, fg=RED, font=(FONT, 26, "bold")).pack(pady=(30, 0))
        tk.Label(side, text="LAUNCHER", bg=SIDE, fg=TEXT, font=(FONT, 10, "bold")).pack(pady=(0, 30))

        self.nav = {}
        items = [("play", "Главная"), ("accounts", "Аккаунты"), ("versions", "Версии"),
                 ("mods", "Моды"), ("settings", "Настройки")]
        for key, title in items:
            b = tk.Button(side, text=title, anchor="w", padx=24, pady=10, bg=SIDE, fg=TEXT,
                          activebackground=RED_DARK, activeforeground=TEXT, relief="flat", bd=0,
                          font=(FONT, 11), cursor="hand2",
                          command=lambda k=key: self.show_page(k))
            b.pack(fill="x")
            self.nav[key] = b

        self.content = tk.Frame(self, bg=BG)
        self.content.pack(side="left", fill="both", expand=True, padx=30, pady=25)

    def show_page(self, key):
        for k, b in self.nav.items():
            b.config(bg=RED_DARK if k == key else SIDE)
        for w in self.content.winfo_children():
            w.destroy()
        pages = {"play": self.page_play, "accounts": self.page_accounts,
                 "versions": self.page_versions, "mods": self.page_mods,
                 "settings": self.page_settings}
        pages[key]()

    def header(self, text):
        tk.Label(self.content, text=text, bg=BG, fg=RED, font=(FONT, 22, "bold")).pack(anchor="w", pady=(0, 15))

    def card(self):
        f = tk.Frame(self.content, bg=PANEL, padx=20, pady=14)
        f.pack(fill="x", pady=6)
        return f

    def info_row(self, title, value, button_text=None, cmd=None):
        f = self.card()
        left = tk.Frame(f, bg=PANEL)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text=title, bg=PANEL, fg=GREY, font=(FONT, 9)).pack(anchor="w")
        tk.Label(left, text=value, bg=PANEL, fg=TEXT, font=(FONT, 12, "bold")).pack(anchor="w")
        if button_text:
            make_button(f, button_text, cmd, color=RED_DARK, hover=RED).pack(side="right")
        return f

    def save_settings(self):
        self.settings["ram"] = self.ram_var.get()
        save_json(CONFIG_FILE, self.settings)

    def current_account(self):
        return next((a for a in self.accounts if a["name"] == self.settings.get("account")), None)

    # ---------- Главная ----------
    def page_play(self):
        self.header("Главная")
        acc = self.current_account()
        self.info_row("Аккаунт", acc["name"] if acc else "не выбран",
                      "Сменить", lambda: self.show_page("accounts"))
        self.info_row("Версия игры", self.settings["version"],
                      "Выбрать", lambda: self.show_page("versions"))
        self.info_row("Корневая папка", self.settings["root"],
                      "Открыть", lambda: open_folder(self.settings["root"]))

        c = self.card()
        tk.Label(c, text="Оперативная память", bg=PANEL, fg=GREY, font=(FONT, 9)).pack(anchor="w")
        self.ram_label = tk.Label(c, text="", bg=PANEL, fg=RED, font=(FONT, 12, "bold"))
        self.ram_label.pack(anchor="w")
        max_ram = max(2048, total_ram_mb() - 1024)
        scale = tk.Scale(c, from_=1024, to=max_ram, resolution=512, orient="horizontal",
                         variable=self.ram_var, bg=PANEL, fg=TEXT, troughcolor=FIELD,
                         activebackground=RED, highlightthickness=0, showvalue=False, length=560,
                         command=lambda v: self.update_ram_label())
        scale.pack(anchor="w", pady=5)
        self.update_ram_label()

        self.status = tk.Label(self.content, text="Готов", bg=BG, fg=GREY, font=(FONT, 10))
        self.status.pack(anchor="w", pady=(12, 8))
        make_button(self.content, "ЗАПУСТИТЬ", self.start_game, big=True).pack(anchor="w")

    def update_ram_label(self):
        if hasattr(self, "ram_label"):
            try:
                self.ram_label.config(text=f"{self.ram_var.get() / 1024:g} ГБ")
            except tk.TclError:
                pass

    # ---------- Аккаунты ----------
    def page_accounts(self):
        self.header("Аккаунты")
        if not self.accounts:
            tk.Label(self.content, text="Аккаунтов пока нет. Создай первый ниже.",
                     bg=BG, fg=GREY, font=(FONT, 10)).pack(anchor="w", pady=(0, 6))
        for acc in self.accounts:
            c = self.card()
            is_cur = acc["name"] == self.settings.get("account")
            left = tk.Frame(c, bg=PANEL)
            left.pack(side="left", fill="x", expand=True)
            tk.Label(left, text=acc["name"] + ("   ● выбран" if is_cur else ""),
                     bg=PANEL, fg=RED if is_cur else TEXT, font=(FONT, 12, "bold")).pack(anchor="w")
            tk.Label(left, text="с паролем" if acc.get("password_hash") else "без пароля",
                     bg=PANEL, fg=GREY, font=(FONT, 9)).pack(anchor="w")
            make_button(c, "Удалить", lambda n=acc["name"]: self.delete_account(n),
                        color=FIELD, hover=RED_DARK).pack(side="right", padx=(8, 0))
            if not is_cur:
                make_button(c, "Выбрать", lambda n=acc["name"]: self.select_account(n),
                            color=RED_DARK, hover=RED).pack(side="right")

        form = self.card()
        tk.Label(form, text="Новый аккаунт", bg=PANEL, fg=TEXT, font=(FONT, 12, "bold")).pack(anchor="w")
        tk.Label(form, text="Имя: 1–16 символов, латиница, цифры и _", bg=PANEL, fg=GREY,
                 font=(FONT, 9)).pack(anchor="w", pady=(8, 2))
        self.name_field = Field(form, width=40)
        self.name_field.pack(fill="x")
        tk.Label(form, text="Пароль для входа в лаунчер (необязательно)", bg=PANEL, fg=GREY,
                 font=(FONT, 9)).pack(anchor="w", pady=(8, 2))
        self.pass_field = Field(form, width=40, show="*")
        self.pass_field.pack(fill="x")
        make_button(form, "Добавить аккаунт", self.add_account).pack(anchor="w", pady=(12, 0))

    def add_account(self):
        name = self.name_field.get()
        if not re.fullmatch(r"[A-Za-z0-9_]{1,16}", name):
            return messagebox.showwarning("Ошибка", "Имя: 1–16 символов, только латиница, цифры и _")
        if any(a["name"].lower() == name.lower() for a in self.accounts):
            return messagebox.showwarning("Ошибка", "Аккаунт с таким именем уже есть")
        acc = {"name": name, "uuid": str(uuid.uuid4())}
        pwd = self.pass_field.raw()
        if pwd:
            acc["salt"], acc["password_hash"] = hash_password(pwd)
        self.accounts.append(acc)
        save_json(ACCOUNTS_FILE, self.accounts)
        if not self.current_account():
            self.settings["account"] = name
            self.save_settings()
        self.show_page("accounts")

    def ask_password(self, name):
        win = tk.Toplevel(self, bg=PANEL)
        win.title("Вход")
        win.geometry("340x200")
        win.resizable(False, False)
        win.transient(self)
        win.grab_set()
        result = {"value": None}
        tk.Label(win, text=f"Пароль для {name}", bg=PANEL, fg=TEXT,
                 font=(FONT, 11, "bold")).pack(pady=(25, 10))
        field = Field(win, width=28, show="*")
        field.pack(padx=25, fill="x")
        field.entry.focus_set()

        def ok(_=None):
            result["value"] = field.raw()
            win.destroy()
        field.entry.bind("<Return>", ok)
        make_button(win, "ОК", ok).pack(pady=15)
        self.wait_window(win)
        return result["value"]

    def select_account(self, name):
        acc = next(a for a in self.accounts if a["name"] == name)
        if acc.get("password_hash"):
            pwd = self.ask_password(name)
            if pwd is None:
                return
            _, digest = hash_password(pwd, acc["salt"])
            if digest != acc["password_hash"]:
                return messagebox.showerror("Ошибка", "Неверный пароль")
        self.settings["account"] = name
        self.save_settings()
        self.show_page("accounts")

    def delete_account(self, name):
        if not messagebox.askyesno("Удаление", f"Удалить аккаунт {name}?"):
            return
        self.accounts = [a for a in self.accounts if a["name"] != name]
        save_json(ACCOUNTS_FILE, self.accounts)
        if self.settings.get("account") == name:
            self.settings["account"] = None
            self.save_settings()
        self.show_page("accounts")

    # ---------- Версии ----------
    def page_versions(self):
        self.header("Версии Minecraft")
        top = self.card()
        tk.Label(top, text=f"Выбрано: {self.settings['version']}", bg=PANEL, fg=TEXT,
                 font=(FONT, 12, "bold")).pack(side="left")
        self.snap_var = tk.BooleanVar(value=self.settings["snapshots"])
        tk.Checkbutton(top, text="Снапшоты", variable=self.snap_var, command=self.on_snapshots_toggle,
                       bg=PANEL, fg=TEXT, selectcolor=FIELD, activebackground=PANEL,
                       activeforeground=TEXT, highlightthickness=0).pack(side="right")

        self.version_status = tk.Label(self.content, text="", bg=BG, fg=GREY, font=(FONT, 9))
        self.version_status.pack(anchor="w")
        self.version_list = tk.Listbox(self.content, bg=FIELD, fg=TEXT, selectbackground=RED,
                                       selectforeground=TEXT, relief="flat", font=(FONT, 11),
                                       highlightthickness=0, activestyle="none", height=10)
        self.version_list.pack(fill="both", expand=True, pady=6)
        make_button(self.content, "Выбрать версию", self.choose_version).pack(anchor="w")

        if self.version_cache is None:
            self.load_versions()
        else:
            self.fill_versions()

    def load_versions(self):
        self.version_status.config(text="Загрузка списка версий...")

        def work():
            try:
                versions = mll.utils.get_version_list()
                self.after(0, lambda: self.on_versions_loaded(versions))
            except Exception as e:
                self.after(0, lambda: self.set_version_status(f"Не удалось загрузить список: {e}"))
        threading.Thread(target=work, daemon=True).start()

    def set_version_status(self, text):
        try:
            self.version_status.config(text=text)
        except Exception:
            pass

    def on_versions_loaded(self, versions):
        self.version_cache = versions
        self.fill_versions()

    def fill_versions(self):
        show_snap = self.settings["snapshots"]
        allowed = {"release", "snapshot"} if show_snap else {"release"}
        self.visible_versions = [v["id"] for v in self.version_cache if v["type"] in allowed]
        try:
            self.version_list.delete(0, "end")
            for vid in self.visible_versions:
                self.version_list.insert("end", vid)
            if self.settings["version"] in self.visible_versions:
                idx = self.visible_versions.index(self.settings["version"])
                self.version_list.selection_set(idx)
                self.version_list.see(idx)
            self.version_status.config(text=f"Доступно версий: {len(self.visible_versions)}")
        except tk.TclError:
            pass

    def on_snapshots_toggle(self):
        self.settings["snapshots"] = self.snap_var.get()
        save_json(CONFIG_FILE, self.settings)
        if self.version_cache is not None:
            self.fill_versions()

    def choose_version(self):
        sel = self.version_list.curselection()
        if not sel:
            return messagebox.showwarning("Ошибка", "Выбери версию в списке")
        self.settings["version"] = self.visible_versions[sel[0]]
        self.save_settings()
        self.show_page("play")

    # ---------- Моды ----------
    def mod_dirs(self):
        root = self.settings["root"]
        return os.path.join(root, "mods"), os.path.join(root, "mods_disabled")

    def page_mods(self):
        self.header("Моды")
        tk.Label(self.content, text="Для модов нужен загрузчик Fabric или Forge под выбранную версию игры.",
                 bg=BG, fg=GREY, font=(FONT, 10)).pack(anchor="w", pady=(0, 10))
        mods_dir, dis_dir = self.mod_dirs()
        os.makedirs(mods_dir, exist_ok=True)
        os.makedirs(dis_dir, exist_ok=True)

        box = tk.Frame(self.content, bg=PANEL, padx=18, pady=12)
        box.pack(fill="both", expand=True)
        jars = []
        for folder, enabled in [(mods_dir, True), (dis_dir, False)]:
            for f in sorted(os.listdir(folder)):
                if f.lower().endswith(".jar"):
                    jars.append((f, enabled))
        if not jars:
            tk.Label(box, text="Модов нет. Добавь .jar файл кнопкой ниже.",
                     bg=PANEL, fg=GREY).pack(anchor="w")
        for name, enabled in jars:
            var = tk.BooleanVar(value=enabled)
            tk.Checkbutton(box, text=name, variable=var,
                           command=lambda n=name, v=var: self.toggle_mod(n, v.get()),
                           bg=PANEL, fg=TEXT, selectcolor=FIELD, activebackground=PANEL,
                           activeforeground=TEXT, highlightthickness=0, anchor="w").pack(anchor="w", pady=2)

        row = tk.Frame(self.content, bg=BG)
        row.pack(anchor="w", pady=12)
        make_button(row, "Добавить мод (.jar)", self.add_mod).pack(side="left", padx=(0, 8))
        make_button(row, "Открыть папку модов", lambda: open_folder(mods_dir),
                    color=PANEL, hover=RED_DARK).pack(side="left")

    def toggle_mod(self, name, enabled):
        mods_dir, dis_dir = self.mod_dirs()
        src, dst = (dis_dir, mods_dir) if enabled else (mods_dir, dis_dir)
        try:
            shutil.move(os.path.join(src, name), os.path.join(dst, name))
        except OSError as e:
            messagebox.showerror("Ошибка", str(e))
            self.show_page("mods")

    def add_mod(self):
        path = filedialog.askopenfilename(filetypes=[("Mod", "*.jar")])
        if not path:
            return
        mods_dir, _ = self.mod_dirs()
        os.makedirs(mods_dir, exist_ok=True)
        shutil.copy(path, os.path.join(mods_dir, os.path.basename(path)))
        self.show_page("mods")

    # ---------- Настройки ----------
    def page_settings(self):
        self.header("Настройки")
        self.info_row("Корневая папка игры", self.settings["root"],
                      "Изменить", self.change_root)
        self.info_row("Сбросить папку", f"вернуть {DEFAULT_ROOT}",
                      "Сбросить", self.reset_root)
        self.info_row("Папка лаунчера", "аккаунты и конфиг",
                      "Открыть", lambda: open_folder(APP_DIR))

    def change_root(self):
        path = filedialog.askdirectory()
        if path:
            self.settings["root"] = os.path.normpath(path)
            self.save_settings()
            self.show_page("settings")

    def reset_root(self):
        self.settings["root"] = DEFAULT_ROOT
        self.save_settings()
        self.show_page("settings")

    # ---------- Запуск ----------
    def set_status(self, text):
        def upd():
            try:
                self.status.config(text=text)
            except Exception:
                pass
        self.after(0, upd)

    def start_game(self):
        acc = self.current_account()
        if not acc:
            messagebox.showwarning("Нет аккаунта", "Сначала выбери аккаунт")
            return self.show_page("accounts")
        self.save_settings()
        threading.Thread(target=self._launch,
                         args=(acc, self.settings["root"], self.settings["version"], self.ram_var.get()),
                         daemon=True).start()

    def _launch(self, acc, root, version, ram):
        try:
            os.makedirs(root, exist_ok=True)
            installed = [v["id"] for v in mll.utils.get_installed_versions(root)]
            if version not in installed:
                self.set_status(f"Загрузка Minecraft {version}...")
                mll.install.install_minecraft_version(version, root, callback={
                    "setStatus": self.set_status,
                    "setProgress": lambda v: None,
                    "setMax": lambda v: None,
                })
            options = {
                "username": acc["name"],
                "uuid": acc["uuid"],
                "token": "",
                "jvmArguments": [f"-Xmx{ram}M", f"-Xms{min(ram, 1024)}M"],
                "gameDirectory": root,
            }
            self.set_status("Запуск игры...")
            command = mll.command.get_minecraft_command(version, root, options)
            subprocess.Popen(command, cwd=root)
            self.set_status(f"Minecraft {version} запущен")
        except Exception as e:
            self.set_status("Ошибка запуска")
            msg = str(e)
            self.after(0, lambda: messagebox.showerror("Ошибка", msg))


if __name__ == "__main__":
    App().mainloop()
