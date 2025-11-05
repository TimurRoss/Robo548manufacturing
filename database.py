"""
Модуль для работы с базой данных SQLite
"""
import aiosqlite
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from loguru import logger
import config


class Database:
    def __init__(self, db_path: Path = config.DB_PATH):
        self.db_path = db_path

    async def init_db(self):
        """Инициализация базы данных и создание таблиц"""
        async with aiosqlite.connect(self.db_path) as db:
            # Таблица пользователей
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    first_name TEXT NOT NULL,
                    last_name TEXT NOT NULL,
                    username TEXT,
                    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Миграция: добавляем поле username если его нет
            try:
                cursor = await db.execute("PRAGMA table_info(users)")
                columns = [row[1] for row in await cursor.fetchall()]
                if 'username' not in columns:
                    await db.execute("ALTER TABLE users ADD COLUMN username TEXT")
                    await db.commit()
                    logger.info("Добавлено поле username в таблицу users")
            except Exception as e:
                logger.warning(f"Ошибка при добавлении поля username: {e}")

            # Таблица статусов (предопределенные)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS statuses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL
                )
            """)

            # Таблица материалов (объединенная: цвет + тип пластика)
            # Пример: "зеленый PETG", "синий PLA"
            await db.execute("""
                CREATE TABLE IF NOT EXISTS materials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL
                )
            """)

            # Таблица заказов
            await db.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    status_id INTEGER NOT NULL,
                    material_id INTEGER,
                    part_name TEXT,
                    photo_path TEXT,
                    model_path TEXT,
                    photo_caption TEXT,
                    original_filename TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (status_id) REFERENCES statuses(id),
                    FOREIGN KEY (material_id) REFERENCES materials(id)
                )
            """)

            await db.commit()

            # Миграция данных из старой структуры (если есть)
            try:
                await self._migrate_old_data(db)
            except Exception as e:
                logger.warning(f"Миграция данных: {e}")
            
            # Удаляем старую таблицу colors если она существует (после миграции)
            try:
                await db.execute("DROP TABLE IF EXISTS colors")
                await db.commit()
            except Exception as e:
                logger.warning(f"Удаление таблицы colors: {e}")

            # Добавляем начальные статусы
            await self._init_statuses(db)
            # Добавляем начальные материалы (комбинации цвет+тип)
            await self._init_default_materials(db)

            logger.info("База данных инициализирована")

    async def _init_statuses(self, db):
        """Инициализация статусов заказов"""
        statuses = [
            ("pending", "В ожидании"),
            ("in_progress", "В работе"),
            ("ready", "Готов"),
            ("rejected", "Отклонен")
        ]
        for code, name in statuses:
            await db.execute(
                "INSERT OR IGNORE INTO statuses (code, name) VALUES (?, ?)",
                (code, name)
            )
        await db.commit()

    async def _migrate_old_data(self, db):
        """Миграция данных из старой структуры (если есть)"""
        # Проверяем, есть ли старые данные в orders с color_id
        try:
            cursor = await db.execute("PRAGMA table_info(orders)")
            columns = [row[1] for row in await cursor.fetchall()]
            
            if 'color_id' in columns:
                # Если есть старые данные, создаем комбинации
                # Получаем все комбинации material_id + color_id
                cursor = await db.execute("""
                    SELECT DISTINCT o.material_id, o.color_id, m.name as material_name, c.name as color_name
                    FROM orders o
                    LEFT JOIN materials m ON o.material_id = m.id
                    LEFT JOIN colors c ON o.color_id = c.id
                    WHERE o.material_id IS NOT NULL AND o.color_id IS NOT NULL
                """)
                combinations = await cursor.fetchall()
                
                # Создаем комбинации и обновляем orders
                for material_id, color_id, material_name, color_name in combinations:
                    if material_name and color_name:
                        combined_name = f"{color_name.lower()} {material_name.upper()}"
                        # Проверяем, существует ли уже такая комбинация
                        cursor = await db.execute(
                            "SELECT id FROM materials WHERE name = ?",
                            (combined_name,)
                        )
                        existing = await cursor.fetchone()
                        
                        if not existing:
                            # Добавляем новую комбинацию
                            cursor = await db.execute(
                                "INSERT INTO materials (name) VALUES (?)",
                                (combined_name,)
                            )
                            new_material_id = cursor.lastrowid
                        else:
                            new_material_id = existing[0]
                        
                        # Обновляем заказы
                        await db.execute(
                            "UPDATE orders SET material_id = ?, color_id = NULL WHERE material_id = ? AND color_id = ?",
                            (new_material_id, material_id, color_id)
                        )
                
                # Удаляем столбец color_id из orders (SQLite не поддерживает DROP COLUMN напрямую)
                # Создаем новую таблицу без color_id
                await db.execute("""
                    CREATE TABLE orders_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        status_id INTEGER NOT NULL,
                        material_id INTEGER,
                        part_name TEXT,
                        photo_path TEXT,
                        model_path TEXT,
                        photo_caption TEXT,
                        original_filename TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users(user_id),
                        FOREIGN KEY (status_id) REFERENCES statuses(id),
                        FOREIGN KEY (material_id) REFERENCES materials(id)
                    )
                """)
                await db.execute("""
                    INSERT INTO orders_new 
                    (id, user_id, status_id, material_id, part_name, photo_path, model_path, photo_caption, original_filename, created_at)
                    SELECT id, user_id, status_id, material_id, part_name, photo_path, model_path, photo_caption, original_filename, created_at
                    FROM orders
                """)
                await db.execute("DROP TABLE orders")
                await db.execute("ALTER TABLE orders_new RENAME TO orders")
                
                await db.commit()
                logger.info("Миграция данных выполнена успешно")
        except Exception as e:
            logger.warning(f"Ошибка при миграции: {e}")

    async def _init_default_materials(self, db):
        """Инициализация начальных материалов (комбинации цвет+тип)"""
        default_materials = [
            "белый PLA",
            "черный PLA",
            "красный PLA",
            "синий PLA",
            "зеленый PLA",
            "желтый PLA",
            "белый PETG",
            "черный PETG",
            "синий PETG",
            "белый ABS",
            "черный ABS"
        ]
        for material in default_materials:
            await db.execute(
                "INSERT OR IGNORE INTO materials (name) VALUES (?)",
                (material,)
            )
        await db.commit()

    async def get_or_create_user(self, user_id: int, first_name: str, last_name: str, username: Optional[str] = None) -> Dict[str, Any]:
        """Получить или создать пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,)
            )
            user = await cursor.fetchone()

            if user:
                # Преобразуем Row в словарь для работы
                user_dict = dict(user)
                # Обновляем username если он изменился
                if username and username != user_dict.get('username'):
                    await db.execute(
                        "UPDATE users SET username = ? WHERE user_id = ?",
                        (username, user_id)
                    )
                    await db.commit()
                    logger.info(f"Обновлен username для пользователя {user_id}: {username}")
                    # Получаем обновленного пользователя
                    cursor = await db.execute(
                        "SELECT * FROM users WHERE user_id = ?",
                        (user_id,)
                    )
                    user = await cursor.fetchone()
                    user_dict = dict(user)
                return user_dict

            await db.execute(
                "INSERT INTO users (user_id, first_name, last_name, username) VALUES (?, ?, ?, ?)",
                (user_id, first_name, last_name, username)
            )
            await db.commit()
            logger.info(f"Создан новый пользователь: {user_id} - {first_name} {last_name} (@{username if username else 'без username'})")

            cursor = await db.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,)
            )
            user = await cursor.fetchone()
            return dict(user)

    async def is_user_registered(self, user_id: int) -> bool:
        """Проверить, зарегистрирован ли пользователь"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT 1 FROM users WHERE user_id = ?",
                (user_id,)
            )
            return await cursor.fetchone() is not None

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получить пользователя по ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM users WHERE user_id = ?",
                (user_id,)
            )
            user = await cursor.fetchone()
            return dict(user) if user else None

    async def create_order(
        self,
        user_id: int,
        material_id: int,
        part_name: str,
        photo_path: str,
        model_path: str,
        photo_caption: Optional[str] = None,
        original_filename: str = ""
    ) -> int:
        """Создать новый заказ"""
        async with aiosqlite.connect(self.db_path) as db:
            # Получаем ID статуса "В ожидании"
            cursor = await db.execute(
                "SELECT id FROM statuses WHERE code = 'pending'"
            )
            status_row = await cursor.fetchone()
            status_id = status_row[0]

            cursor = await db.execute("""
                INSERT INTO orders 
                (user_id, status_id, material_id, part_name, photo_path, model_path, photo_caption, original_filename)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, status_id, material_id, part_name, photo_path, model_path, photo_caption, original_filename))

            await db.commit()
            order_id = cursor.lastrowid
            logger.info(f"Создан заказ №{order_id} для пользователя {user_id}")
            return order_id

    async def get_order(self, order_id: int) -> Optional[Dict[str, Any]]:
        """Получить заказ по ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT o.*, 
                       u.first_name, u.last_name, u.user_id, u.username,
                       s.code as status_code, s.name as status_name,
                       m.name as material_name
                FROM orders o
                JOIN users u ON o.user_id = u.user_id
                JOIN statuses s ON o.status_id = s.id
                LEFT JOIN materials m ON o.material_id = m.id
                WHERE o.id = ?
            """, (order_id,))
            order = await cursor.fetchone()
            return dict(order) if order else None

    async def get_user_orders(self, user_id: int) -> List[Dict[str, Any]]:
        """Получить все заказы пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT o.*, 
                       s.code as status_code, s.name as status_name,
                       m.name as material_name
                FROM orders o
                JOIN statuses s ON o.status_id = s.id
                LEFT JOIN materials m ON o.material_id = m.id
                WHERE o.user_id = ?
                ORDER BY o.created_at DESC
            """, (user_id,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_orders_by_status(self, status_code: Optional[str] = None) -> List[Dict[str, Any]]:
        """Получить заказы по статусу (или все, если status_code=None)"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if status_code:
                cursor = await db.execute("""
                    SELECT o.*, 
                           u.first_name, u.last_name, u.user_id, u.username,
                           s.code as status_code, s.name as status_name,
                           m.name as material_name
                    FROM orders o
                    JOIN users u ON o.user_id = u.user_id
                    JOIN statuses s ON o.status_id = s.id
                    LEFT JOIN materials m ON o.material_id = m.id
                    WHERE s.code = ?
                    ORDER BY o.created_at DESC
                """, (status_code,))
            else:
                cursor = await db.execute("""
                    SELECT o.*, 
                           u.first_name, u.last_name, u.user_id, u.username,
                           s.code as status_code, s.name as status_name,
                           m.name as material_name
                    FROM orders o
                    JOIN users u ON o.user_id = u.user_id
                    JOIN statuses s ON o.status_id = s.id
                    LEFT JOIN materials m ON o.material_id = m.id
                    ORDER BY o.created_at DESC
                """)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def update_order_status(self, order_id: int, status_code: str) -> bool:
        """Обновить статус заказа"""
        async with aiosqlite.connect(self.db_path) as db:
            # Получаем ID статуса
            cursor = await db.execute(
                "SELECT id FROM statuses WHERE code = ?",
                (status_code,)
            )
            status_row = await cursor.fetchone()
            if not status_row:
                return False

            status_id = status_row[0]
            await db.execute(
                "UPDATE orders SET status_id = ? WHERE id = ?",
                (status_id, order_id)
            )
            await db.commit()
            logger.info(f"Статус заказа №{order_id} изменен на {status_code}")
            return True

    async def get_all_materials(self) -> List[Dict[str, Any]]:
        """Получить все материалы (комбинации цвет+тип)"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM materials ORDER BY name")
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def add_material(self, name: str) -> bool:
        """Добавить новый материал (формат: "цвет тип", например "зеленый PETG")"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                # Нормализуем название (первая буква цвета заглавная, тип заглавными)
                await db.execute(
                    "INSERT INTO materials (name) VALUES (?)",
                    (name.strip(),)
                )
                await db.commit()
                logger.info(f"Добавлен материал: {name}")
                return True
            except aiosqlite.IntegrityError:
                return False

    async def delete_material(self, material_id: int) -> bool:
        """Удалить материал"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM materials WHERE id = ?",
                (material_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def get_material_id_by_name(self, name: str) -> Optional[int]:
        """Получить ID материала по имени"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT id FROM materials WHERE name = ?",
                (name,)
            )
            row = await cursor.fetchone()
            return row[0] if row else None


# Глобальный экземпляр базы данных
db = Database()

