# -*- coding: utf-8 -*-

"""
Aetheria Jaseb - Bot Pengontrol Userbot v10.21 (Laporan Kirim & Hapus)
- FEAT: Mengubah sistem laporan promosi dari edit pesan menjadi kirim pesan baru dan hapus pesan lama.
- FIX: Memperbaiki bug kritis yang dapat menghentikan loop promosi secara diam-diam.
- FEAT: Meningkatkan penanganan error pada pengiriman pesan laporan dan notifikasi.
- FEAT: Sistem auto-blacklist untuk grup yang gagal dikirimi pesan 3x berturut-turut.
- FEAT: Menambahkan informasi 'Putaran ke-X' pada laporan promosi real-time.
"""

import asyncio
import os
import random
import logging
import json
import time
import importlib.util
import sys
import uuid
import re
from functools import wraps
from datetime import datetime, timedelta
from telethon import TelegramClient, events, Button
from telethon.tl.functions.account import UpdateStatusRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.types import Message, PeerUser, PeerChannel
from telethon.errors.rpcerrorlist import (
    SessionPasswordNeededError, PhoneCodeInvalidError, SessionRevokedError,
    MessageNotModifiedError, UserNotParticipantError
)
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- Konfigurasi (Data Anda) ---
API_ID = 10317256
API_HASH = '4ed59a0835d3c1cb1dd0849044e42b76'
BOT_TOKEN = '8326636224:AAFVb8iP00jLTgoMmeOXVd_I3PWrPocPIw4'
DASHBOARD_PHOTO_URL = 'https://files.catbox.moe/yu4tpk.mp4'

# --- URL TUTORIAL ---
TUTORIAL_URL = "https://telegra.ph/ACILSHOP-USERBOT-10-27"

# --- Info Owner ---
OWNER_ID = 6355497501
OWNER_USERNAME = "AcilOffcial"

# --- Konfigurasi Internal ---
FORCE_SUB_CHANNEL = "AcilTestimoni"
LOGIN_TIMEOUT_SECONDS = 300
USERBOT_PLUGINS_DIR = 'plugins'
BOT_PLUGINS_DIR = 'downloader'
ADMIN_MENU_DIR = 'admin_menu' 
FEATURES_PER_PAGE = 6
WATERMARK_TEXT = "@AcilOffcial"
MAX_CONSECUTIVE_FAILS = 3


# --- Nama File untuk Penyimpanan Data ---
USER_DATA_FILE = 'aetheria_data.json'

# --- Logging ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logging.getLogger('telethon').setLevel(logging.WARNING)

# --- Variabel Global & Kunci ---
user_data = {}
active_workers = {}
user_locks = {}
force_sub_enabled = True
BOT_START_TIME = None
BOT_ENTITY = None

# --- Sistem Plugin ---
loaded_userbot_plugins = {}
userbot_plugin_mods = {}
loaded_bot_plugins = {}
bot_plugin_mods = {}

# --- Class Client Kustom untuk Menghitung Unduhan ---
class CountingTelegramClient(TelegramClient):
    async def send_file(self, *args, **kwargs):
        file_arg = kwargs.get('file')
        is_local_file = isinstance(file_arg, str) and os.path.exists(file_arg)
        result = await super().send_file(*args, **kwargs)
        if result and is_local_file:
            user_data['global_download_count'] = user_data.get('global_download_count', 0) + 1
        return result

# --- Manajemen Plugin ---
def get_plugin_id_from_path(path):
    filename = os.path.basename(path)
    return filename[:-3] if filename.endswith('.py') else None

async def register_userbot_plugin_for_all_workers(plugin_id, plugin_data):
    for user_id, worker in active_workers.items():
        if callable(plugin_data.get("run_function")):
            try:
                worker.client.bot_entity = BOT_ENTITY
                plugin_handlers = await plugin_data["run_function"](worker.client, user_id, user_data)
                if plugin_handlers:
                    for handler, event_filter in plugin_handlers:
                        worker.client.add_event_handler(handler, event_filter)
                        worker.registered_handlers.append((handler, event_filter, plugin_id))
            except Exception as e:
                logging.error(f"Error mendaftarkan plugin userbot '{plugin_id}' untuk user {user_id}: {e}")

async def unregister_userbot_plugin_for_all_workers(plugin_id):
    for worker in active_workers.values():
        handlers_to_remove = [(h, f) for h, f, pid in worker.registered_handlers if pid == plugin_id]
        for handler, event_filter in handlers_to_remove:
            worker.client.remove_event_handler(handler, event_filter)
        worker.registered_handlers = [h for h in worker.registered_handlers if h[2] != plugin_id]

async def load_or_reload_plugin(path, plugin_registry, mod_registry, plugin_type="userbot"):
    plugin_id = get_plugin_id_from_path(path)
    if not plugin_id: return
    is_update = plugin_id in plugin_registry
    action_log = "updated" if is_update else "detected"
    logging.info(f"Plugin {plugin_type} '{plugin_id}' {action_log}. Meregistrasi...")
    if is_update and plugin_type == "userbot":
        await unregister_userbot_plugin_for_all_workers(plugin_id)
    dir_name = os.path.basename(os.path.dirname(path))
    module_name = f"{dir_name}.{plugin_id}"
    try:
        if module_name in sys.modules: del sys.modules[module_name]
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        plugin_data = {
            "name": getattr(module, 'plugin_name', 'Tanpa Nama'),
            "description": getattr(module, 'plugin_description', 'Tidak ada deskripsi.'),
            "version": getattr(module, 'plugin_version', '1.0'),
            "run_function": getattr(module, 'run', None)
        }
        if plugin_type == "bot":
            plugin_data["can_handle"] = getattr(module, 'can_handle', None)
            plugin_data["handle_url"] = getattr(module, 'handle_url', None)
        plugin_registry[plugin_id] = plugin_data
        mod_registry[path] = os.path.getmtime(path)
        if plugin_type == "userbot":
            await register_userbot_plugin_for_all_workers(plugin_id, plugin_data)
        logging.info(f"Plugin {plugin_type} '{plugin_id}' berhasil diregistrasi.")
    except Exception as e:
        logging.error(f"Gagal memuat/memuat ulang plugin {plugin_type} {plugin_id}: {e}")

async def remove_plugin(path, plugin_registry, mod_registry, plugin_type="userbot"):
    plugin_id = get_plugin_id_from_path(path)
    if plugin_id and plugin_id in plugin_registry:
        logging.info(f"Plugin {plugin_type} '{plugin_id}' removed. Menonaktifkan...")
        if plugin_type == "userbot":
            await unregister_userbot_plugin_for_all_workers(plugin_id)
        del plugin_registry[plugin_id]
        if path in mod_registry:
            del mod_registry[path]
        logging.info(f"Plugin {plugin_type} '{plugin_id}' berhasil dinonaktifkan.")

async def initial_plugin_load():
    if not os.path.exists(USERBOT_PLUGINS_DIR): os.makedirs(USERBOT_PLUGINS_DIR)
    for filename in os.listdir(USERBOT_PLUGINS_DIR):
        if filename.endswith('.py') and not filename.startswith('_'):
            path = os.path.join(USERBOT_PLUGINS_DIR, filename)
            await load_or_reload_plugin(path, loaded_userbot_plugins, userbot_plugin_mods, "userbot")
    if not os.path.exists(BOT_PLUGINS_DIR): os.makedirs(BOT_PLUGINS_DIR)
    for filename in os.listdir(BOT_PLUGINS_DIR):
        if filename.endswith('.py') and not filename.startswith('_'):
            path = os.path.join(BOT_PLUGINS_DIR, filename)
            await load_or_reload_plugin(path, loaded_bot_plugins, bot_plugin_mods, "bot")

class PluginChangeHandler(FileSystemEventHandler):
    def __init__(self, loop):
        self.loop = loop
    def dispatch(self, event):
        if event.is_directory or not event.src_path.endswith('.py'): return
        path = event.src_path
        dir_name = os.path.basename(os.path.dirname(path))
        if dir_name == USERBOT_PLUGINS_DIR:
            registry, mods, p_type = loaded_userbot_plugins, userbot_plugin_mods, "userbot"
        elif dir_name == BOT_PLUGINS_DIR:
            registry, mods, p_type = loaded_bot_plugins, bot_plugin_mods, "bot"
        else: return
        if event.event_type == 'created':
            asyncio.run_coroutine_threadsafe(load_or_reload_plugin(path, registry, mods, p_type), self.loop)
        elif event.event_type == 'modified':
            if os.path.getmtime(path) > mods.get(path, 0):
                asyncio.run_coroutine_threadsafe(load_or_reload_plugin(path, registry, mods, p_type), self.loop)
        elif event.event_type == 'deleted':
            asyncio.run_coroutine_threadsafe(remove_plugin(path, registry, mods, p_type), self.loop)

# --- Fungsi Manajemen Data & Decorator ---
def save_user_data():
    with open(USER_DATA_FILE, 'w') as f:
        data_to_save = {k: v for k, v in user_data.items() if k != 'temp'}
        json.dump(data_to_save, f, indent=4)

def load_user_data():
    global user_data
    if os.path.exists(USER_DATA_FILE):
        try:
            with open(USER_DATA_FILE, 'r') as f:
                user_data = json.load(f)
        except (json.JSONDecodeError, TypeError): user_data = {}
    else: user_data = {}
    user_data.setdefault('global_download_count', 0)

def check_subscription(func):
    @wraps(func)
    async def wrapped(event, *args, **kwargs):
        if not force_sub_enabled or event.sender_id == OWNER_ID:
            return await func(event, *args, **kwargs)
        try:
            await bot.get_permissions(FORCE_SUB_CHANNEL, event.sender_id)
            return await func(event, *args, **kwargs)
        except UserNotParticipantError:
            await event.respond("**❗️ AKSES DITOLAK ❗️**\n\nUntuk dapat menggunakan bot ini, Anda diwajibkan untuk bergabung dengan channel kami.", buttons=[[Button.url("🚀 Gabung Channel", f"https://t.me/{FORCE_SUB_CHANNEL}")], [Button.inline("✅ Sudah Bergabung", "check_join")]])
        except Exception:
            return await func(event, *args, **kwargs)
    return wrapped

# --- Kelas UserbotWorker ---
class UserbotWorker:
    def __init__(self, user_id, client: TelegramClient, bot_instance):
        self.user_id = user_id
        self.client = client
        self.bot = bot_instance
        self.is_promoting = False
        self.promotion_task = None
        self.online_task = None
        self.promo_message: Message | str | None = None
        self.registered_handlers = []
        self.report_message_id = None
        self.promo_failure_tracker = {}


    async def initialize_promo_message(self):
        user_id_str = str(self.user_id)
        u_data = user_data.get(user_id_str, {})
        self.promo_message = None
        if not u_data.get('promo_is_forward') and u_data.get('promo_text'):
            self.promo_message = u_data.get('promo_text')
            return
        if u_data.get('promo_is_forward'):
            ref_code = u_data.get('promo_ref_code')
            saved_msg_id = u_data.get('promo_saved_msg_id')
            if saved_msg_id:
                try:
                    self.promo_message = await self.client.get_messages('me', ids=saved_msg_id)
                    if self.promo_message: return
                    else: u_data.pop('promo_saved_msg_id', None)
                except Exception: pass
            if ref_code:
                try:
                    reply_message = await self.client.iter_messages(BOT_ENTITY.id, search=f"REF-{ref_code}", limit=1).__anext__()
                    original_message = await reply_message.get_reply_message()
                    saved_message = await self.client.forward_messages('me', original_message)
                    u_data['promo_saved_msg_id'] = saved_message.id
                    u_data.pop('promo_ref_code', None)
                    save_user_data()
                    self.promo_message = saved_message
                except Exception as e:
                    logging.error(f"[{self.user_id}] GAGAL memproses kode referensi '{ref_code}': {e}")
                    self.promo_message = "Gagal memproses pesan forward. Atur ulang."

    async def register_all_handlers(self):
        for plugin_id, plugin_data in loaded_userbot_plugins.items():
            if callable(plugin_data.get("run_function")):
                try:
                    self.client.bot_entity = BOT_ENTITY
                    plugin_handlers = await plugin_data["run_function"](self.client, self.user_id, user_data)
                    if plugin_handlers:
                        for handler, event_filter in plugin_handlers:
                            self.client.add_event_handler(handler, event_filter)
                            self.registered_handlers.append((handler, event_filter, plugin_id))
                except Exception as e:
                    logging.error(f"Error saat menjalankan plugin '{plugin_id}' untuk user {self.user_id}: {e}")

    async def start(self):
        try:
            if not self.client.is_connected(): await self.client.connect()
            await self.initialize_promo_message()
            await self.register_all_handlers()
            self.online_task = asyncio.create_task(self.keep_online_task())
            await self.client.send_message('me', "✅ **Userbot Anda sekarang aktif!**\nSemua kontrol sekarang ada di bot utama.")
        except SessionRevokedError:
            await self.bot.send_message(self.user_id, "❌ **Sesi Anda tidak valid lagi!**\nSesi telah dihapus. Silakan tekan 'Start Userbot' untuk login kembali.")
            await shutdown_userbot(self.user_id, delete_session=True)
        except Exception as e:
            await self.bot.send_message(self.user_id, f"❌ Terjadi error saat memulai userbot Anda: `{e}`")
            await shutdown_userbot(self.user_id)

    async def stop(self):
        if self.promotion_task: self.promotion_task.cancel()
        if self.online_task: self.online_task.cancel()
        self.is_promoting = False
        for handler, event_filter, _ in self.registered_handlers:
            self.client.remove_event_handler(handler, event_filter)
        self.registered_handlers = []
        try:
            await self.client.send_message('me', "🛑 **Userbot Anda telah dihentikan.**")
        except Exception: pass
    
    async def keep_online_task(self):
        while True:
            try:
                await self.client(UpdateStatusRequest(offline=False))
                await asyncio.sleep(240)
            except Exception: await asyncio.sleep(60)

    def start_promotion(self):
        if self.is_promoting: return False
        if not self.promo_message or (isinstance(self.promo_message, str) and "Gagal" in self.promo_message):
            return False
        self.is_promoting = True
        self.promo_failure_tracker = {}
        self.promotion_task = asyncio.create_task(self.run_promotion_loop())
        return True

    def stop_promotion(self):
        if not self.is_promoting: return False
        self.is_promoting = False
        if self.promotion_task: self.promotion_task.cancel()
        asyncio.create_task(self.update_report_message(status="Dihentikan Manual 🛑"))
        return True

    # --- PERUBAHAN --- Logika diubah menjadi Kirim & Hapus
    async def update_report_message(self, status, sent=0, failed=0, cycle_delay=0, next_run_time=None, cycle=0):
        now = datetime.now().strftime('%d %B %Y, %H:%M:%S')
        
        next_run_str = "N/A"
        if next_run_time:
            next_run_str = next_run_time.strftime('%H:%M:%S')

        cycle_line = f"**Putaran ke:** `{cycle}`\n" if cycle > 0 else ""

        text = (
            "**⚜️ Acilbot Promotion ⚜️**\n\n"
            f"**Waktu Laporan:** `{now}`\n"
            f"**Status:** `{status}`\n"
            f"{cycle_line}"
            f"**Berhasil Terkirim:** `{sent}`\n"
            f"**Gagal Terkirim:** `{failed}`\n\n"
            f"**Info Siklus:** `Setiap {cycle_delay} menit`\n"
            f"**Siaran Berikutnya:** `{next_run_str}`"
        )
        
        buttons = None
        if "Dihentikan" not in status and "Selesai" not in status:
            buttons = [Button.inline("Hentikan Promosi 🛑", f"stop_promo_report_{self.user_id}")]

        # 1. Hapus pesan lama (jika ada)
        if self.report_message_id:
            try:
                await self.bot.delete_messages(self.user_id, [self.report_message_id])
            except Exception:
                pass # Abaikan jika gagal (mungkin sudah terhapus)

        # 2. Kirim pesan baru dan simpan ID-nya
        try:
            new_message = await self.bot.send_message(self.user_id, text, buttons=buttons)
            self.report_message_id = new_message.id
        except Exception as e:
            logging.error(f"[{self.user_id}] Gagal mengirim pesan laporan baru: {e}")
            self.report_message_id = None


    async def run_promotion_loop(self):
        await asyncio.sleep(random.randint(2, 5))
        settings = user_data.get(str(self.user_id), {})
        cycle_delay_minutes = settings.get('promo_cycle_delay_minutes', 60)
        send_delay_seconds = settings.get('sequential_send_delay_seconds', 0.5)
        
        cycle_count = 1

        while self.is_promoting:
            try:
                await self.initialize_promo_message()
                if not self.promo_message or (isinstance(self.promo_message, str) and "Gagal" in self.promo_message):
                    await self.update_report_message(status="Dihentikan (Pesan Promo Error) ❌")
                    break

                if 'promo_blacklist' not in settings:
                    settings['promo_blacklist'] = []

                blacklist = settings.get('promo_blacklist', [])
                all_groups = [d for d in await self.client.get_dialogs() if d.is_group]
                groups = [d for d in all_groups if d.id not in blacklist]
                
                if not groups:
                    next_run = datetime.now() + timedelta(minutes=cycle_delay_minutes)
                    await self.update_report_message(
                        status="Menunggu (Tidak ada grup) ⏳",
                        cycle_delay=cycle_delay_minutes,
                        next_run_time=next_run
                    )
                    await asyncio.sleep(cycle_delay_minutes * 60)
                    continue

                random.shuffle(groups)
                
                await self.update_report_message(
                    status=f"Menyiarkan ke {len(groups)} grup... 🚀",
                    cycle_delay=cycle_delay_minutes,
                    cycle=cycle_count
                )
                
                sent_count, failed_count = 0, 0
                auto_blacklisted_groups = []

                for i, group in enumerate(groups):
                    if not self.is_promoting: break
                    try:
                        if isinstance(self.promo_message, Message):
                            await self.client.forward_messages(group.id, self.promo_message)
                        else:
                            await self.client.send_message(group.id, self.promo_message + WATERMARK_TEXT)
                        sent_count += 1
                        self.promo_failure_tracker[group.id] = 0
                    except Exception as e:
                        logging.warning(f"[{self.user_id}] Gagal mengirim ke {group.id}: {e}")
                        failed_count += 1
                        current_fails = self.promo_failure_tracker.get(group.id, 0) + 1
                        self.promo_failure_tracker[group.id] = current_fails
                        
                        if current_fails >= MAX_CONSECUTIVE_FAILS:
                            if group.id not in settings['promo_blacklist']:
                                settings['promo_blacklist'].append(group.id)
                                auto_blacklisted_groups.append(group.id)
                            self.promo_failure_tracker[group.id] = 0
                    
                    if i < len(groups) - 1:
                        await asyncio.sleep(send_delay_seconds + random.uniform(0.1, 0.4))

                if auto_blacklisted_groups:
                    save_user_data()
                    blacklisted_ids_str = "\n".join([f"- `{gid}`" for gid in auto_blacklisted_groups])
                    notification_text = (
                        "**⚠️ Peringatan Keamanan Promosi ⚠️**\n\n"
                        "Beberapa grup telah dihapus dari daftar target promosi karena gagal dikirimi pesan secara terus-menerus:\n"
                        f"{blacklisted_ids_str}\n\n"
                        "Grup-grup ini telah ditambahkan ke blacklist Anda. Anda dapat mengelolanya di panel promosi."
                    )
                    try:
                        await self.bot.send_message(self.user_id, notification_text)
                    except Exception as e:
                        logging.error(f"[{self.user_id}] Gagal mengirim notifikasi auto-blacklist: {e}")


                next_run = datetime.now() + timedelta(minutes=cycle_delay_minutes)
                status_text = f"Menunggu siklus berikutnya... ⏳"
                await self.update_report_message(
                    status=status_text,
                    sent=sent_count,
                    failed=failed_count,
                    cycle_delay=cycle_delay_minutes,
                    next_run_time=next_run,
                    cycle=cycle_count
                )
                
                cycle_count += 1
                await asyncio.sleep(cycle_delay_minutes * 60)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"[{self.user_id}] Error loop promosi: {e}")
                next_run = datetime.now() + timedelta(minutes=5)
                await self.update_report_message(
                    status="Error, mencoba lagi dalam 5 menit ⚠️",
                    cycle_delay=cycle_delay_minutes,
                    next_run_time=next_run,
                    cycle=cycle_count
                )
                await asyncio.sleep(300)
        
        self.is_promoting = False
        if not self.promotion_task.cancelled():
             await self.update_report_message(status="Dihentikan 🛑")


# --- Bot Controller Utama ---
bot = CountingTelegramClient('aetheria_controller_session', API_ID, API_HASH)

def get_status_emoji(status_bool):
    return "🟢 ON" if status_bool else "🔴 OFF"

def get_bot_uptime():
    if BOT_START_TIME is None: return "N/A"
    delta = int(time.time() - BOT_START_TIME)
    d, rem = divmod(delta, 86400); h, rem = divmod(rem, 3600); m, _ = divmod(rem, 60)
    uptime_str = ""
    if d > 0: uptime_str += f"{d}h "
    if h > 0: uptime_str += f"{h}j "
    if m > 0: uptime_str += f"{m}m"
    return uptime_str.strip() or f"{delta}d"

async def get_dashboard_text(user_id):
    user_id_str = str(user_id)
    current_user_data = user_data.get(user_id_str, {})
    uptime_string = get_bot_uptime()
    total_users = len([u for u in user_data if u.isdigit()])
    running_users = len(active_workers)
    download_count = user_data.get('global_download_count', 0)

    nama, nama_lengkap, bio_pengguna = "Pengguna", "Tidak Diketahui", "Tidak Diketahui"
    try:
        user_entity = await bot.get_entity(user_id)
        full_user = await bot(GetFullUserRequest(user_id))
        nama = user_entity.first_name
        nama_lengkap = f"{user_entity.first_name} {user_entity.last_name or ''}".strip()
        bio_pengguna = full_user.full_user.about or "Bio tidak diatur."
    except Exception:
        pass

    userbot_status_string = "🟢 Aktif" if user_id in active_workers else "🔴 Tidak Aktif"
    pmpermit_status = get_status_emoji(current_user_data.get('pmpermit', {}).get('status', False))
    autoreply_status = get_status_emoji(current_user_data.get('autoreply', {}).get('status', False))
    autoread_status = get_status_emoji(any(current_user_data.get('autoread', {}).values()))
    anticulik_status = get_status_emoji(current_user_data.get('anticulik', False))
    autochangename_status = get_status_emoji(current_user_data.get('autochangename', {}).get('status', False))

    return (
        "╭─────────────────────────────\n"
        f"│ 👋 𝐒𝐞𝐥𝐚𝐦𝐚𝐭 𝐃𝐚𝐭𝐚𝐧𝐠, **{nama}**\n"
        "├─────────────────────────────\n"
        "│ 📦 𝐔𝐒𝐄𝐑 𝐈𝐍𝐅𝐎\n"
        f"│ 👤 Nama       : {nama_lengkap}\n"
        f"│ 🆔 User ID    : {user_id}\n"
        f"│ 💬 Bio        : {bio_pengguna}\n"
        f"│ ⚙️ Status Bot : {userbot_status_string}\n"
        "├─────────────────────────────\n"
        "│ 📊 𝐒𝐓𝐀𝐓𝐔𝐒 𝐒𝐘𝐒𝐓𝐄𝐌\n"
        f"│ 🕰️ Waktu Aktif : {uptime_string}\n"
        f"│ 👥 Total User  : {total_users}\n"
        f"│ 🚀 Userbot Aktif : {running_users}\n"
        f"│ 🌍 Total Unduhan : {download_count}\n"
        "├─────────────────────────────\n"
        "│ ⚙️ 𝐅𝐈𝐓𝐔𝐑 𝐀𝐂𝐈𝐋𝐁𝐎𝐓\n"
        f"│ 🛡️ Izin PM          : {pmpermit_status}\n"
        f"│ 🤖 Balasan Otomatis : {autoreply_status}\n"
        f"│ 📖 Baca Otomatis    : {autoread_status}\n"
        f"│ 🏃‍♂️ Anti Culik       : {anticulik_status}\n"
        f"│ 🎭 Ubah Nama Otomatis: {autochangename_status}\n"
        "├─────────────────────────────\n"
        "│ 💡 Gunakan tombol di bawah\n"
        "│    untuk mengelola fitur.\n"
        "├─────────────────────────────\n"
        "│ 🔰 Credits: @AcilOffcial\n"
        "╰─────────────────────────────"
    )

async def get_dashboard_buttons(user_id):
    userbot_button = [Button.inline("🛑 Stop Userbot", "stop_userbot")] if user_id in active_workers else [Button.inline("🚀 Start Userbot", "start_userbot")]
    userbot_features_row1 = [Button.inline("👑 Panel Promosi", "promo_panel"), Button.inline("✨ Fitur Ubot", "list_features_0")]
    bot_features_row = [Button.inline("📥 Downloader", "downloader_panel")]
    other_buttons_row = [Button.url("📚 Tutorial & FAQ", TUTORIAL_URL), Button.url("💬 Hubungi Owner", f"https://t.me/{OWNER_USERNAME}")]
    return [userbot_button, userbot_features_row1, bot_features_row, other_buttons_row]

async def generate_promo_panel(user_id):
    user_id_str = str(user_id)
    u_data = user_data.get(user_id_str, {})
    worker = active_workers.get(user_id)
    status = "🟢 On" if worker and worker.is_promoting else "🔴 Off"
    cycle_delay = u_data.get('promo_cycle_delay_minutes', 60)
    send_delay = u_data.get('sequential_send_delay_seconds', 0.5)
    text = (f"**👑 Control Panel Promotion 👑**\n\n"
            f"**Status Promosi:** {status}\n"
            f"**Delay Siklus:** `{cycle_delay}` menit\n"
            f"**Delay Antarkirim:** `{send_delay}` detik\n\n"
            "Gunakan tombol di bawah untuk mengelola promosi Anda.")
    toggle_button = Button.inline("🛑 Stop Promosi", "toggle_promo") if worker and worker.is_promoting else Button.inline("🚀 Start Promosi", "toggle_promo")
    buttons = [[toggle_button], [Button.inline("✉️ Set Pesan", "set_promo_message")], [Button.inline("⏱️ Set Delay Siklus", "set_promo_cycle_delay"), Button.inline("⚡️ Set Delay Kirim", "set_promo_send_delay")], [Button.inline("🚫 Blacklist Grup", "manage_blacklist")], [Button.inline("⬅️ Kembali", "back_to_dashboard")]]
    return text, buttons

async def generate_blacklist_panel(user_id):
    blacklist = user_data.get(str(user_id), {}).get('promo_blacklist', [])
    text = "**🚫 Manajemen Blacklist Grup**\n\n"
    text += "Saat ini tidak ada grup yang diblacklist." if not blacklist else "Grup berikut tidak akan dikirimi promosi:\n" + "\n".join([f"- `{gid}`" for gid in blacklist])
    buttons = [[Button.inline("➕ Tambah", "add_to_blacklist"), Button.inline("➖ Hapus", "remove_from_blacklist")], [Button.inline("⬅️ Kembali", "promo_panel")]]
    return text, buttons

def generate_features_view(page=0):
    plugin_items = list(loaded_userbot_plugins.items())
    if not plugin_items: return "**Tidak ada fitur tambahan userbot yang tersedia.**", [[Button.inline("⬅️ Kembali", "back_to_dashboard")]]
    total_pages = (len(plugin_items) - 1) // FEATURES_PER_PAGE
    start_index, end_index = page * FEATURES_PER_PAGE, (page + 1) * FEATURES_PER_PAGE
    current_plugins = plugin_items[start_index:end_index]
    text = f"**✨ Daftar Fitur Userbot (Halaman {page + 1}/{total_pages + 1})**\n\nPilih fitur untuk melihat detailnya:"
    buttons = [[Button.inline(p['name'], f"view_feature_{pid}_{page}") for pid, p in current_plugins[i:i+2]] for i in range(0, len(current_plugins), 2)]
    nav_row = []
    if page > 0: nav_row.append(Button.inline("⬅️", f"list_features_{page - 1}"))
    nav_row.append(Button.inline("❌", "back_to_dashboard"))
    if page < total_pages: nav_row.append(Button.inline("➡️", f"list_features_{page + 1}"))
    buttons.append(nav_row)
    return text, buttons

def paginate_modules(page_number, all_plugins, prefix):
    buttons = []
    plugin_items = list(all_plugins.items())
    start_index = page_number * FEATURES_PER_PAGE
    end_index = start_index + FEATURES_PER_PAGE
    current_plugins = plugin_items[start_index:end_index]
    for i in range(0, len(current_plugins), 2):
        row = []
        for plugin_id, plugin_data in current_plugins[i:i+2]:
            row.append(Button.inline(plugin_data['name'], f"{prefix}_module_{plugin_id}"))
        buttons.append(row)
    nav_row = []
    if page_number > 0:
        nav_row.append(Button.inline("⬅️", f"{prefix}_prev_{page_number - 1}"))
    nav_row.append(Button.inline("❌", f"{prefix}_close"))
    if end_index < len(plugin_items):
        nav_row.append(Button.inline("➡️", f"{prefix}_next_{page_number + 1}"))
    buttons.append(nav_row)
    return buttons

@bot.on(events.NewMessage(pattern='/start'))
@check_subscription
async def start_handler(event):
    user_id_str = str(event.sender_id)
    if not user_id_str.isdigit(): return
    if user_id_str not in user_data:
        user_data[user_id_str] = {'status': 'idle', 'promo_is_forward': False, 'promo_text': None, 'promo_ref_code': None, 'promo_saved_msg_id': None, 'promo_blacklist': [], 'promo_cycle_delay_minutes': 60, 'sequential_send_delay_seconds': 0.5}
    dashboard_text = await get_dashboard_text(event.sender_id)
    buttons = await get_dashboard_buttons(event.sender_id)
    await event.respond(dashboard_text, file=DASHBOARD_PHOTO_URL, buttons=buttons)

@bot.on(events.InlineQuery(pattern=r"^user_help_menu$"))
async def help_inline_handler(event):
    builder = event.builder
    userbot_plugins = loaded_userbot_plugins
    
    top_text = (
        f"**⚜️ 𝚌𝚎𝚌𝚒𝚕𝚒𝚊 𝐔𝐒𝐄𝐑𝐁𝐎𝐓 𝐇𝐄𝐋𝐏 ⚜️**\n\n"
        f"⌬ **Total Modul:** `{len(userbot_plugins)}`\n"
        f"⌬ **Owner:** @{OWNER_USERNAME}\n\n"
        ""
    )
    buttons = paginate_modules(0, userbot_plugins, "help")
    result = builder.article(
        title="Menu Bantuan Userbot",
        text=top_text,
        buttons=buttons,
        link_preview=False
    )
    await event.answer([result])

@bot.on(events.CallbackQuery)
async def callback_handler(event):
    query_data = event.data.decode('utf-8')
    user_id = event.sender_id

    if query_data.startswith("help_"):
        parts = query_data.split('_')
        action = parts[1]
        userbot_plugins = loaded_userbot_plugins
        
        top_text = (
            f"**⚜️ 𝚌𝚎𝚌𝚒𝚕𝚒𝚊 𝐔𝐒𝐄𝐑𝐁𝐎𝐓 𝐇𝐄𝐋𝐏 ⚜️**\n\n"
            f"⌬ **Total Modul:** `{len(userbot_plugins)}`\n"
            f"⌬ **Owner:** @{OWNER_USERNAME}\n\n"
            ""
        )
        try:
            if action == "close":
                await event.delete()
                return
            elif action in ["next", "prev"]:
                page_number = int(parts[2])
                buttons = paginate_modules(page_number, userbot_plugins, "help")
                await event.edit(top_text, buttons=buttons)
            elif action == "module":
                plugin_id = '_'.join(parts[2:])
                if plugin_id in userbot_plugins:
                    plugin = userbot_plugins[plugin_id]
                    text = (
                        f"**⚜️ Bantuan untuk Modul: {plugin['name']} ⚜️**\n\n"
                        f"{plugin['description']}\n\n"
                        f"<blockquote><b>ᣃ࿈ 𝚌𝚎𝚌𝚒𝚕𝚒𝚊 𝐔𝐒𝐄𝐑𝐁𝐎𝐓 ࿈ᣄ</b></blockquote>"
                    )
                    buttons = [Button.inline("⬅️ Kembali", "help_back_0")]
                    await event.edit(text, buttons=buttons, link_preview=False)
            elif action == "back":
                page_number = int(parts[2])
                buttons = paginate_modules(page_number, userbot_plugins, "help")
                await event.edit(top_text, buttons=buttons)
        except MessageNotModifiedError:
            pass
        except Exception as e:
            logging.error(f"Help callback error: {e}")
        return

    user_id_str = str(user_id)
    async def safe_edit(text, buttons=None, file=None):
        try: await event.edit(text, buttons=buttons, file=file)
        except MessageNotModifiedError: pass

    if query_data.startswith("stop_promo_report_"):
        user_id_to_stop = int(query_data.split('_')[3])
        if user_id != user_id_to_stop:
            return await event.answer("❌ Ini bukan tombol untuk Anda.", alert=True)
        
        worker = active_workers.get(user_id)
        if worker and worker.is_promoting:
            worker.stop_promotion()
            await event.answer("✅ Promosi akan dihentikan...", alert=False)
        else:
            await event.answer("ℹ️ Promosi sudah tidak aktif.", alert=False)
        return

    if query_data == 'check_join':
        try:
            await bot.get_permissions(FORCE_SUB_CHANNEL, user_id)
            await event.answer("Terima kasih telah bergabung!", alert=False)
            await start_handler(event)
        except UserNotParticipantError:
            await event.answer("Anda belum bergabung dengan channel.", alert=True)
        return
    if query_data == 'downloader_panel':
        user_data[user_id_str]['status'] = 'waiting_download_link'
        downloader_list = "\n".join([f"- {p['name']}" for p in loaded_bot_plugins.values() if 'can_handle' in p]) or "Belum ada platform yang didukung."
        text = f"**📥 Menu Downloader**\n\nSilakan kirim link yang ingin Anda unduh.\n\n**Platform yang Didukung:**\n{downloader_list}"
        buttons = [[Button.inline("⬅️ Kembali", "back_to_dashboard")]]
        await safe_edit(text, buttons=buttons)
        return
    if query_data.startswith("list_features_"):
        page = int(query_data.split('_')[2])
        text, buttons = generate_features_view(page)
        await safe_edit(text, buttons=buttons)
        return
    if query_data.startswith("view_feature_"):
        _, _, plugin_id, page_str = query_data.split('_', 3)
        plugin = loaded_userbot_plugins.get(plugin_id)
        if plugin:
            text = f"**Fitur: {plugin['name']} (v{plugin['version']})**\n\n**Deskripsi:**\n{plugin['description']}"
            buttons = [[Button.inline(f"⬅️ Kembali", f"list_features_{page_str}")]]
            await safe_edit(text, buttons=buttons)
        return
    if query_data == 'promo_panel':
        text, buttons = await generate_promo_panel(user_id)
        await safe_edit(text, buttons=buttons)
    elif query_data == 'manage_blacklist':
        text, buttons = await generate_blacklist_panel(user_id)
        await safe_edit(text, buttons=buttons)
    elif query_data == 'add_to_blacklist':
        user_data[user_id_str]['status'] = 'waiting_blacklist_add'
        await safe_edit("Kirimkan **ID grup** (pisahkan dengan spasi).", buttons=[[Button.inline("❌ Batal", "manage_blacklist")]])
    elif query_data == 'remove_from_blacklist':
        user_data[user_id_str]['status'] = 'waiting_blacklist_remove'
        await safe_edit("Kirimkan **ID grup** yang ingin dihapus (pisahkan dengan spasi).", buttons=[[Button.inline("❌ Batal", "manage_blacklist")]])
    elif query_data == 'toggle_promo':
        if user_id not in active_workers:
            await safe_edit("❌ **Userbot belum aktif!**", buttons=[[Button.inline("⬅️ Kembali", "promo_panel")]])
            return
        worker = active_workers[user_id]
        if worker.is_promoting:
            worker.stop_promotion()
            await event.answer("Promosi dihentikan.")
        else:
            await worker.initialize_promo_message()
            if worker.start_promotion(): await event.answer("Promosi dimulai. Laporan akan dikirimkan.")
            else: await event.answer("Gagal memulai! Pesan promosi belum diatur.", alert=True)
        text, buttons = await generate_promo_panel(user_id)
        await safe_edit(text, buttons=buttons)
    elif query_data == 'set_promo_message':
        user_data[user_id_str]['status'] = 'waiting_promo_message'
        await safe_edit("**Atur Pesan Promosi:**\n\n- **Teks Biasa:** Kirim teksnya.\n- **Pesan Forward:** Teruskan pesannya ke sini.", buttons=[[Button.inline("❌ Batal", "promo_panel")]])
    elif query_data in ['set_promo_cycle_delay', 'set_promo_send_delay']:
        user_data[user_id_str]['status'] = f'waiting_{query_data.split("_")[2]}_{query_data.split("_")[3]}'
        await safe_edit(f"Kirim angka untuk **delay antar {query_data.split('_')[2]}** ({'menit' if 'cycle' in query_data else 'detik'}).", buttons=[[Button.inline("❌ Batal", "promo_panel")]])
    elif query_data == 'start_userbot':
        await event.answer("✅ Perintah diterima!", alert=False)
        await safe_edit("⏳ Mengecek sesi Anda...")
        if os.path.exists(f"sessions/user_{user_id}.session"): await launch_userbot(event, user_id)
        else:
            user_data[user_id_str]['status'] = 'waiting_phone'
            await safe_edit("⚠️ Sesi tidak ditemukan.\n\nKirim **nomor telepon** (format: `+628...`).", buttons=[[Button.inline("❌ Batal", "cancel_login")]])
    elif query_data == 'stop_userbot':
        await event.answer("Menghentikan...", alert=False)
        await safe_edit("🛑 Menghentikan userbot Anda...")
        await shutdown_userbot(user_id)
        await start_handler(event)
    elif query_data == 'cancel_login':
        await event.answer("Dibatalkan.", alert=False)
        await cleanup_login_attempt(user_id)
        await start_handler(event)
    elif query_data == 'back_to_dashboard':
        user_data[user_id_str]['status'] = 'idle'
        await start_handler(event)

@bot.on(events.NewMessage)
async def message_handler(event):
    if not event.raw_text or event.raw_text.startswith('/'): return
    user_id = event.sender_id
    user_id_str = str(user_id)
    lock = user_locks.setdefault(user_id, asyncio.Lock())
    async with lock:
        u_data = user_data.get(user_id_str, {})
        status = u_data.get('status', 'idle')
        if status == 'waiting_download_link':
            url = event.raw_text.strip()
            handled = False
            for plugin_id, plugin in loaded_bot_plugins.items():
                if callable(plugin.get("can_handle")) and plugin["can_handle"](url):
                    logging.info(f"Link '{url[:30]}...' ditangani oleh '{plugin_id}'")
                    if callable(plugin.get("handle_url")):
                        u_data['status'] = 'idle'
                        await plugin["handle_url"](event, url)
                        handled = True
                        break
            if not handled:
                await event.respond("❌ **Link tidak didukung.**", buttons=[[Button.inline("⬅️ Kembali", "back_to_dashboard")]])
            return
        if status == 'waiting_promo_message':
            worker = active_workers.get(user_id)
            if event.message.fwd_from:
                ref_code = str(uuid.uuid4()).split('-')[0].upper()
                u_data.update({'promo_is_forward': True, 'promo_text': None, 'promo_ref_code': ref_code, 'promo_saved_msg_id': None})
                await event.reply(f"**[SISTEM]** Pesan diterima. Kode: `REF-{ref_code}`")
                if worker: await worker.initialize_promo_message()
            else:
                u_data.update({'promo_is_forward': False, 'promo_text': event.raw_text, 'promo_ref_code': None, 'promo_saved_msg_id': None})
                if worker: worker.promo_message = event.raw_text
                await event.respond("✅ **Pesan promosi (teks) berhasil diatur.**")
            u_data['status'] = 'idle'
            text, buttons = await generate_promo_panel(user_id)
            await event.respond(text, buttons=buttons)
        elif status in ('waiting_blacklist_add', 'waiting_blacklist_remove'):
            try:
                ids = [int(gid) for gid in event.raw_text.split()]
                blacklist = u_data.get('promo_blacklist', [])
                count = 0
                if status == 'waiting_blacklist_add':
                    for gid in ids:
                        if gid not in blacklist: blacklist.append(gid); count += 1
                    msg = f"✅ Berhasil menambahkan **{count}** grup."
                else:
                    for gid in ids:
                        if gid in blacklist: blacklist.remove(gid); count += 1
                    msg = f"✅ Berhasil menghapus **{count}** grup."
                u_data['promo_blacklist'] = blacklist
                save_user_data()
                await event.respond(msg)
            except ValueError: await event.respond("❌ Input tidak valid.")
            u_data['status'] = 'idle'
            text, buttons = await generate_blacklist_panel(user_id)
            await event.respond(text, buttons=buttons)
        elif status in ('waiting_cycle_delay', 'waiting_send_delay'):
            try:
                key, unit, type_func = ('promo_cycle_delay_minutes', 'menit', int) if 'cycle' in status else ('sequential_send_delay_seconds', 'detik', float)
                delay = type_func(event.raw_text)
                if delay <= 0: raise ValueError
                u_data[key] = delay
                await event.respond(f"✅ **Delay diatur ke `{delay}` {unit}.**")
            except (ValueError, TypeError): await event.respond("❌ Input tidak valid.")
            u_data['status'] = 'idle'
            text, buttons = await generate_promo_panel(user_id)
            await event.respond(text, buttons=buttons)
        elif status in ['waiting_phone', 'waiting_code', 'waiting_2fa']:
            if 'temp' not in user_data: user_data['temp'] = {}
            if status == 'waiting_phone':
                u_data.update({'phone': event.raw_text, 'login_timestamp': time.time()})
                await event.respond("⏳ Menghubungkan...")
                client = TelegramClient(f"sessions/user_{user_id}", API_ID, API_HASH)
                user_data['temp'][user_id_str] = client
                try:
                    await client.connect()
                    sent_code = await client.send_code_request(event.raw_text)
                    u_data.update({'phone_code_hash': sent_code.phone_code_hash, 'status': 'waiting_code'})
                    await event.respond("✅ Kode terkirim. Masukkan kode (contoh: `1 2 3 4 5`).", buttons=[[Button.inline("❌ Batal", "cancel_login")]])
                except Exception as e:
                    await event.respond(f"❌ **Error:** `{e}`"); await cleanup_login_attempt(user_id)
            elif status == 'waiting_code':
                client = user_data['temp'].get(user_id_str)
                if not client: await event.respond("❌ Sesi login kadaluarsa."); return
                try:
                    await client.sign_in(u_data['phone'], event.raw_text.replace(' ', ''), phone_code_hash=u_data['phone_code_hash'])
                    await launch_userbot(event, user_id)
                except SessionPasswordNeededError:
                    u_data['status'] = 'waiting_2fa'
                    await event.respond("🔑 Masukkan **kata sandi** 2FA Anda.", buttons=[[Button.inline("❌ Batal", "cancel_login")]])
                except PhoneCodeInvalidError: await event.respond("❌ Kode salah. Coba lagi.")
                except Exception as e: await event.respond(f"❌ **Error:** `{e}`"); await cleanup_login_attempt(user_id)
            elif status == 'waiting_2fa':
                client = user_data['temp'].get(user_id_str)
                if not client: await event.respond("❌ Sesi login kadaluarsa."); return
                try:
                    await client.sign_in(password=event.raw_text)
                    await launch_userbot(event, user_id)
                except Exception as e: await event.respond(f"❌ **Error:** `{e}`"); await cleanup_login_attempt(user_id)

async def launch_userbot(event, user_id):
    user_id_str = str(user_id)
    client = user_data.get('temp', {}).pop(user_id_str, None) or TelegramClient(f"sessions/user_{user_id}", API_ID, API_HASH)
    active_workers[user_id] = UserbotWorker(user_id, client, bot)
    user_data[user_id_str]['status'] = 'running'
    user_data[user_id_str].pop('login_timestamp', None)
    asyncio.create_task(active_workers[user_id].start())
    msg = "✅ **Userbot Anda berhasil dihidupkan!**"
    buttons = [[Button.inline("⬅️ Kembali ke Menu", "back_to_dashboard")]]
    try:
        if isinstance(event, events.CallbackQuery.Event): await event.edit(msg, buttons=buttons)
        else: await event.respond(msg, buttons=buttons)
    except MessageNotModifiedError: pass

async def shutdown_userbot(user_id, delete_session=False):
    if user_id in active_workers:
        worker = active_workers.pop(user_id)
        await worker.stop()
        if worker.client.is_connected(): await worker.client.disconnect()
    user_data[str(user_id)]['status'] = 'idle'
    if delete_session: await cleanup_login_attempt(user_id)

async def cleanup_login_attempt(user_id):
    user_id_str = str(user_id)
    if client := user_data.get('temp', {}).pop(user_id_str, None):
        if client.is_connected(): await client.disconnect()
    if u_data := user_data.get(user_id_str):
        u_data['status'] = 'idle'
        u_data.pop('login_timestamp', None)
    for ext in ['.session', '.session.lock']:
        if os.path.exists(p := f"sessions/user_{user_id}{ext}"): os.remove(p)

async def auto_restart_workers():
    await asyncio.sleep(10)
    logging.info("Memulai auto-restart userbot...")
    for uid_str, u_data in list(user_data.items()):
        if u_data.get('status') == 'running' and uid_str.isdigit():
            user_id = int(uid_str)
            if os.path.exists(f"sessions/user_{user_id}.session"):
                class DummyEvent:
                    async def edit(*a, **kw): pass
                    async def respond(*a, **kw): pass
                try: 
                    await launch_userbot(DummyEvent(), user_id)
                    await asyncio.sleep(2)
                except Exception: 
                    u_data['status'] = 'idle'
            else: 
                u_data['status'] = 'idle'
    logging.info("Proses auto-restart selesai.")


async def periodic_save_task():
    while True:
        await asyncio.sleep(300)
        save_user_data()
        logging.info("Database diperbarui!")

async def check_login_timeouts_task():
    while True:
        await asyncio.sleep(60)
        current_time = time.time()
        for uid_str, u_data in list(user_data.items()):
            if u_data.get('status') in ['waiting_code', 'waiting_2fa'] and (current_time - u_data.get('login_timestamp', 0)) > LOGIN_TIMEOUT_SECONDS:
                user_id = int(uid_str)
                logging.info(f"Login timeout untuk user {user_id}.")
                await cleanup_login_attempt(user_id)
                try: await bot.send_message(user_id, "❌ **Sesi Login Kedaluwarsa.** Silakan mulai lagi.")
                except Exception: pass

async def main():
    global BOT_ENTITY, BOT_START_TIME
    BOT_START_TIME = time.time()
    
    if not os.path.exists('sessions'): os.makedirs('sessions')
    
    load_user_data()
    
    loop = asyncio.get_running_loop()
    event_handler = PluginChangeHandler(loop)
    observer = Observer()
    for d in [USERBOT_PLUGINS_DIR, BOT_PLUGINS_DIR]:
        if not os.path.exists(d): os.makedirs(d)
        observer.schedule(event_handler, d, recursive=True)
    observer.start()
    logging.info(f"Hot-Reload aktif: Memantau '{USERBOT_PLUGINS_DIR}' & '{BOT_PLUGINS_DIR}'...")
    
    try:
        await bot.start(bot_token=BOT_TOKEN)
        BOT_ENTITY = await bot.get_me()
        await initial_plugin_load()
        logging.info(f"Bot Pengontrol v10.21 aktif sebagai @{BOT_ENTITY.username}")
        loop.create_task(auto_restart_workers())
        loop.create_task(periodic_save_task())
        loop.create_task(check_login_timeouts_task())
        await bot.run_until_disconnected()
    except Exception as e:
        logging.critical(f"GAGAL MEMULAI BOT: {e}")
    finally:
        observer.stop()
        observer.join()
        if bot.is_connected(): await bot.disconnect()
        save_user_data()
        logging.info("Bot dihentikan.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
