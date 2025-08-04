import re
from datetime import datetime
import pytz
from telethon.sync import TelegramClient, events
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from pybit.unified_trading import HTTP
import json
import os
import telebot
from decimal import Decimal


TOKEN = "________"  #token from telebot
bot = telebot.TeleBot(TOKEN)

#telegram api data
API_ID = ___________
API_HASH = '______________'
SESSION_NAME = "my_session"
CHANNEL = '@TokenSplashBybit'

# Регулярка для парсинга токена и Result даты
POST_REGEX = r'^(?P<token>\w+)\n.*?Result (?P<result_date>\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}) UTC' #парсинг из канала @TokenSplashBybit
TRADE_AMOUNT = 10  # USDT
TP1_PCT = 0.03
TP2_PCT = 0.06
STOP_LOSS_PCT = 0.02
scheduler = BackgroundScheduler(timezone=pytz.utc)
scheduler.start()
user_states = {}

USER_DATA_PATH = "user_data_tg"
os.makedirs(USER_DATA_PATH, exist_ok=True)
#GET USER + SAVE USER INFO
# ======================================================================================================================
def get_user_file(user_id):
    return os.path.join(USER_DATA_PATH, f"{user_id}.json")

def load_user_data(user_id):
    try:
        with open(get_user_file(user_id), 'r') as f:
            return json.load(f)
    except:
        return {}

def save_user_data(user_id, data):
    with open(get_user_file(user_id), 'w') as f:
        json.dump(data, f)


def get_all_user_ids():
    user_ids = []
    for filename in os.listdir(USER_DATA_PATH):
        if filename.endswith(".json"):
            try:
                user_id = int(filename.split(".")[0])
                user_ids.append(user_id)
            except:
                continue
    return user_ids

def notify_all_enabled_users(token):
    user_ids = get_all_user_ids()
    for uid in user_ids:
        data = load_user_data(uid)
        if data.get("bot_enabled"):
            long_token(uid, token_symbol=token)
            
            
            
def get_menu_markup(user_id):
    data = load_user_data(user_id)
    bot_enabled = data.get("bot_enabled", False)
    state_button = "🟢 Бот включен" if bot_enabled else "🔴 Бот выключен"

    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(state_button, "ℹ️ Информация о боте")
    markup.row("⚙️ Настройки")
    return markup




settings_markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
settings_markup.row("API Key", "secret")
settings_markup.row("Leverage", "Margin")
settings_markup.row("Назад")


#MATH
def count_decimal_places(number: float) -> int:
    s = f"{number:.16f}".rstrip('0')  # преобразуем с запасом знаков, убираем хвостящие нули
    if '.' in s:
        return len(s.split('.')[1])
    else:
        return 0
    
    
#КОМАНДЫ ДЛЯ БОТА
#=======================================================================================================================                         
@bot.message_handler(func=lambda msg: msg.text in ["🟢 Бот включен", "🔴 Бот выключен"])
def toggle_bot_state(message):
    user_id = message.chat.id
    data = load_user_data(user_id)
    current_state = data.get("bot_enabled", False)
    data["bot_enabled"] = not current_state
    save_user_data(user_id, data)
    
    status = "включен" if data["bot_enabled"] else "выключен"
    bot.send_message(user_id, f"Бот теперь {status}.", reply_markup=get_menu_markup(user_id))




@bot.message_handler(func=lambda msg: msg.text == "ℹ️ Информация о боте")
def bot_info(message):
    user_id = message.chat.id
    info_text = (
        "Это торговый бот для биржи Bybit, торгующий в шорт листинги.\n"
        "Вы можете включать и выключать бота, а также настраивать параметры в разделе Настройки. Для грамотной работы бота необходимо обязательно указать всё.\n"
        "Если нужна помощь — обращайтесь @perpetual_god."
    )
    bot.send_message(user_id, info_text, reply_markup=get_menu_markup(user_id))

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.chat.id
    bot.send_message(user_id, "Добро пожаловать! Выберите действие:", reply_markup=get_menu_markup(user_id))
 

@bot.message_handler(func=lambda msg: msg.text in ["⚙️ Настройки"])
def handle_settings_menu(message):
    user_id = message.chat.id
    bot.send_message(user_id, "Выберите параметр:", reply_markup=settings_markup)

@bot.message_handler(func=lambda msg: msg.text in ["API Key", "secret", "Leverage", "Margin", "Stop", "Take"])
def ask_for_value(message):
    user_id = message.chat.id
    key = message.text.lower().replace(" ", "_")
    
    data = load_user_data(user_id)
    current_value = data.get(key, "(не задано)")
    
    user_states[user_id] = key
    if message.text == 'Stop' or message.text == 'Take':
        bot.send_message(user_id, f"Установленный {message.text} для позиции: {current_value}% чистого движения\n\nВведите новое значение:")
    else:
        bot.send_message(user_id, f"Текущее значение {message.text}: {current_value}\n\nВведите новое значение:")



@bot.message_handler(func=lambda msg: msg.text == "Назад")
def back_to_menu(message):
    user_id = message.chat.id
    bot.send_message(user_id, "Вы вернулись в меню", reply_markup=get_menu_markup(user_id))
#============================================================================================================================


def fetch_new_tokens():
    new_tokens = []
    try:
        with TelegramClient(SESSION_NAME, API_ID, API_HASH) as client:
            print("[Telethon] Получаем последние 50 сообщений из канала...")
            messages = client.get_messages(CHANNEL, limit=50)
            print(f"[Telethon] Всего сообщений получено: {len(messages)}")

            for msg in messages:
                if msg.text is None:
                    continue

                match = re.search(POST_REGEX, msg.text, re.DOTALL)
                if not match:
                    continue

                symbol = match.group('token').strip()
                result_date_str = match.group('result_date').strip()

                try:
                    result_dt = datetime.strptime(result_date_str, "%d.%m.%Y %H:%M")
                    result_dt = pytz.utc.localize(result_dt)
                except ValueError:
                    print(f"[Telethon] Невозможно разобрать дату: {result_date_str}")
                    continue

                now = datetime.utcnow().replace(tzinfo=pytz.utc)
                if result_dt > now:
                    print(f"[Telethon] Найден токен для планирования: {symbol} (Result: {result_dt})")
                    new_tokens.append({
                        "symbol": symbol,
                        "result_time": result_dt
                    })
    except Exception as e:
        print(f"[Telethon] Ошибка при получении токенов: {e}")

    return new_tokens


def schedule_long(token_info):
    symbol = token_info["symbol"]
    run_time = token_info["result_time"]

    # Найти все задачи, которые начинаются с "long_{symbol}_"
    existing_jobs = [job for job in scheduler.get_jobs() if job.id.startswith(f"long_{symbol}_")]
    if existing_jobs:
        print(f"[Scheduler] Задачи для {symbol} уже запланированы, пропускаем добавление.")
        return

    job_id = f"long_{symbol}_{run_time.strftime('%Y%m%d%H%M')}"
    print(f"[Scheduler] Планируем лонг для {symbol} на {run_time} (UTC)")
    scheduler.add_job(notify_all_enabled_users, trigger=DateTrigger(run_date=run_time), args=[symbol], id=job_id)

def long_token(user_id, token_symbol):
    print(f"▶️ Лонг {token_symbol}")
    try:
        # 1. Купить 70%
        data = load_user_data(user_id)
        session = HTTP(api_key=data['api_key'], api_secret=data['secret'], recv_window=60000)
        
        res = session.get_tickers(category="linear", symbol=token_symbol)
        
        leverage = int(data.get("leverage", 5))
        margin = float(data.get("margin", 10))
        price = float(res['result']['list'][0]['lastPrice'])
        raw_qty = leverage * margin / price
        
        qty = get_valid_qty(session, token_symbol, raw_qty)
        
        # 2. Выставить лимитные тейк-профиты
        mark_price = float(session.get_tickers(category="linear", symbol=token_symbol)["result"]["list"][0]["lastPrice"])
        precision = int(count_decimal_places(price))
        tp1 = round(mark_price * (1 + TP1_PCT), precision)
        tp2 = round(mark_price * (1 + TP2_PCT), precision)
        sl = round(mark_price * (1 - STOP_LOSS_PCT), precision)
        
        try:
            session.place_order(
                category="linear",
                symbol=token_symbol,
                side="Buy",
                order_type="Market",
                qty=round(qty * 0.7, 3),
                reduce_only=False,
                time_in_force="GoodTillCancel",
                stopLoss = sl
            )
        except Exception as e:
            try:
                session.place_order(
                category="linear",
                symbol=token_symbol,
                side="Buy",
                order_type="Market",
                qty=round(qty * 0.7, 1),
                reduce_only=False,
                time_in_force="GoodTillCancel",
                stopLoss = sl
            )
            except Exception as r:
                print(r)

    

        # 33% тейк на 3%
        session.place_order(
            category="linear",
            symbol=token_symbol,
            side="Sell",
            order_type="Limit",
            qty=round(qty * 0.4, 2),
            price=tp1,
            reduce_only=True,
            time_in_force="GoodTillCancel"
        )

        # 33% тейк на 6%
        session.place_order(
            category="linear",
            symbol=token_symbol,
            side="Sell",
            order_type="Limit",
            qty=round(qty * 0.3, 2),
            price=tp2,
            reduce_only=True,
            time_in_force="GoodTillCancel"
        )

        # Стоп на остаток
        session.place_order(
            category="linear",
            symbol=token_symbol,
            side="Sell",
            order_type="StopMarket",
            stop_px=sl,
            qty=round(qty * 0.3, 2),
            reduce_only=True,
            time_in_force="GoodTillCancel",
            trigger_direction=1
        )
        
    except Exception as err:
        print('Error while placing order', err)
    
def get_valid_qty(session, symbol, raw_qty):
    try:
        info = session.get_instruments_info(category="linear", symbol=symbol)
        
        if 'result' not in info or 'list' not in info['result'] or not info['result']['list']:
            print(f"❌ Пара {symbol} не найдена в get_instruments_info.")
            return None

        lot_filter = info['result']['list'][0].get('lotSizeFilter', {})
        step = float(lot_filter.get('qtyStep', 0))
        min_qty = float(lot_filter.get('minOrderQty', 0))

        if step == 0:
            print(f"❌ qtyStep равен 0 для {symbol}")
            return None

        qty = max(raw_qty, min_qty)
        precision = abs(Decimal(str(step)).as_tuple().exponent)
        valid_qty = round(qty, precision-1)
       
            
        print(f"qty: {valid_qty}, step: {step}, min_qty: {min_qty}")
        return valid_qty
    except Exception as e:
        print(f"⚠️ Ошибка получения допустимого объема для {symbol}: {e}")
        return None    

def main():
    # Получаем и планируем уже существующие токены
    tokens = fetch_new_tokens()
    for token_info in tokens:
        schedule_long(token_info)

    # Запускаем клиент Telethon для мониторинга новых сообщений
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    client.start()

    @client.on(events.NewMessage(chats=CHANNEL))
    async def new_message_handler(event):
        text = event.message.message
        if text is None:
            return
        match = re.search(POST_REGEX, text, re.DOTALL)
        if not match:
            return

        symbol = match.group('token').strip()
        result_date_str = match.group('result_date').strip()
        try:
            result_dt = datetime.strptime(result_date_str, "%d.%m.%Y %H:%M")
            result_dt = pytz.utc.localize(result_dt)
        except ValueError:
            print(f"[Telethon] Невозможно разобрать дату из нового сообщения: {result_date_str}")
            return

        now = datetime.utcnow().replace(tzinfo=pytz.utc)
        if result_dt > now:
            print(f"[Telethon] Новый токен из чата для планирования: {symbol} (Result: {result_dt})")
            schedule_long({"symbol": symbol, "result_time": result_dt})

    print("[Telethon] Запущен мониторинг новых сообщений...")
    client.run_until_disconnected()

# ================= ОБРАБОТЧИК ДЛЯ ВВОДА ЗНАЧЕНИЙ =====================
@bot.message_handler(func=lambda msg: True)
def catch_input(message):
    user_id = message.chat.id
    if user_id in user_states:
        key = user_states.pop(user_id)
        data = load_user_data(user_id)
        data[key] = message.text.strip()
        save_user_data(user_id, data)
        bot.send_message(user_id, f"{key} сохранено. Выберите следующий параметр:", reply_markup=settings_markup)
        
        
def main():
    print("[Init] Получаем токены...")
    for token in fetch_new_tokens():
        schedule_long(token)
    print("[Init] Запускаем polling и scheduler")
    bot.polling(none_stop=True)

if __name__ == "__main__":
    main()





