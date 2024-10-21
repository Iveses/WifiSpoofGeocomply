import customtkinter as ctk
import paramiko
import os
import json
import random
import threading
import time
import re
from faker import Faker

# Paths and data
WIRELESS_PATH = "/etc/config/wireless"
SETTINGS_FILE = os.path.join(os.path.expanduser("~"), "AppData", "Local", "RouterConf", "router_settings.json")
fake = Faker()

# CustomTkinter settings
ctk.set_appearance_mode("dark")  # Темный режим
ctk.set_default_color_theme("blue")  # Синяя тема


def save_settings(router_ip, login, password):
    """Сохраняем данные роутера в файл JSON."""
    # Получаем путь к директории
    settings_dir = os.path.dirname(SETTINGS_FILE)

    # Проверяем, существует ли директория, и создаем её, если нет
    if not os.path.exists(settings_dir):
        os.makedirs(settings_dir)

    # Сохраняем настройки в файл
    with open(SETTINGS_FILE, "w") as file:
        json.dump({"ip": router_ip, "login": login, "password": password}, file)



def load_settings():
    """Загружаем данные роутера из файла JSON."""
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as file:
            return json.load(file)
    return None


def generate_random_bssid():
    """Генерируем случайный BSSID."""
    first_byte = random.randint(1, 255) & 0xfe
    mac_address = [first_byte] + [random.randint(0x00, 0xff) for _ in range(5)]
    return ':'.join(['%02X' % x for x in mac_address])


def generate_random_word():
    """Генерация случайного слова для SSID."""
    return fake.word()


def ssh_connect(router_ip, login, password):
    """Устанавливаем SSH-подключение через paramiko."""
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # Автоматическое принятие ключей хоста
    ssh.connect(router_ip, username=login, password=password, timeout=10)
    return ssh


def check_connection(router_ip, login, password):
    """Проверяем подключение к роутеру через SSH."""
    try:
        ssh = ssh_connect(router_ip, login, password)
        stdin, stdout, stderr = ssh.exec_command("echo 'Connection successful'")
        output = stdout.read().decode()
        ssh.close()
        return "Connection successful" in output
    except Exception:
        return False


def configure_router(bssid_list, router_ip, login, password):
    """Настраиваем роутер с новым списком BSSID через SSH."""
    try:
        ssh = ssh_connect(router_ip, login, password)

        # Удаляем существующие wifi-iface
        delete_command = f"sed -i '/config \'wifi-iface\'/,$d' {WIRELESS_PATH}"
        ssh.exec_command(delete_command)

        total_points = len(bssid_list)
        half = total_points // 2
        if total_points % 2 != 0:
            half += random.choice([0, 1])

        for i, bssid in enumerate(bssid_list):
            ssid = generate_random_word()
            device = 'radio0' if i < half else 'radio1'
            command = (
                f"uci set wireless.wifinet{i}=wifi-iface && "
                f"uci set wireless.wifinet{i}.device='{device}' && "
                f"uci set wireless.wifinet{i}.mode='ap' && "
                f"uci set wireless.wifinet{i}.ssid='{ssid}' && "
                f"uci set wireless.wifinet{i}.encryption='psk2' && "
                f"uci set wireless.wifinet{i}.key='11111111' && "
                f"uci set wireless.wifinet{i}.macaddr='{bssid}' && "
                f"uci set wireless.wifinet{i}.network='lan'"
            )
            ssh.exec_command(command)

        # Коммитим изменения и перезапускаем WiFi
        commit_command = "uci commit wireless; wifi"
        ssh.exec_command(commit_command)
        ssh.close()

        return f"Успешно настроен роутер с {total_points} BSSID(s)."
    except Exception as e:
        return f"Ошибка настройки роутера: {str(e)}"


def fetch_current_networks(router_ip, login, password):
    """Получаем текущие сети Wi-Fi с роутера через SSH."""
    try:
        ssh = ssh_connect(router_ip, login, password)
        command = f"cat {WIRELESS_PATH}"
        stdin, stdout, stderr = ssh.exec_command(command)
        output = stdout.read().decode()
        ssh.close()

        networks = []
        for line in output.splitlines():
            if "option macaddr" in line:
                bssid = line.split("'")[1]
                networks.append(bssid)
        return networks
    except Exception as e:
        return [f"Ошибка получения сетей: {str(e)}"]


def validate_bssid(bssid_list):
    """Проверяем корректность введённых BSSID."""
    bssid_pattern = re.compile(r'^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$')
    invalid_bssids = [bssid for bssid in bssid_list if not bssid_pattern.match(bssid.strip())]
    return invalid_bssids


def show_settings_interface(root, router_ip, login, password):
    """Интерфейс для настройки роутера."""
    for widget in root.winfo_children():
        widget.destroy()

    ip_label = ctk.CTkLabel(root, text="Router IP:")
    ip_label.pack(pady=10)
    ip_entry = ctk.CTkEntry(root)
    ip_entry.pack(pady=5)
    ip_entry.insert(0, router_ip)

    login_label = ctk.CTkLabel(root, text="Login:")
    login_label.pack(pady=10)
    login_entry = ctk.CTkEntry(root)
    login_entry.pack(pady=5)
    login_entry.insert(0, login)

    password_label = ctk.CTkLabel(root, text="Password:")
    password_label.pack(pady=10)
    password_entry = ctk.CTkEntry(root, show="*")
    password_entry.pack(pady=5)
    password_entry.insert(0, password)

    status_label = ctk.CTkLabel(root, text="")
    status_label.pack(pady=10)

    def save_and_close():
        new_ip = ip_entry.get()
        new_login = login_entry.get()
        new_password = password_entry.get()

        status_label.configure(text="Проверка подключения...")
        root.update()

        if check_connection(new_ip, new_login, new_password):
            save_settings(new_ip, new_login, new_password)
            status_label.configure(text="Подключение успешно. Настройки сохранены.")
            root.after(2000, lambda: show_main_interface(root, new_ip, new_login, new_password))
        else:
            status_label.configure(text="Ошибка подключения. Проверьте данные.")

    save_button = ctk.CTkButton(root, text="Save", command=save_and_close)
    save_button.pack(pady=20)

    back_button = ctk.CTkButton(root, text="Back",
                                command=lambda: show_main_interface(root, router_ip, login, password))
    back_button.pack(pady=10)


def show_main_interface(root, router_ip, login, password):
    """Основной интерфейс приложения после ввода данных."""
    for widget in root.winfo_children():
        widget.destroy()

    network_info_label = ctk.CTkLabel(root, text="Текущее количество сетей: 0\nBSSID:", justify="left")
    network_info_label.pack(pady=10)

    update_thread = None
    update_running = True

    def update_network_info():
        """Обновляем информацию о текущих сетях каждые 5 секунд."""
        while update_running:
            networks = fetch_current_networks(router_ip, login, password)
            network_text = f"Current number of networks: {len(networks)}\nBSSID:\n" + "\n".join(networks)

            if network_info_label.winfo_exists():
                root.after(0, lambda text=network_text: network_info_label.configure(text=text))
            time.sleep(5)

    def start_update_thread():
        nonlocal update_thread
        update_thread = threading.Thread(target=update_network_info, daemon=True)
        update_thread.start()

    start_update_thread()

    mode_var = ctk.StringVar(value="manual")

    # Frame для "Ввести BSSID вручную" и поле ввода
    manual_frame = ctk.CTkFrame(root)
    manual_frame.pack(pady=10, fill="x", padx=10)
    manual_radio = ctk.CTkRadioButton(manual_frame, text="Manually enter BSSID:", variable=mode_var, value="manual")
    manual_radio.pack(side="left", padx=5)
    bssid_input = ctk.CTkEntry(manual_frame, placeholder_text="Enter BSSID separated by commas:")
    bssid_input.pack(side="left", fill="x", expand=True)

    # Frame для "Сгенерировать" и выпадающий список
    generate_frame = ctk.CTkFrame(root)
    generate_frame.pack(pady=10, fill="x", padx=10)
    generate_radio = ctk.CTkRadioButton(generate_frame, text="Generate                         ", variable=mode_var, value="generate")
    generate_radio.pack(side="left", padx=5)
    dropdown_var = ctk.StringVar(value="1")
    dropdown = ctk.CTkOptionMenu(generate_frame, variable=dropdown_var, values=[str(i) for i in range(1, 7)])
    dropdown.pack(side="left", fill="x", expand=True)



    def configure_action():
        """Настраиваем роутер на основе введённых или сгенерированных BSSID."""
        bssid_list = []

        if mode_var.get() == "manual":
            bssid_input_text = bssid_input.get()
            bssid_list = [bssid.strip() for bssid in bssid_input_text.split(",")]

            invalid_bssids = validate_bssid(bssid_list)
            if invalid_bssids:
                status_label.configure(text=f"Некорректные BSSID: {', '.join(invalid_bssids)}")
                return
        else:
            num_bssids = int(dropdown_var.get())
            bssid_list = [generate_random_bssid() for _ in range(num_bssids)]

        status_label.configure(text="Настройка роутера...")
        root.update()

        result = configure_router(bssid_list, router_ip, login, password)
        status_label.configure(text=result)

    status_label = ctk.CTkLabel(root, text="")
    status_label.pack(pady=10)

    configure_button = ctk.CTkButton(root, text="Apply", command=configure_action)
    configure_button.pack(pady=20)

    settings_button = ctk.CTkButton(root, text="Settings",
                                    command=lambda: show_settings_interface(root, router_ip, login, password))
    settings_button.pack(pady=10)

    def on_closing():
        nonlocal update_running
        update_running = False
        if update_thread is not None:
            update_thread.join(timeout=1)
        root.destroy()
    footer_label = ctk.CTkLabel(root, text="Made by ivese", text_color="red")
    footer_label.pack(pady=5)

    telegram_label = ctk.CTkLabel(root, text="Telegram: @ivese", text_color="red")
    telegram_label.pack(pady=5)
    root.protocol("WM_DELETE_WINDOW", on_closing)


# Загружаем настройки роутера
settings = load_settings()
if settings:
    router_ip = settings['ip']
    login = settings['login']
    password = settings['password']
else:
    router_ip = ""
    login = ""
    password = ""

# Создаём главное окно
root = ctk.CTk()
root.title("Router BSSID Configurator")
root.geometry("400x435")

# Показываем основной интерфейс
show_main_interface(root, router_ip, login, password)

root.mainloop()
