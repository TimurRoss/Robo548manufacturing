"""
Конфигурационный файл для Telegram-бота 3DPrintQueue
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Токен бота (получить у @BotFather в Telegram)
# Читается из .env файла или переменной окружения
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Список user_id администраторов (через запятую или список)
# Читается из .env файла или переменной окружения
ADMIN_IDS = [
    int(admin_id.strip()) 
    for admin_id in os.getenv("ADMIN_IDS", "").split(",") 
    if admin_id.strip().isdigit()
]

# Путь к базе данных
DB_PATH = Path("database.db")

# Путь для хранения загруженных файлов
FILES_DIR = Path("files")
PHOTOS_DIR = FILES_DIR / "photos"
MODELS_DIR = FILES_DIR / "models"

# Создаем директории если их нет
FILES_DIR.mkdir(exist_ok=True)
PHOTOS_DIR.mkdir(exist_ok=True)
MODELS_DIR.mkdir(exist_ok=True)

# Статусы заказов
ORDER_STATUSES = {
    "pending": "В ожидании",
    "in_progress": "В работе",
    "ready": "Готов",
    "rejected": "Отклонен",
    "archived": "Архив"
}

# Максимальное количество заказов в архиве
ARCHIVE_MAX_SIZE = 25

# Допустимые расширения для 3D-моделей
ALLOWED_MODEL_EXTENSIONS = {".stl", ".stp", ".step"}

# Допустимые расширения для файлов лазерной резки
LASER_ALLOWED_MODEL_EXTENSIONS = {".dxf"}

# Справочник типов заказов
ORDER_TYPES = {
    "3d_print": "3D-печать",
    "laser_cut": "Лазерная резка",
}

# Сдвиг времени (UTC offset) для отображения времени создания заказов
try:
    TIMEZONE_OFFSET_HOURS = float(os.getenv("TIMEZONE_OFFSET_HOURS", "3"))
except ValueError:
    TIMEZONE_OFFSET_HOURS = 3.0

# Контакты технических специалистов для решения проблем
TECH_SUPPORT_CONTACTS = [
    {"name": "Россихн Тимур", "role": "Технический специалист", "contact": "@TimurRoss"},
    {"name": "Виктор Николаев", "role": "Технический специалист", "contact": "@vdnrobo"}
]

