"""
Модуль для работы с базой данных SQLite
"""
import aiosqlite
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple, Sequence
from loguru import logger
import config


class Database:
    def __init__(self, db_path: Path = config.DB_PATH):
        self.db_path = db_path

    _DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
    _DATETIME_MICRO_FORMAT = "%Y-%m-%d %H:%M:%S.%f"
    _UTC_OFFSET = timedelta(hours=config.TIMEZONE_OFFSET_HOURS)

    @classmethod
    def _format_created_at(cls, created_at: Optional[str]) -> Optional[str]:
        if not created_at:
            return created_at
        for fmt in (cls._DATETIME_FORMAT, cls._DATETIME_MICRO_FORMAT):
            try:
                dt = datetime.strptime(created_at, fmt)
                dt += cls._UTC_OFFSET
                return dt.strftime(cls._DATETIME_FORMAT)
            except ValueError:
                continue
        return created_at

    @classmethod
    def _order_row_to_dict(cls, row) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        data = dict(row)
        formatted = cls._format_created_at(data.get("created_at"))
        if formatted:
            data["created_at"] = formatted
        return data

    @classmethod
    def _order_rows_to_list(cls, rows: List[Any]) -> List[Dict[str, Any]]:
        return [cls._order_row_to_dict(row) for row in rows if row is not None]

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
                    name TEXT UNIQUE NOT NULL,
                    type TEXT NOT NULL DEFAULT '3d_print',
                    is_available INTEGER NOT NULL DEFAULT 1
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
                    rejection_reason TEXT,
                    last_reminder_time TIMESTAMP,
                    comment TEXT,
                    order_type TEXT NOT NULL DEFAULT '3d_print',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (status_id) REFERENCES statuses(id),
                    FOREIGN KEY (material_id) REFERENCES materials(id)
                )
            """)
            
            # Миграция: добавляем поля если их нет
            try:
                cursor = await db.execute("PRAGMA table_info(orders)")
                columns = [row[1] for row in await cursor.fetchall()]
                
                if 'rejection_reason' not in columns:
                    await db.execute("ALTER TABLE orders ADD COLUMN rejection_reason TEXT")
                    await db.commit()
                    logger.info("Добавлено поле rejection_reason в таблицу orders")
                
                if 'last_reminder_time' not in columns:
                    await db.execute("ALTER TABLE orders ADD COLUMN last_reminder_time TIMESTAMP")
                    await db.commit()
                    logger.info("Добавлено поле last_reminder_time в таблицу orders")
                
                if 'comment' not in columns:
                    await db.execute("ALTER TABLE orders ADD COLUMN comment TEXT")
                    await db.commit()
                    logger.info("Добавлено поле comment в таблицу orders")

                if 'order_type' not in columns:
                    await db.execute("ALTER TABLE orders ADD COLUMN order_type TEXT NOT NULL DEFAULT '3d_print'")
                    await db.commit()
                    logger.info("Добавлено поле order_type в таблицу orders")

                cursor = await db.execute("PRAGMA table_info(materials)")
                material_columns = [row[1] for row in await cursor.fetchall()]

                if 'type' not in material_columns:
                    await db.execute("ALTER TABLE materials ADD COLUMN type TEXT NOT NULL DEFAULT '3d_print'")
                    await db.commit()
                    logger.info("Добавлено поле type в таблицу materials")
                if 'is_available' not in material_columns:
                    await db.execute("ALTER TABLE materials ADD COLUMN is_available INTEGER NOT NULL DEFAULT 1")
                    await db.commit()
                    logger.info("Добавлено поле is_available в таблицу materials")
            except Exception as e:
                logger.warning(f"Ошибка при добавлении полей в orders или materials: {e}")

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
            # await self._init_default_materials(db)

            logger.info("База данных инициализирована")

    async def _init_statuses(self, db):
        """Инициализация статусов заказов"""
        statuses = [
            ("pending", "В ожидании"),
            ("in_progress", "В работе"),
            ("ready", "Готов"),
            ("rejected", "Отклонен"),
            ("archived", "Архив")
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

    async def get_all_user_ids(self) -> List[int]:
        """Получить список всех ID пользователей бота"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT user_id FROM users")
            rows = await cursor.fetchall()
            return [int(row[0]) for row in rows if row and row[0] is not None]

    async def create_order(
        self,
        user_id: int,
        material_id: int,
        part_name: str,
        photo_path: str,
        model_path: str,
        photo_caption: Optional[str] = None,
        original_filename: str = "",
        comment: Optional[str] = None,
        order_type: str = '3d_print'
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
                (user_id, status_id, material_id, part_name, photo_path, model_path, photo_caption, original_filename, comment, order_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, status_id, material_id, part_name, photo_path, model_path, photo_caption, original_filename, comment, order_type))

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
            return self._order_row_to_dict(order)

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
            return self._order_rows_to_list(rows)

    async def get_orders_statistics(self, order_type: Optional[str] = None) -> Dict[str, int]:
        """Получить статистику по заказам по статусам (без архива и rejected)"""
        async with aiosqlite.connect(self.db_path) as db:
            params: Tuple[Any, ...] = ()
            join_filter = ""
            if order_type:
                join_filter = " AND o.order_type = ?"
                params = (order_type,)

            cursor = await db.execute(
                f"""
                SELECT s.code, COUNT(o.id) as count
                FROM statuses s
                LEFT JOIN orders o ON s.id = o.status_id
                    {join_filter}
                WHERE s.code != 'archived' AND s.code != 'rejected'
                GROUP BY s.code
                """,
                params
            )
            rows = await cursor.fetchall()
            stats = {}
            total = 0
            for row in rows:
                code = row[0]
                count = row[1] if row[1] else 0
                stats[code] = count
                total += count
            stats['all'] = total
            return stats

    async def get_orders_by_status(self, status_code: Optional[str] = None, order_type: Optional[str] = None, limit: int = None, offset: int = 0) -> List[Dict[str, Any]]:
        """Получить заказы по статусу (или все, если status_code=None, без архива)"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if status_code:
                # Для статусов "pending" и "in_progress" сортируем в хронологическом порядке (старые сверху)
                # Для остальных - по убыванию (новые сначала)
                if status_code in ['pending', 'in_progress']:
                    order_by = "ORDER BY o.created_at ASC"
                else:
                    order_by = "ORDER BY o.created_at DESC"

                query = f"""
                    SELECT o.*, 
                           u.first_name, u.last_name, u.user_id, u.username,
                           s.code as status_code, s.name as status_name,
                           m.name as material_name
                    FROM orders o
                    JOIN users u ON o.user_id = u.user_id
                    JOIN statuses s ON o.status_id = s.id
                    LEFT JOIN materials m ON o.material_id = m.id
                    WHERE s.code = ?
                """
                params_list: List[Any] = [status_code]
                if order_type:
                    query += " AND o.order_type = ?"
                    params_list.append(order_type)
                query += f"\n                    {order_by}"
                params = tuple(params_list)
            else:
                query = """
                    SELECT o.*, 
                           u.first_name, u.last_name, u.user_id, u.username,
                           s.code as status_code, s.name as status_name,
                           m.name as material_name
                    FROM orders o
                    JOIN users u ON o.user_id = u.user_id
                    JOIN statuses s ON o.status_id = s.id
                    LEFT JOIN materials m ON o.material_id = m.id
                    WHERE s.code != 'archived' AND s.code != 'rejected'
                    ORDER BY o.created_at DESC
                """
                params = ()
                if order_type:
                    query = query.replace("WHERE s.code != 'archived' AND s.code != 'rejected'",
                                           "WHERE s.code != 'archived' AND s.code != 'rejected' AND o.order_type = ?")
                    params = (order_type,)
            
            if limit:
                query += f" LIMIT {limit} OFFSET {offset}"
            
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            return self._order_rows_to_list(rows)
    
    async def count_orders_by_status(self, status_code: Optional[str] = None, order_type: Optional[str] = None) -> int:
        """Получить количество заказов по статусу"""
        async with aiosqlite.connect(self.db_path) as db:
            if status_code:
                query = """
                    SELECT COUNT(*) FROM orders o
                    JOIN statuses s ON o.status_id = s.id
                    WHERE s.code = ?
                """
                params: Tuple[Any, ...] = (status_code,)
                if order_type:
                    query += " AND o.order_type = ?"
                    params += (order_type,)
                cursor = await db.execute(query, params)
            else:
                query = """
                    SELECT COUNT(*) FROM orders o
                    JOIN statuses s ON o.status_id = s.id
                    WHERE s.code != 'archived' AND s.code != 'rejected'
                """
                params = ()
                if order_type:
                    query += " AND o.order_type = ?"
                    params = (order_type,)
                cursor = await db.execute(query, params)
            result = await cursor.fetchone()
            return result[0] if result else 0

    async def get_orders_by_material(
        self,
        material_id: int,
        statuses: Optional[Sequence[str]] = None,
        order_type: Optional[str] = None,
        limit: int | None = None,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Получить заказы по материалу с опциональным фильтром по статусам"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            base_query = """
                SELECT o.*,
                       u.first_name, u.last_name, u.user_id, u.username,
                       s.code as status_code, s.name as status_name,
                       m.name as material_name
                FROM orders o
                JOIN users u ON o.user_id = u.user_id
                JOIN statuses s ON o.status_id = s.id
                LEFT JOIN materials m ON o.material_id = m.id
                WHERE o.material_id = ?
            """

            params: List[Any] = [material_id]

            if statuses:
                placeholders = ",".join("?" for _ in statuses)
                base_query += f" AND s.code IN ({placeholders})"
                params.extend(statuses)
            else:
                base_query += " AND s.code != 'archived' AND s.code != 'rejected'"

            if order_type:
                base_query += " AND o.order_type = ?"
                params.append(order_type)

            if statuses and all(status in {"pending", "in_progress"} for status in statuses):
                base_query += "\n                ORDER BY o.created_at ASC"
            else:
                base_query += "\n                ORDER BY o.created_at DESC"

            if limit is not None:
                base_query += f" LIMIT {int(limit)} OFFSET {int(offset)}"

            cursor = await db.execute(base_query, tuple(params))
            rows = await cursor.fetchall()
            return self._order_rows_to_list(rows)

    async def count_orders_by_material(
        self,
        material_id: int,
        statuses: Optional[Sequence[str]] = None,
        order_type: Optional[str] = None
    ) -> int:
        """Получить количество заказов по материалу"""
        async with aiosqlite.connect(self.db_path) as db:
            base_query = """
                SELECT COUNT(*) 
                FROM orders o
                JOIN statuses s ON o.status_id = s.id
                WHERE o.material_id = ?
            """
            params: List[Any] = [material_id]

            if statuses:
                placeholders = ",".join("?" for _ in statuses)
                base_query += f" AND s.code IN ({placeholders})"
                params.extend(statuses)
            else:
                base_query += " AND s.code != 'archived' AND s.code != 'rejected'"

            if order_type:
                base_query += " AND o.order_type = ?"
                params.append(order_type)

            cursor = await db.execute(base_query, tuple(params))
            result = await cursor.fetchone()
            return result[0] if result else 0

    async def update_order_status(self, order_id: int, status_code: str, rejection_reason: Optional[str] = None) -> bool:
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
            # Обновляем статус и причину отклонения (если указана)
            if rejection_reason:
                # Если указана причина отклонения, сохраняем её
                await db.execute(
                    "UPDATE orders SET status_id = ?, rejection_reason = ? WHERE id = ?",
                    (status_id, rejection_reason, order_id)
                )
            elif status_code != "rejected":
                # Если статус не "отклонен", очищаем причину отклонения
                await db.execute(
                    "UPDATE orders SET status_id = ?, rejection_reason = NULL WHERE id = ?",
                    (status_id, order_id)
                )
            else:
                # Просто обновляем статус, не трогая причину отклонения
                await db.execute(
                    "UPDATE orders SET status_id = ? WHERE id = ?",
                    (status_id, order_id)
                )
            await db.commit()
            logger.info(f"Статус заказа №{order_id} изменен на {status_code}")
            return True

    async def get_all_materials(self, material_type: Optional[str] = None, only_available: bool = True) -> List[Dict[str, Any]]:
        """Получить материалы (с optional фильтром по типу)"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = "SELECT * FROM materials"
            conditions = []
            params: Tuple[Any, ...] = ()
            if material_type:
                conditions.append("type = ?")
                params += (material_type,)
            if only_available:
                conditions.append("is_available = 1")
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY name"
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            return self._order_rows_to_list(rows)

    async def get_materials_with_usage_count(self, material_type: Optional[str] = None, include_unavailable: bool = True) -> List[Dict[str, Any]]:
        """Получить материалы с количеством использований в заказах"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = """
                SELECT m.id, m.name, m.type, m.is_available, COUNT(o.id) as usage_count
                FROM materials m
                LEFT JOIN orders o ON m.id = o.material_id
            """
            params: Tuple[Any, ...] = ()
            conditions = []
            if material_type:
                conditions.append("m.type = ?")
                params += (material_type,)
            if not include_unavailable:
                conditions.append("m.is_available = 1")
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " GROUP BY m.id, m.name, m.type, m.is_available ORDER BY m.name"
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            return self._order_rows_to_list(rows)

    async def get_materials_with_orders(
        self,
        order_type: str,
        statuses: Sequence[str] = ("pending", "in_progress")
    ) -> List[Dict[str, Any]]:
        """Получить материалы, которые используются в указанных статусах заказов"""
        if not statuses:
            return []

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            placeholders = ",".join("?" for _ in statuses)
            query = f"""
                SELECT m.id, m.name, m.is_available, COUNT(o.id) as orders_count
                FROM orders o
                JOIN materials m ON o.material_id = m.id
                JOIN statuses s ON o.status_id = s.id
                WHERE o.order_type = ?
                  AND s.code IN ({placeholders})
                GROUP BY m.id, m.name, m.is_available
                ORDER BY m.name
            """
            params: Tuple[Any, ...] = (order_type, *statuses)
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            return self._order_rows_to_list(rows)

    async def add_material(self, name: str, material_type: str = '3d_print') -> bool:
        """Добавить новый материал"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute(
                    "INSERT INTO materials (name, type, is_available) VALUES (?, ?, 1)",
                    (name.strip(), material_type)
                )
                await db.commit()
                logger.info(f"Добавлен материал: {name} (тип: {material_type})")
                return True
            except aiosqlite.IntegrityError:
                return False

    async def delete_material(self, material_id: int) -> bool:
        """Сделать материал недоступным (soft delete)"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE materials SET is_available = 0 WHERE id = ?",
                (material_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def restore_material(self, material_id: int) -> bool:
        """Сделать материал вновь доступным"""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE materials SET is_available = 1 WHERE id = ?",
                (material_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def get_material(self, material_id: int) -> Optional[Dict[str, Any]]:
        """Получить материал по ID"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM materials WHERE id = ?",
                (material_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_material_id_by_name(self, name: str, material_type: Optional[str] = None) -> Optional[int]:
        """Получить ID материала по имени"""
        async with aiosqlite.connect(self.db_path) as db:
            query = "SELECT id FROM materials WHERE name = ?"
            params: Tuple[Any, ...] = (name,)
            if material_type:
                query += " AND type = ?"
                params += (material_type,)
            cursor = await db.execute(query, params)
            row = await cursor.fetchone()
            return row[0] if row else None

    async def get_ready_orders_for_reminder(self, hours: int = 4) -> List[Dict[str, Any]]:
        """Получить заказы со статусом 'Готов', которым нужно отправить напоминание"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            # Получаем заказы со статусом "ready", которым не отправляли напоминание или последнее напоминание было более hours часов назад
            cursor = await db.execute("""
                SELECT o.*, 
                       u.first_name, u.last_name, u.user_id, u.username,
                       s.code as status_code, s.name as status_name,
                       m.name as material_name
                FROM orders o
                JOIN users u ON o.user_id = u.user_id
                JOIN statuses s ON o.status_id = s.id
                LEFT JOIN materials m ON o.material_id = m.id
                WHERE s.code = 'ready'
                AND (o.last_reminder_time IS NULL 
                     OR datetime(o.last_reminder_time, '+' || ? || ' hours') <= datetime('now'))
                ORDER BY o.created_at DESC
            """, (hours,))
            rows = await cursor.fetchall()
            return self._order_rows_to_list(rows)

    async def update_last_reminder_time(self, order_id: int):
        """Обновить время последнего напоминания для заказа"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE orders SET last_reminder_time = datetime('now') WHERE id = ?",
                (order_id,)
            )
            await db.commit()

    async def archive_order(self, order_id: int, rejection_reason: Optional[str] = None) -> bool:
        """Переместить заказ в архив"""
        async with aiosqlite.connect(self.db_path) as db:
            # Получаем ID статуса "archived"
            cursor = await db.execute(
                "SELECT id FROM statuses WHERE code = 'archived'"
            )
            status_row = await cursor.fetchone()
            if not status_row:
                logger.error("Статус 'archived' не найден в БД")
                return False
            
            archived_status_id = status_row[0]
            
            # Переводим заказ в архив, сохраняя причину отклонения если она есть
            if rejection_reason:
                cursor = await db.execute(
                    "UPDATE orders SET status_id = ?, rejection_reason = ? WHERE id = ?",
                    (archived_status_id, rejection_reason, order_id)
                )
            else:
                cursor = await db.execute(
                    "UPDATE orders SET status_id = ? WHERE id = ?",
                    (archived_status_id, order_id)
                )
            await db.commit()
            
            if cursor.rowcount > 0:
                logger.info(f"Заказ №{order_id} перемещен в архив")
                
                # Очищаем архив, если в нем больше 25 заказов
                await self._cleanup_archive(db, archived_status_id)
                
                return True
            return False

    async def _cleanup_archive(self, db, archived_status_id: int):
        """Очистить архив, оставив только последние 25 заказов"""
        import config
        
        # Получаем все архивированные заказы, отсортированные по дате создания (новые первыми)
        cursor = await db.execute("""
            SELECT id, photo_path, model_path FROM orders 
            WHERE status_id = ? 
            ORDER BY created_at DESC
        """, (archived_status_id,))
        
        archived_orders = await cursor.fetchall()
        
        # Если заказов больше 25, удаляем старые
        if len(archived_orders) > config.ARCHIVE_MAX_SIZE:
            orders_to_delete = archived_orders[config.ARCHIVE_MAX_SIZE:]
            
            for order in orders_to_delete:
                order_id = order[0]
                photo_path_str = order[1]
                model_path_str = order[2]
                
                # Удаляем заказ из БД
                await db.execute("DELETE FROM orders WHERE id = ?", (order_id,))
                
                # Удаляем файлы заказа
                if photo_path_str:
                    photo_path = Path(photo_path_str)
                    if photo_path.exists():
                        try:
                            photo_path.unlink()
                        except Exception as e:
                            logger.warning(f"Не удалось удалить фото {photo_path}: {e}")
                
                if model_path_str:
                    model_path = Path(model_path_str)
                    if model_path.exists():
                        try:
                            model_path.unlink()
                        except Exception as e:
                            logger.warning(f"Не удалось удалить модель {model_path}: {e}")
                
                logger.info(f"Заказ №{order_id} удален из архива (превышен лимит)")
            
            await db.commit()
            logger.info(f"Архив очищен: удалено {len(orders_to_delete)} старых заказов")

    async def get_archived_orders(self, order_type: Optional[str] = None, limit: int = None, offset: int = 0) -> List[Dict[str, Any]]:
        """Получить архивированные заказы"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = """
                SELECT o.*, 
                       u.first_name, u.last_name, u.user_id, u.username,
                       s.code as status_code, s.name as status_name,
                       m.name as material_name
                FROM orders o
                JOIN users u ON o.user_id = u.user_id
                JOIN statuses s ON o.status_id = s.id
                LEFT JOIN materials m ON o.material_id = m.id
                WHERE s.code = 'archived'
                ORDER BY o.created_at DESC
            """
            if limit:
                query += f" LIMIT {limit} OFFSET {offset}"

            params: Tuple[Any, ...] = ()
            if order_type:
                query = query.replace("WHERE s.code = 'archived'", "WHERE s.code = 'archived' AND o.order_type = ?")
                params = (order_type,)

            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            return self._order_rows_to_list(rows)

    async def count_archived_orders(self, order_type: Optional[str] = None) -> int:
        """Получить количество архивированных заказов"""
        async with aiosqlite.connect(self.db_path) as db:
            query = """
                SELECT COUNT(*) FROM orders o
                JOIN statuses s ON o.status_id = s.id
                WHERE s.code = 'archived'
            """
            params: Tuple[Any, ...] = ()
            if order_type:
                query += " AND o.order_type = ?"
                params = (order_type,)
            cursor = await db.execute(query, params)
            result = await cursor.fetchone()
            return result[0] if result else 0

    async def delete_order(self, order_id: int) -> bool:
        """Удалить заказ из БД (полное удаление)"""
        async with aiosqlite.connect(self.db_path) as db:
            # Получаем информацию о заказе для удаления файлов
            cursor = await db.execute(
                "SELECT photo_path, model_path FROM orders WHERE id = ?",
                (order_id,)
            )
            order = await cursor.fetchone()
            
            if not order:
                return False
            
            # Удаляем заказ
            cursor = await db.execute(
                "DELETE FROM orders WHERE id = ?",
                (order_id,)
            )
            await db.commit()
            
            # Удаляем файлы заказа
            if order[0]:  # photo_path
                photo_path = Path(order[0])
                if photo_path.exists():
                    try:
                        photo_path.unlink()
                    except Exception as e:
                        logger.warning(f"Не удалось удалить фото {photo_path}: {e}")
            
            if order[1]:  # model_path
                model_path = Path(order[1])
                if model_path.exists():
                    try:
                        model_path.unlink()
                    except Exception as e:
                        logger.warning(f"Не удалось удалить модель {model_path}: {e}")
            
            logger.info(f"Заказ №{order_id} удален из БД")
            return cursor.rowcount > 0


# Глобальный экземпляр базы данных
db = Database()

