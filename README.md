# Placewise Backend

API каталога мест Душанбе: категории, места, поиск, избранное, отзывы, жалобы, модерация и кабинет владельца.

## Стек

- Python 3.14 / Django 6.1 / Django REST Framework
- PostgreSQL + PostGIS
- Redis (кэш)
- SimpleJWT, drf-spectacular, GeoDjango
- Gunicorn + WhiteNoise

## Требования

- Python 3.14+
- PostgreSQL с расширением PostGIS
- Redis
- GDAL/GEOS для GeoDjango (обычно определяются автоматически)

## Быстрый старт

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# откройте .env и задайте SECRET_KEY, JWT_SIGNING_KEY и параметры БД
```

Создайте базу и включите PostGIS:

```bash
createdb placewise_db
psql -d placewise_db -c "CREATE EXTENSION IF NOT EXISTS postgis;"
```

Примените миграции, заполните стартовые категории и запустите сервер:

```bash
python manage.py migrate
python manage.py seed_categories
python manage.py runserver
```

Проверка:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

## Docker

Одна команда для запуска приложения, PostgreSQL/PostGIS, Redis и ежедневного
резервного копирования:

```bash
cp .env.example .env
# задайте SECRET_KEY и JWT_SIGNING_KEY
docker compose up --build
```

Сервисы:

- `web` — Django + Gunicorn на `http://localhost:8000`.
- `db` — PostgreSQL 16 + PostGIS.
- `redis` — кэш и лимиты запросов.
- `backup` — `pg_dump` раз в сутки в volume `backups_data`, хранение 7 дней.

Миграции и `collectstatic` выполняются автоматически в `docker/entrypoint.sh`.
Для ручного бэкапа вне Docker есть `scripts/backup_db.sh`.

## Переменные окружения

Шаблон находится в `.env.example`.

Обязательные:

- `SECRET_KEY` — секрет Django.
- `JWT_SIGNING_KEY` — ключ подписи JWT.
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` — подключение к PostgreSQL.
- `DATABASE_URL` — альтернатива `DB_*`; имеет приоритет. Например:
  `postgis://postgres:postgres@127.0.0.1:5432/placewise_db`.

Основные:

- `DJANGO_DEBUG` — `True` для локальной разработки.
- `DJANGO_ALLOWED_HOSTS` — список через запятую.
- `DJANGO_CSRF_TRUSTED_ORIGINS`, `DJANGO_CORS_ALLOWED_ORIGINS` — доверенные frontend-домены.
- `REDIS_URL` — по умолчанию `redis://127.0.0.1:6379/1`.
- `SMS_ENABLED`, `SMS_API_URL`, `SMS_API_KEY`, `SMS_SENDER` — параметры SMS-провайдера.
  При `SMS_ENABLED=True` код отправляется POST-запросом с JSON
  `{"phone", "message", "sender"}`; при ошибке шлюза OTP удаляется, API отвечает `503`.
- `AWS_STORAGE_BUCKET_NAME`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
  `AWS_S3_ENDPOINT_URL`, `AWS_S3_REGION_NAME`, `AWS_S3_CUSTOM_DOMAIN`,
  `AWS_S3_MEDIA_LOCATION`, `AWS_QUERYSTRING_AUTH` — S3/MinIO/R2 для медиа.
  Если bucket не задан, используется локальная папка `media/`.
- `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_RELEASE`, `SENTRY_TRACES_SAMPLE_RATE` — Sentry.
- `EMAIL_*`, `DEFAULT_FROM_EMAIL` — почта.
- `DJANGO_SECURE_SSL_REDIRECT`, `DJANGO_SESSION_COOKIE_SECURE`, `DJANGO_CSRF_COOKIE_SECURE`,
  `DJANGO_SECURE_HSTS_SECONDS`, `DJANGO_HSTS_INCLUDE_SUBDOMAINS`, `DJANGO_HSTS_PRELOAD` — security-настройки для HTTPS.
- `GDAL_LIBRARY_PATH`, `GEOS_LIBRARY_PATH` — только если Django не находит библиотеки сам.

Секреты и `.env` не коммитятся.

## Категории

Команда `seed_categories` создаёт/обновляет девять стартовых категорий:

`restaurants`, `pharmacies`, `supermarkets`, `flowers`, `bakery`, `electronics`, `beauty`, `powerbanks`, `home_care`.

Она идемпотентна: существующие названия и настройки не перезаписываются, заполняются только недостающие переводы.

```bash
python manage.py seed_categories --dry-run
python manage.py seed_categories
```

## Импорт 2GIS

Импорт принимает CSV 2GIS. Категория по умолчанию определяется по имени файла:

| Файл | Категория |
| --- | --- |
| `01_Рестораны.csv` | `restaurants` |
| `02_Аптеки.csv` | `pharmacies` |
| `03_Супермаркеты.csv` | `supermarkets` |
| `04_Цветы.csv` | `flowers` |
| `05_Выпечка.csv` | `bakery` |
| `06_Электроника.csv` | `electronics` |
| `07_Красота.csv` | `beauty` |
| `08_Павербанки.csv` | `powerbanks` |
| `09_Дом и уход.csv` | `home_care` |

Сначала проверьте файл без записи в базу:

```bash
python manage.py import_places imports/01_Рестораны.csv \
  --dry-run \
  --report /tmp/import-report.csv
```

Затем выполните импорт:

```bash
python manage.py import_places imports/01_Рестораны.csv
```

Параметры:

- `--category` — явно задать категорию, если имя файла не распознано.
- `--status {draft,published,hidden}` — статус новых мест, по умолчанию `published`.
- `--source` — источник, по умолчанию `2gis`.
- `--report` — путь к CSV-отчёту.
- `--dry-run` — только проверка и отчёт.

Часы работы приводятся к формату `"24/7"` или
`{"mon": ["09:00", "18:00"], ...}`. Старые записи нормализуются при чтении.
Неизвестные часы сохраняются как есть и требуют ручной проверки.

## API

- Swagger UI: `/api/docs/`
- OpenAPI schema: `/api/schema/`
- Базовый префикс: `/api/v1/`
- Postman-коллекция: `postman/Placewise.postman_collection.json`

Публичные маршруты работают как с завершающим `/`, так и без него. В API
оставлен только один канонический путь для каждой функции, согласно ТЗ:
`/me/favorites`, `/auth/send-code`, `/auth/verify`, `/api/v1/me`,
`/places/{slug}/claim`, `/admin/reviews`, `/admin/claims`. Дубли и старые
алиасы удалены.

Списки отдают одновременно `items/total/page/limit` и legacy
`count/results/next/previous`. Ошибки имеют вид
`{"error": {"code": "...", "message": "..."}}` с сохранением `detail`.

Аутентификация — JWT в заголовке:

```http
Authorization: Bearer <access_token>
```

### Вход администратора

Админ входит по телефону и паролю:

```http
POST /api/v1/auth/admin/login/
Content-Type: application/json

{
  "phone": "+992900000001",
  "password": "StrongPassword123!"
}
```

Доступ разрешён активным пользователям с ролью `admin` или `moderator`,
а также superuser. Ответ содержит `access`, `refresh` и данные пользователя.

Первого администратора можно создать командой:

```bash
python manage.py createsuperuser
```

Если у существующего администратора нет пароля:

```bash
python manage.py changepassword +992900000001
```

### Сброс пароля пользователя

Админ может задать новый пароль пользователю, например если тот забыл старый:

```http
POST /api/v1/admin/users/{user_id}/set-password/
Authorization: Bearer <admin_access_token>
Content-Type: application/json

{
  "new_password": "NewStrongPassword123!"
}
```

Новый пароль проверяется теми же правилами Django, что и при создании.
Ответ — `204 No Content`, пароль в ответе не возвращается.

- `admin` и superuser могут менять пароль обычным пользователям, владельцам
  и модераторам.
- Пароль администратора или superuser может менять только superuser.
- Модератор не имеет доступа к этому endpoint.

## Production

```bash
python manage.py collectstatic --noinput
gunicorn config.wsgi:application
```

В production задайте `DJANGO_DEBUG=False`, реальные `DJANGO_ALLOWED_HOSTS`,
включите HTTPS-флаги и используйте внешние PostgreSQL/Redis. Для S3 задайте
`AWS_STORAGE_BUCKET_NAME` и ключи; для мониторинга — `SENTRY_DSN`.
Поиск использует `pg_trgm` (миграция `places.0010_enable_pg_trgm`).

## Структура

- `config/` — настройки и корневые URL.
- `places/` — места, категории, бренды, фото, избранное, импорт 2GIS, кабинет владельца.
- `users/` — пользователи, OTP и административный API пользователей.
- `reviews/` — отзывы, лайки, жалобы и модерация.
- `notifications/` — уведомления.
- `core/` — общие утилиты, включая парсер часов работы.
