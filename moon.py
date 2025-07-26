import os
import json
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from PIL import Image
import requests
from io import BytesIO
from threading import Timer
from datetime import datetime

# Bot initialization (يجب أن يكون هنا قبل أي استخدام للـ bot)
TOKEN = '6472606496:AAGmgLlNWpX_ZJDldgvAZpm2Uy9254RYdDQ'
bot = telebot.TeleBot(TOKEN)

# ---------------- CONFIGURATION FILES ----------------
CONFIG_FILE = 'config.json'
USERS_FILE = 'users.json'
IMAGES_FOLDER = 'images'
BACKUP_FILE = 'backup_config.json'

os.makedirs(IMAGES_FOLDER, exist_ok=True)

# Load or initialize config
def load_config():
    if os.path.exists(CONFIG_FILE):
        return json.load(open(CONFIG_FILE, 'r', encoding='utf-8'))
    return {
        'developer_id': 651561282,
        'admins': [],
        'banned_users': [],
        'sticker_label': 'ستيكرات المطور',
        'sticker_url': 'https://t.me/addstickers/emg_s',
        'password_enabled': False,
        'password': '',
        'welcome_message': 'مرحبًا بك! الرجاء إدخال كلمة السر للمتابعة.'
    }
config = load_config()

# Load or initialize users
def load_users():
    if os.path.exists(USERS_FILE):
        raw = json.load(open(USERS_FILE, 'r', encoding='utf-8'))
    else:
        raw = []
    users = []
    for u in raw:
        if isinstance(u, int):
            users.append({'id': u, 'username': ''})
        elif isinstance(u, dict) and 'id' in u:
            users.append({'id': u['id'], 'username': u.get('username', '')})
    return users
users = load_users()

# Save helpers
def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
def save_config():
    save_json(CONFIG_FILE, config)
def save_users():
    save_json(USERS_FILE, users)
def backup_config():
    save_json(BACKUP_FILE, {
        'config': config,
        'users': users,
        'pending_password': list(pending_password)
    })

def restore_config():
    if os.path.exists(BACKUP_FILE):
        data = json.load(open(BACKUP_FILE, 'r', encoding='utf-8'))
        save_json(CONFIG_FILE, data['config'])
        save_json(USERS_FILE, data['users'])
        global config, users, pending_password
        config = load_config()
        users = load_users()
        pending_password = set(data.get('pending_password', []))
        return True
    return False

# إضافة قائمة المستخدمين الذين لم يدخلوا كلمة السر بعد
pending_password = set()

# ---------------- PASSWORD HANDLING ----------------

def require_password(uid):
    return config.get('password_enabled', False) and uid not in config['admins'] and uid != config['developer_id']

@bot.message_handler(commands=['start'])
def cmd_start(message):
    uid = message.chat.id
    uname = message.from_user.username or ''
    # إذا كلمة السر مفعلة والمستخدم ليس ادمن أو مطور
    if require_password(uid) and uid not in pending_password:
        pending_password.add(uid)
        bot.send_message(uid, config.get('welcome_message', 'أدخل كلمة السر للمتابعة:'))
        return
    # إذا كان بانتظار كلمة السر
    if uid in pending_password:
        bot.send_message(uid, 'يرجى إدخال كلمة السر أولاً.')
        return
    existing = next((u for u in users if u['id'] == uid), None)
    if not existing:
        users.append({'id': uid, 'username': uname})
        save_users()
    elif existing['username'] != uname:
        existing['username'] = uname
        save_users()
    text = f"مرحبًا بك {message.from_user.first_name} في بوت توسيط الصور. أرسل صورة أو استخدم الأزرار أدناه."
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(config['sticker_label'], url=config['sticker_url']))
    kb.add(
        InlineKeyboardButton('تلوين', callback_data='colorize'),
        InlineKeyboardButton('تواصل', callback_data='contact_developer')
    )
    bot.send_message(uid, text, reply_markup=kb)

# استقبال كلمة السر من المستخدمين الجدد
@bot.message_handler(func=lambda m: m.chat.id in pending_password)
def handle_password_entry(message):
    uid = message.chat.id
    if message.text == config.get('password', ''):
        pending_password.remove(uid)
        bot.send_message(uid, '✅ تم التحقق! يمكنك الآن استخدام البوت.')
        # إعادة تنفيذ /start تلقائياً
        cmd_start(message)
    else:
        bot.send_message(uid, '❌ كلمة السر خاطئة. حاول مرة أخرى.')

# عند تغيير كلمة السر، تسجيل خروج الجميع
def logout_all_users():
    global pending_password
    pending_password = set(u['id'] for u in users if u['id'] not in config['admins'] and u['id'] != config['developer_id'])

# State containers
images_to_color = {}
broadcast_context = {}
permissions = {}
sticker_context = {}
welcome_context = {}
messages_from_users = {}

# Privilege levels
LEVELS = {'basic': 0, 'operator': 1, 'admin': 2, 'owner': 3}
def level(uid):
    if uid == config['developer_id']:
        return LEVELS['owner']
    if uid in config['admins']:
        return LEVELS['admin']
    return permissions.get(uid, LEVELS['basic'])

# ---------------- COMMAND HANDLERS ----------------
@bot.message_handler(commands=['admin'])
def basic_admin_panel(message):
    uid = message.chat.id
    if level(uid) < LEVELS['admin']:
        bot.send_message(uid, '🚫 لا تمتلك صلاحية.')
        return
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton('❌ حظر مستخدم', callback_data='ban_user'),
        InlineKeyboardButton('✅ إلغاء حظر', callback_data='unban_user'),
        InlineKeyboardButton('📢 اذاعة بدون تثبيت', callback_data='broadcast_no_pin'),
        InlineKeyboardButton('📌 اذاعة وتثبيت', callback_data='broadcast_with_pin'),
        InlineKeyboardButton('➕ إضافة آدمن', callback_data='add_admin'),
        InlineKeyboardButton('➖ إزالة آدمن', callback_data='remove_admin'),
        InlineKeyboardButton('🖼️ استعراض الصور', callback_data='view_images'),
        InlineKeyboardButton('👥 المستخدمون', callback_data='view_users'),
        InlineKeyboardButton('⚙️ إعدادات', callback_data='edit_config'),
        InlineKeyboardButton('🛠️ الإعدادات المتقدمة', callback_data='advanced_settings')
    )
    bot.send_message(uid, '🎛️ لوحة التحكم:', reply_markup=kb)

# Advanced panel function
def advanced_panel(uid):
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton('📊 إحصائيات', callback_data='stats'),
        InlineKeyboardButton('✏️ تعديل ترحيب', callback_data='edit_welcome'),
        InlineKeyboardButton('⏰ جدولة بث', callback_data='schedule_broadcast'),
        InlineKeyboardButton('💾 نسخ احتياطي', callback_data='backup'),
        InlineKeyboardButton('♻️ استعادة', callback_data='restore'),
        InlineKeyboardButton('🔑 صلاحيات', callback_data='manage_perms'),
        InlineKeyboardButton('⬅️ رجوع', callback_data='view_basic')
    )
    bot.send_message(uid, '🎛️ الإعدادات المتقدمة:', reply_markup=kb)

# ------------------- دوال الإدارة -------------------
def process_ban(message):
    try:
        uid = int(message.text)
        if uid not in config['banned_users']:
            config['banned_users'].append(uid)
            save_config()
            bot.send_message(message.chat.id, f'🚫 تم حظر المستخدم {uid}')
        else:
            bot.send_message(message.chat.id, 'المستخدم محظور بالفعل.')
    except Exception as e:
        bot.send_message(message.chat.id, 'خطأ في ايدي المستخدم.')

def process_unban(message):
    try:
        uid = int(message.text)
        if uid in config['banned_users']:
            config['banned_users'].remove(uid)
            save_config()
            bot.send_message(message.chat.id, f'✅ تم فك الحظر عن المستخدم {uid}')
        else:
            bot.send_message(message.chat.id, 'المستخدم غير محظور.')
    except Exception as e:
        bot.send_message(message.chat.id, 'خطأ في ايدي المستخدم.')

def process_broadcast_message(message):
    text = message.text or ''
    for u in users:
        try:
            bot.send_message(u['id'], text)
        except Exception:
            pass
    bot.send_message(message.chat.id, '📢 تم إرسال الإذاعة للجميع.')

def process_add_admin(message):
    try:
        uid = int(message.text)
        if uid not in config['admins']:
            config['admins'].append(uid)
            save_config()
            bot.send_message(message.chat.id, f'✅ تم إضافة {uid} كآدمن.')
        else:
            bot.send_message(message.chat.id, 'المستخدم آدمن بالفعل.')
    except Exception as e:
        bot.send_message(message.chat.id, 'خطأ في ايدي المستخدم.')

def process_remove_admin(message):
    try:
        uid = int(message.text)
        if uid in config['admins']:
            config['admins'].remove(uid)
            save_config()
            bot.send_message(message.chat.id, f'✅ تم إزالة {uid} من الآدمنات.')
        else:
            bot.send_message(message.chat.id, 'المستخدم ليس آدمن.')
    except Exception as e:
        bot.send_message(message.chat.id, 'خطأ في ايدي المستخدم.')

def process_change_password(message):
    config['password'] = message.text
    save_config()
    logout_all_users()
    bot.send_message(message.chat.id, '✅ تم تغيير كلمة السر وتم تسجيل خروج المستخدمين. يجب عليهم إدخال كلمة السر الجديدة.')

# ---------------- CALLBACK HANDLER ----------------
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    bot.answer_callback_query(call.id)
    uid = call.from_user.id
    data = call.data
    # User actions
    if data == 'colorize':
        images_to_color[uid] = True
        bot.send_message(uid, 'أرسل الصورة للتلوين.')
        return
    if data == 'contact_developer':
        bot.send_message(uid, 'أرسل رسالتك للمطور.')
        messages_from_users[call.message.message_id] = uid
        return
    # Panel switching
    if data == 'view_basic':
        return basic_admin_panel(call.message)
    if data == 'advanced_settings' and level(uid) >= LEVELS['admin']:
        return advanced_panel(uid)
    # Advanced actions
    if data == 'stats' and level(uid) >= LEVELS['operator']:
        stats_text = f"📊 إحصائيات:\n- مستخدمين: {len(users)}\n- آدمنات: {len(config['admins'])}\n- صور: {len(os.listdir(IMAGES_FOLDER))}"
        bot.send_message(uid, stats_text)
        return
    if data == 'edit_welcome' and level(uid) >= LEVELS['operator']:
        welcome_context[uid] = {}
        bot.send_message(uid, '✏️ ادخل رسالة الترحيب الجديدة:')
        return
    if data == 'schedule_broadcast' and level(uid) >= LEVELS['operator']:
        broadcast_context[uid] = {'pin': False}
        bot.send_message(uid, '⏰ ارسل وقت البث بصيغة YYYY-MM-DD HH:MM')
        return
    if data == 'backup' and level(uid) >= LEVELS['admin']:
        backup_config()
        bot.send_message(uid, '💾 تم النسخ الاحتياطي')
        return
    if data == 'restore' and level(uid) >= LEVELS['admin']:
        ok = restore_config()
        bot.send_message(uid, '✅ تم الاستعادة' if ok else '❌ لا يوجد نسخة')
        return
    if data == 'manage_perms' and level(uid) >= LEVELS['owner']:
        bot.send_message(uid, '🔑 تحت التطوير')
        return
    # Admin actions
    if level(uid) < LEVELS['admin']:
        bot.answer_callback_query(call.id, '🚫 ما عندك صلاحية.')
        return
    if data == 'ban_user':
        msg = bot.send_message(uid, 'ادخل ايدي الحظر:')
        bot.register_next_step_handler(msg, process_ban)
        return
    if data == 'unban_user':
        msg = bot.send_message(uid, 'ادخل ايدي فك الحظر:')
        bot.register_next_step_handler(msg, process_unban)
        return
    if data in ['broadcast_no_pin', 'broadcast_with_pin']:
        broadcast_context[uid] = {'pin': data == 'broadcast_with_pin'}
        msg = bot.send_message(uid, 'ارسل الآن النص/الوسائط للإذاعة:')
        bot.register_next_step_handler(msg, process_broadcast_message)
        return
    if data == 'add_admin':
        msg = bot.send_message(uid, 'ادخل ايدي لمنح آدمن:')
        bot.register_next_step_handler(msg, process_add_admin)
        return
    if data == 'remove_admin':
        msg = bot.send_message(uid, 'ادخل ايدي لإزالة آدمن:')
        bot.register_next_step_handler(msg, process_remove_admin)
        return
    if data == 'view_images':
        imgs = os.listdir(IMAGES_FOLDER)
        if not imgs:
            bot.send_message(uid, 'لا توجد صور.')
            return
        for img in imgs:
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton('حذف', callback_data=f'del_img:{img}'))
            bot.send_photo(uid, open(os.path.join(IMAGES_FOLDER, img), 'rb'), caption=img, reply_markup=kb)
        return
    if data.startswith('del_img:'):
        img = data.split(':', 1)[1]
        path = os.path.join(IMAGES_FOLDER, img)
        if os.path.exists(path): os.remove(path)
        bot.answer_callback_query(call.id, '🗑️ حذف!')
        return
    if data == 'view_users':
        lines = [f"- {u['id']} (@{u['username']})" for u in users]
        bot.send_message(uid, '👥 المستخدمون:\n' + ('\n'.join(lines) if lines else 'لا مستخدمين'))
        return
    if data == 'edit_config':
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton('👤 تغيير مطور', callback_data='edit_dev'),
            InlineKeyboardButton('🎟️ تعديل ستيكر', callback_data='edit_sticker'),
            InlineKeyboardButton('🗑️ مسح جميع الصور', callback_data='clear_images'),
            InlineKeyboardButton('👥 عرض آدمنات', callback_data='list_admins'),
            InlineKeyboardButton('🚫 عرض محظورين', callback_data='list_banned'),
            InlineKeyboardButton('🔒 إعدادات كلمة السر', callback_data='password_settings'),
            InlineKeyboardButton('⬅️ رجوع', callback_data='view_basic')
        )
        bot.send_message(uid, '⚙️ الإعدادات:', reply_markup=kb)
        return
    # إعدادات كلمة السر
    if data == 'password_settings' and level(uid) >= LEVELS['admin']:
        kb = InlineKeyboardMarkup(row_width=1)
        kb.add(
            InlineKeyboardButton('🔑 تغيير كلمة السر', callback_data='change_password'),
            InlineKeyboardButton('✅ تفعيل كلمة السر' if not config.get('password_enabled', False) else '❌ تعطيل كلمة السر', callback_data='toggle_password'),
            InlineKeyboardButton('⬅️ رجوع', callback_data='edit_config')
        )
        bot.send_message(uid, '🔒 إعدادات كلمة السر:', reply_markup=kb)
        return
    if data == 'change_password' and level(uid) >= LEVELS['admin']:
        msg = bot.send_message(uid, '📝 أدخل كلمة السر الجديدة:')
        bot.register_next_step_handler(msg, process_change_password)
        return
    if data == 'toggle_password' and level(uid) >= LEVELS['admin']:
        config['password_enabled'] = not config.get('password_enabled', False)
        save_config()
        state = '✅ تم تفعيل كلمة السر.' if config['password_enabled'] else '❌ تم تعطيل كلمة السر.'
        if config['password_enabled']:
            logout_all_users()
        bot.send_message(uid, state)
        return

# ---------------- PASSWORD CONTEXT HANDLER ----------------
# (تم تعريفها أعلاه مع دوال الإدارة)

# يمكنك إضافة باقي دوال البوت هنا حسب الحاجة

# لتشغيل البوت
if __name__ == "__main__":
    print("Bot is running...")
    bot.polling(none_stop=True)