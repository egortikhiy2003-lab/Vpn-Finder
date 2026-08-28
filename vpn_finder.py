#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import re
import subprocess
import time
import os
import platform
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# ============================================================
# НАЧАЛЬНЫЕ ЗНАЧЕНИЯ (можно менять через меню)
# ============================================================
TCP_TIMEOUT = 1.0
PING_TIMEOUT = 0.5
MAX_WORKERS = 40
MAX_CONFIGS_TO_CHECK = 5000

USE_TCP = True      # включить TCP проверку
USE_PING = True     # включить Ping проверку

SOURCES = [
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/BLACK_VLESS_RUS_mobile.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/Vless-Reality-White-Lists-Rus-Mobile.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/refs/heads/main/WHITE-CIDR-RU-all.txt",
    "https://solovyov-jenya2004.vercel.app/final_sorted/",
    "https://solovyov-jenya2004.vercel.app/random/?n=100",
    "https://raw.githubusercontent.com/Kolandone/v2raycollector/main/vless.txt",
    "https://raw.githubusercontent.com/vlesscollector/vlesscollector/refs/heads/main/vless_configs.txt",
    "https://raw.githubusercontent.com/youfoundamin/V2rayCollector/main/vless_iran.txt",
]
# ============================================================

def get_downloads_folder():
    system = platform.system()
    if system == 'Windows':
        return os.path.join(os.environ['USERPROFILE'], 'Downloads')
    elif system == 'Darwin':
        return os.path.join(os.path.expanduser('~'), 'Downloads')
    else:
        possible_paths = [
            '/sdcard/Download',
            '/storage/emulated/0/Download',
            os.path.join(os.path.expanduser('~'), 'Downloads'),
            '/sdcard/Downloads'
        ]
        for path in possible_paths:
            if os.path.exists(path) or path.startswith('/sdcard'):
                return path
        return os.path.join(os.path.expanduser('~'), 'Downloads')

DOWNLOADS = get_downloads_folder()
SUBSCRIPTION_FILE = os.path.join(DOWNLOADS, "vless_subscription.txt")
BEST_CONFIG_FILE = os.path.join(DOWNLOADS, "best_vless_config.txt")
ALL_CONFIGS_FILE = os.path.join(DOWNLOADS, "all_vless_configs.txt")
LOG_FILE = os.path.join(DOWNLOADS, "vpn_finder_log.txt")

def log_message(msg):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    full_msg = f"[{timestamp}] {msg}"
    print(full_msg)
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(full_msg + '\n')
    except:
        pass

def get_all_configs_from_sources():
    log_message(f"Загрузка конфигов из {len(SOURCES)} источников...")
    all_configs = []
    sources_working = 0
    
    for i, url in enumerate(SOURCES, 1):
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(url, timeout=10, headers=headers)
            
            if response.status_code == 200:
                lines = response.text.strip().split('\n')
                configs = [line.strip() for line in lines if line.startswith('vless://')]
                if configs:
                    all_configs.extend(configs)
                    sources_working += 1
                    print(f"\r  [{i}/{len(SOURCES)}] OK +{len(configs)} (всего: {len(all_configs)})", end='', flush=True)
                else:
                    print(f"\r  [{i}/{len(SOURCES)}] нет VLESS-конфигов", end='', flush=True)
            else:
                print(f"\r  [{i}/{len(SOURCES)}] HTTP {response.status_code}", end='', flush=True)
        except Exception as e:
            print(f"\r  [{i}/{len(SOURCES)}] ошибка", end='', flush=True)
    
    print()
    unique_configs = list(dict.fromkeys(all_configs))
    log_message(f"Собрано {len(all_configs)} конфигов, уникальных: {len(unique_configs)}")
    log_message(f"Работающих источников: {sources_working}/{len(SOURCES)}")
    return unique_configs

def extract_host_and_port_from_config(config):
    try:
        match = re.search(r'vless://.+?@([^:]+):(\d+)', config)
        if match:
            return match.group(1), int(match.group(2))
    except:
        pass
    return None, None

def check_tcp(host, port):
    try:
        sock = socket.create_connection((host, port), timeout=TCP_TIMEOUT)
        sock.close()
        return True
    except:
        return False

def check_ping(host):
    try:
        system = platform.system()
        if system == 'Windows':
            cmd = ['ping', '-n', '1', '-w', str(int(PING_TIMEOUT * 1000)), host]
        else:
            cmd = ['ping', '-c', '1', '-W', str(int(PING_TIMEOUT)), host]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=PING_TIMEOUT + 0.5)
        if result.returncode == 0:
            output = result.stdout.decode('utf-8', errors='ignore')
            match = re.search(r'time[=<](\d+\.?\d*)', output)
            if match:
                return float(match.group(1))
    except:
        pass
    return None

def check_single_config(config):
    host, port = extract_host_and_port_from_config(config)
    if not host:
        return config, None
    
    # Проверяем TCP, если включен
    if USE_TCP:
        if not check_tcp(host, port):
            return config, None
    
    # Проверяем Ping, если включен
    if USE_PING:
        ping = check_ping(host)
        return config, ping
    else:
        # Если Ping выключен, считаем что конфиг рабочий (только TCP)
        return config, 999  # ставим фиктивный пинг, чтобы он попал в результаты

def save_all_configs(configs):
    try:
        os.makedirs(os.path.dirname(ALL_CONFIGS_FILE), exist_ok=True)
        with open(ALL_CONFIGS_FILE, 'w', encoding='utf-8') as f:
            f.write(f"# Всего конфигов: {len(configs)}\n")
            f.write(f"# Собрано: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("# ============================================\n\n")
            for config in configs:
                f.write(config + '\n')
        log_message(f"Все конфиги сохранены в {ALL_CONFIGS_FILE}")
        return True
    except Exception as e:
        log_message(f"Ошибка сохранения всех конфигов: {e}")
        return False

def save_subscription(configs):
    try:
        os.makedirs(os.path.dirname(SUBSCRIPTION_FILE), exist_ok=True)
        with open(SUBSCRIPTION_FILE, 'w', encoding='utf-8') as f:
            f.write("# VPN Auto-Finder Подписка (топ-10)\n")
            f.write(f"# Обновлено: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("# ============================================\n\n")
            for config in configs[:10]:
                f.write(config + '\n')
        log_message(f"Подписка сохранена в {SUBSCRIPTION_FILE}")
        return True
    except Exception as e:
        log_message(f"Ошибка сохранения подписки: {e}")
        return False

def save_best_config(config):
    try:
        os.makedirs(os.path.dirname(BEST_CONFIG_FILE), exist_ok=True)
        with open(BEST_CONFIG_FILE, 'w', encoding='utf-8') as f:
            f.write("# Самый быстрый конфиг\n")
            f.write(f"# Найден: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("# ============================================\n\n")
            f.write(config)
        log_message(f"Лучший конфиг сохранён в {BEST_CONFIG_FILE}")
        return True
    except Exception as e:
        log_message(f"Ошибка сохранения лучшего конфига: {e}")
        return False

def clear_screen():
    os.system('clear' if os.name == 'posix' else 'cls')

def show_header():
    clear_screen()
    print("=" * 75)
    print("  Поиск обход белых списков v1.0")
    tcp_status = "ВКЛ" if USE_TCP else "ВЫКЛ"
    ping_status = "ВКЛ" if USE_PING else "ВЫКЛ"
    print(f"  Настройки: TCP={TCP_TIMEOUT}с, Ping={PING_TIMEOUT}с, потоки={MAX_WORKERS}, лимит={MAX_CONFIGS_TO_CHECK}")
    print(f"  TCP: {tcp_status}, Ping: {ping_status}")
    print("=" * 75)
    print(f"  Файлы сохраняются в: {DOWNLOADS}")
    print(f"  Источников: {len(SOURCES)}")
    print("=" * 75)
    print()

def show_results(results, total_checked, total_available):
    if not results:
        print("\nНет рабочих серверов!")
        return
    
    print("\n" + "=" * 75)
    print(f"  Найдено {len(results)} работающих серверов!")
    if USE_PING:
        print(f"  Самый быстрый пинг: {results[0][1]:.0f} мс")
    else:
        print("  Ping отключен, отображены все прошедшие TCP")
    print(f"  Проверено: {total_checked} из {total_available} доступных (лимит {MAX_CONFIGS_TO_CHECK})")
    print("=" * 75)
    print("\nТоп-10 конфигов:")
    for i, (config, ping) in enumerate(results[:10], 1):
        short = config[:70] + "..." if len(config) > 70 else config
        if USE_PING:
            print(f"  {i:>2}. пинг: {ping:>5.0f} мс")
        else:
            print(f"  {i:>2}. TCP OK")
        print(f"      {short}")
        print()
    
    print(f"Файлы сохранены в папке Загрузки:")
    print(f"   Подписка (топ-10): {SUBSCRIPTION_FILE}")
    print(f"   Лучший конфиг:      {BEST_CONFIG_FILE}")
    print(f"   Все конфиги:        {ALL_CONFIGS_FILE}")
    print("=" * 75)

def run_search():
    show_header()
    start_time = time.time()
    
    all_configs = get_all_configs_from_sources()
    if not all_configs:
        log_message("Не удалось собрать конфиги ни из одного источника!")
        return False
    
    save_all_configs(all_configs)
    
    total_available = len(all_configs)
    if total_available > MAX_CONFIGS_TO_CHECK:
        configs_to_check = all_configs[:MAX_CONFIGS_TO_CHECK]
        log_message(f"Ограничение: проверяем только {MAX_CONFIGS_TO_CHECK} из {total_available} конфигов")
    else:
        configs_to_check = all_configs
        log_message(f"Проверяем все {total_available} конфигов")
    
    total = len(configs_to_check)
    log_message(f"Проверяем {total} конфигов (TCP={USE_TCP}, Ping={USE_PING})...")
    print("Прогресс обновляется после каждого конфига:\n")
    
    results = []
    tcp_ok = 0
    checked = 0
    start_ping = time.time()
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_config = {executor.submit(check_single_config, config): config for config in configs_to_check}
        
        for future in as_completed(future_to_config):
            config, ping = future.result()
            checked += 1
            
            if ping is not None:
                results.append((config, ping))
                tcp_ok += 1
                if USE_PING:
                    status = f"OK {ping:.0f}мс"
                else:
                    status = "TCP OK"
            else:
                host, port = extract_host_and_port_from_config(config)
                if host and check_tcp(host, port):
                    tcp_ok += 1
                    status = "TCP OK, ping нет"
                else:
                    status = "TCP/ping нет"
            
            percent = (checked / total) * 100
            elapsed = time.time() - start_ping
            if checked > 0:
                avg_time = elapsed / checked
                remaining = (total - checked) * avg_time
                eta = f"осталось {int(remaining)}с"
            else:
                eta = ""
            
            print(f"\r  [{checked}/{total}] ({percent:.1f}%) {status}  {eta}   ", end='', flush=True)
    
    print()
    log_message(f"Проверка завершена. TCP прошли: {tcp_ok}, всего результатов: {len(results)}")
    
    if USE_PING:
        results.sort(key=lambda x: x[1])
    else:
        # если пинг выключен, сортировка не нужна, но оставим как есть
        results.sort(key=lambda x: x[1] if x[1] is not None else 999)
    
    if results:
        best_configs = [config for config, _ in results[:10]]
        best_config = results[0][0]
        save_subscription(best_configs)
        save_best_config(best_config)
        
        elapsed_total = time.time() - start_time
        log_message(f"Готово. Общее время: {elapsed_total:.1f} сек")
        show_results(results, total, total_available)
        return True
    else:
        log_message("Ни один конфиг не прошёл проверку!")
        return False

def show_settings():
    global TCP_TIMEOUT, PING_TIMEOUT, MAX_WORKERS, MAX_CONFIGS_TO_CHECK, USE_TCP, USE_PING
    clear_screen()
    print("=" * 75)
    print("  НАСТРОЙКИ")
    print("=" * 75)
    print(f"  1. TCP таймаут          : {TCP_TIMEOUT} сек")
    print(f"  2. Ping таймаут         : {PING_TIMEOUT} сек")
    print(f"  3. Количество потоков   : {MAX_WORKERS}")
    print(f"  4. Лимит конфигов       : {MAX_CONFIGS_TO_CHECK}")
    print(f"  5. TCP проверка         : {'ВКЛ' if USE_TCP else 'ВЫКЛ'}")
    print(f"  6. Ping проверка        : {'ВКЛ' if USE_PING else 'ВЫКЛ'}")
    print("  7. Вернуться в главное меню")
    print("=" * 75)
    choice = input("\nВыбери параметр для изменения (1-7): ").strip()
    
    if choice == '1':
        try:
            val = float(input(f"Введите новое значение TCP таймаута (сейчас {TCP_TIMEOUT}): "))
            if val >= 0.1:
                TCP_TIMEOUT = val
                print(f"Таймаут TCP установлен на {TCP_TIMEOUT}")
            else:
                print("Значение должно быть не менее 0.1")
        except:
            print("Неверный ввод, должно быть число")
        input("\nНажми Enter для продолжения...")
        show_settings()
    elif choice == '2':
        try:
            val = float(input(f"Введите новое значение Ping таймаута (сейчас {PING_TIMEOUT}): "))
            if val >= 0.1:
                PING_TIMEOUT = val
                print(f"Таймаут Ping установлен на {PING_TIMEOUT}")
            else:
                print("Значение должно быть не менее 0.1")
        except:
            print("Неверный ввод, должно быть число")
        input("\nНажми Enter для продолжения...")
        show_settings()
    elif choice == '3':
        try:
            val = int(input(f"Введите новое количество потоков (сейчас {MAX_WORKERS}): "))
            if val >= 1:
                MAX_WORKERS = val
                print(f"Количество потоков установлено на {MAX_WORKERS}")
            else:
                print("Значение должно быть не менее 1")
        except:
            print("Неверный ввод, должно быть целое число")
        input("\nНажми Enter для продолжения...")
        show_settings()
    elif choice == '4':
        try:
            val = int(input(f"Введите новое ограничение конфигов (сейчас {MAX_CONFIGS_TO_CHECK}): "))
            if val >= 10:
                MAX_CONFIGS_TO_CHECK = val
                print(f"Лимит конфигов установлен на {MAX_CONFIGS_TO_CHECK}")
            else:
                print("Значение должно быть не менее 10")
        except:
            print("Неверный ввод, должно быть целое число")
        input("\nНажми Enter для продолжения...")
        show_settings()
    elif choice == '5':
        USE_TCP = not USE_TCP
        print(f"TCP проверка теперь {'ВКЛ' if USE_TCP else 'ВЫКЛ'}")
        input("\nНажми Enter для продолжения...")
        show_settings()
    elif choice == '6':
        USE_PING = not USE_PING
        print(f"Ping проверка теперь {'ВКЛ' if USE_PING else 'ВЫКЛ'}")
        input("\nНажми Enter для продолжения...")
        show_settings()
    elif choice == '7':
        return
    else:
        print("Неверный выбор")
        time.sleep(1)
        show_settings()

def show_menu():
    clear_screen()
    print("=" * 75)
    print("  Поиск обход белых списков v1.0")
    print("=" * 75)
    print()
    print("  1. Найти лучшие сервера")
    print("  2. Показать лучший конфиг")
    print("  3. Показать подписку (топ-10)")
    print("  4. Показать все собранные конфиги")
    print("  5. Настройки")
    print("  6. Очистить лог")
    print("  7. Выход")
    print()
    print("=" * 75)
    tcp_status = "ВКЛ" if USE_TCP else "ВЫКЛ"
    ping_status = "ВКЛ" if USE_PING else "ВЫКЛ"
    print(f"  Текущие настройки: TCP={TCP_TIMEOUT}с, Ping={PING_TIMEOUT}с, потоки={MAX_WORKERS}, лимит={MAX_CONFIGS_TO_CHECK}")
    print(f"  TCP: {tcp_status}, Ping: {ping_status}")
    print("=" * 75)
    return input("\nВыбери действие (1-7): ").strip()

def show_best_config():
    try:
        if os.path.exists(BEST_CONFIG_FILE):
            with open(BEST_CONFIG_FILE, 'r', encoding='utf-8') as f:
                print("\n" + "=" * 75)
                print("ЛУЧШИЙ КОНФИГ:")
                print("=" * 75)
                print(f.read())
                print("=" * 75)
                print(f"\nФайл: {BEST_CONFIG_FILE}")
        else:
            print("\nФайл не найден. Сначала запусти поиск (пункт 1).")
    except Exception as e:
        print(f"\nОшибка: {e}")

def show_subscription():
    try:
        if os.path.exists(SUBSCRIPTION_FILE):
            with open(SUBSCRIPTION_FILE, 'r', encoding='utf-8') as f:
                print("\n" + "=" * 75)
                print("ПОДПИСКА (топ-10):")
                print("=" * 75)
                print(f.read())
                print("=" * 75)
                print(f"\nФайл: {SUBSCRIPTION_FILE}")
        else:
            print("\nФайл не найден. Сначала запусти поиск (пункт 1).")
    except Exception as e:
        print(f"\nОшибка: {e}")

def show_all_configs():
    try:
        if os.path.exists(ALL_CONFIGS_FILE):
            with open(ALL_CONFIGS_FILE, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                configs = [line.strip() for line in lines if line.startswith('vless://')]
                print("\n" + "=" * 75)
                print(f"ВСЕ КОНФИГИ (всего: {len(configs)})")
                print("=" * 75)
                for i, config in enumerate(configs[:20], 1):
                    short = config[:70] + "..." if len(config) > 70 else config
                    print(f"  {i}. {short}")
                if len(configs) > 20:
                    print(f"\n  ... и ещё {len(configs) - 20} конфигов")
                print("=" * 75)
                print(f"\nПолный файл: {ALL_CONFIGS_FILE}")
        else:
            print("\nФайл не найден. Сначала запусти поиск (пункт 1).")
    except Exception as e:
        print(f"\nОшибка: {e}")

def clear_logs():
    try:
        if os.path.exists(LOG_FILE):
            os.remove(LOG_FILE)
            print("\nЛог очищен.")
        else:
            print("\nЛог-файл не существует.")
    except Exception as e:
        print(f"\nОшибка: {e}")

def main():
    try:
        requests.get("https://1.1.1.1", timeout=3)
    except:
        print("Нет интернета!")
        input("\nНажми Enter для выхода...")
        return
    
    while True:
        choice = show_menu()
        if choice == '1':
            run_search()
            input("\nНажми Enter для продолжения...")
        elif choice == '2':
            show_best_config()
            input("\nНажми Enter для продолжения...")
        elif choice == '3':
            show_subscription()
            input("\nНажми Enter для продолжения...")
        elif choice == '4':
            show_all_configs()
            input("\nНажми Enter для продолжения...")
        elif choice == '5':
            show_settings()
        elif choice == '6':
            clear_logs()
            input("\nНажми Enter для продолжения...")
        elif choice == '7':
            print("\nВыход.")
            break
        else:
            print("\nНеверный выбор.")
            time.sleep(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nОстановлено пользователем.")
    except Exception as e:
        print(f"\nКритическая ошибка: {e}")
        input("\nНажми Enter для выхода...")