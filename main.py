import logging
import os
import asyncio
import nest_asyncio
import requests
import pdfplumber
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

nest_asyncio.apply()

# Логирование для отслеживания работы
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Этапы разговора
SELECTING_ACTION, GETTING_INFO = range(2)

# Глобальная переменная для хранения данных
data = {}

# Ссылка на облачное хранилище
CLOUD_URL = 'https://cloud.mail.ru/public/QikY/MNEL7hD2y'
DOWNLOAD_FOLDER = 'pdf_files'

# Функция для команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["Расписание группы", "Расписание преподавателя"],
        ["Расписание на день"],
    ]
    reply_markup = ReplyKeyboardMarkup(
        keyboard, one_time_keyboard=True, resize_keyboard=True
    )
    await update.message.reply_text(
        "Привет! Я бот для расписания. Выберите действие:", reply_markup=reply_markup
    )
    return SELECTING_ACTION

# Функция для команды /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Команды:\n"
        "/schedule_group - Расписание для группы\n"
        "/schedule_teacher - Расписание для преподавателя\n"
        "/schedule_day - Расписание на день\n"
        "/help - помощь по командам"
    )

# Обработка выбора действия
async def handle_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = update.message.text
    context.user_data["action"] = action

    if action == "Расписание группы":
        await update.message.reply_text("Введите номер группы:")
    elif action == "Расписание преподавателя":
        await update.message.reply_text("Введите имя преподавателя:")
    elif action == "Расписание на день":
        await update.message.reply_text("Введите дату (в формате ДД.ММ.ГГГГ):")
    else:
        await update.message.reply_text("Неверный выбор. Попробуйте снова.")
        return SELECTING_ACTION

    return GETTING_INFO

# Обработка информации от пользователя
async def handle_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info = update.message.text
    action = context.user_data.get("action")

    if action == "Расписание группы":
        schedule = get_group_schedule(info)
    elif action == "Расписание преподавателя":
        schedule = get_teacher_schedule(info)
    elif action == "Расписание на день":
        schedule = get_day_schedule(info)
    else:
        schedule = "Произошла ошибка. Пожалуйста, начните сначала."

    await update.message.reply_text(schedule)
    return ConversationHandler.END

# Функция отмены
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Действие отменено.")
    return ConversationHandler.END

# Функция для загрузки PDF-файлов из облачного хранилища
def download_pdfs(url, download_folder):
    if not os.path.exists(download_folder):
        os.makedirs(download_folder)

    response = requests.get(url)
    if response.status_code != 200:
        print(f"Не удалось получить доступ к {url}")
        return

    soup = BeautifulSoup(response.content, 'lxml')

    # Ищем все ссылки на файлы и папки
    links = soup.find_all('a', href=True)
    for link in links:
        href = link['href']
        full_url = urljoin(url, href)

        if href.endswith('.pdf'):
            # Скачиваем PDF-файл
            file_name = os.path.basename(href)
            file_path = os.path.join(download_folder, file_name)

            if not os.path.exists(file_path):
                print(f"Скачиваем {file_name}...")
                file_response = requests.get(full_url)
                if file_response.status_code == 200:
                    with open(file_path, 'wb') as f:
                        f.write(file_response.content)
                    print(f"{file_name} успешно скачан.")
                else:
                    print(f"Не удалось скачать {file_name}.")
            else:
                print(f"{file_name} уже существует.")
        elif 'public' in href and href != url:
            # Если это папка, рекурсивно обходим её
            download_pdfs(full_url, download_folder)

# Функция для извлечения текста из PDF-файлов
def extract_text_from_pdf(file_path):
    text = ''
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text
    return text

# Асинхронная функция для обновления данных
async def update_data():
    print("Обновление данных...")
    # Скачиваем PDF-файлы
    download_pdfs(CLOUD_URL, DOWNLOAD_FOLDER)

    # Извлекаем данные из PDF-файлов
    global data
    data = {}  # Сбрасываем предыдущие данные
    for filename in os.listdir(DOWNLOAD_FOLDER):
        if filename.endswith('.pdf'):
            file_path = os.path.join(DOWNLOAD_FOLDER, filename)
            text = extract_text_from_pdf(file_path)
            # Здесь можно добавить логику парсинга текста и извлечения нужной информации
            data[filename] = text
    print("Данные обновлены.")

# Функции для получения расписания
def get_group_schedule(group_number):
    # Поиск расписания группы в данных
    schedules = []
    for filename, text in data.items():
        if group_number in text:
            schedules.append(f"Источник: {filename}\n{text}")
    if schedules:
        return "\n\n".join(schedules)
    else:
        return f"Расписание для группы {group_number} не найдено."

def get_teacher_schedule(teacher_name):
    # Поиск расписания преподавателя в данных
    schedules = []
    for filename, text in data.items():
        if teacher_name in text:
            schedules.append(f"Источник: {filename}\n{text}")
    if schedules:
        return "\n\n".join(schedules)
    else:
        return f"Расписание для преподавателя {teacher_name} не найдено."

def get_day_schedule(date):
    # Поиск расписания на определенную дату в данных
    schedules = []
    for filename, text in data.items():
        if date in text:
            schedules.append(f"Источник: {filename}\n{text}")
    if schedules:
        return "\n\n".join(schedules)
    else:
        return f"Расписание на дату {date} не найдено."

# Основная функция, запускающая бота
async def main():
    # Замените 'YOUR_BOT_TOKEN' на токен вашего бота
    TOKEN = '6461636985:AAGHky0hJqlgOOQB2BzVilkAR6MLBwQsSIc'

    # Создание приложения
    application = Application.builder().token(TOKEN).build()

    # Создание планировщика задач
    scheduler = AsyncIOScheduler()
    scheduler.add_job(update_data, 'interval', hours=24)  # Обновление данных каждые 24 часа
    scheduler.start()

    # Выполняем первоначальное обновление данных
    await update_data()

    # Создание ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECTING_ACTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_selection)
            ],
            GETTING_INFO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_info)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    # Обработка команд
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("help", help_command))

    # Запуск бота
    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
