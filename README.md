# Volunteer Hub — вебсистема керування волонтерськими ініціативами

**Volunteer Hub** — локальний Django-застосунок для керування волонтерськими ініціативами, заявками, змінами, підтвердженими годинами, сертифікатами, повідомленнями та адміністративним контролем.

## Стек

- Python 3
- Django
- Django Templates
- HTMX-lite для часткових оновлень фільтрів
- Alpine-lite для дрібної інтерактивності
- Neon Postgres через `DATABASE_URL`
- Custom CSS без Bootstrap/React/Next.js
- Cloudinary для онлайн-зберігання завантажених файлів і CDN-фонів

## Запуск

Перший запуск або оновлення структури БД:

```powershell
copy .env.example .env
pwsh -NoProfile -ExecutionPolicy Bypass -File .\setup_neon.ps1
```

Щоденний запуск на Windows:

```bat
start_windows.bat
```

Ця команда запускає production-подібний сервер Waitress з `DEBUG=0` і попередньо збирає стиснені статичні файли. Для режиму розробки з автоматичним перезавантаженням використовуйте:

```bat
start_windows.bat --dev
```

Якщо потрібно явно виконати міграції та seed перед стартом:

```bat
start_windows.bat --setup
```

macOS/Linux:

```bash
./start_linux_mac.sh
./start_linux_mac.sh --setup
```

Після запуску відкрийте:

```text
http://127.0.0.1:8000/
```

## Seed-дані

Команда `python manage.py seed` очищає робочу БД і створює наповнений набір користувачів, організацій, ініціатив, заявок, змін, годин і сертифікатів. Після виконання команда записує службовий список seed-акаунтів у `output/seed_accounts.md`.

Файл `output/seed_accounts.md` не додається в GitHub, бо містить паролі для локального/навчального запуску.

Якщо потрібно задати пароль адміністратора вручну, додайте в `.env`:

```env
SEED_ADMIN_PASSWORD=your-secure-admin-password
```

## Реалізовано

- Український інтерфейс
- Реєстрація та авторизація
- Ролі: волонтер, координатор, менеджер організації, адміністратор
- Каталог ініціатив з фільтрами
- Сторінка ініціативи
- Заявка волонтера на ініціативу/зміну
- Скасування заявки з причиною
- Розгляд заявок координатором
- Зміни/слоти участі
- Подання волонтерських годин
- Підтвердження/відхилення годин координатором
- Автоматична видача сертифіката після підтвердження годин
- Повідомлення між волонтером і координатором
- Сповіщення
- Профіль волонтера
- Навички та доступність волонтера
- Панелі волонтера, координатора, менеджера організації та адміністратора
- Керування користувачами, організаціями, категоріями та навичками
- Аналітичні картки та аудит дій
- Фотофони через локальні JPG або Cloudinary manifest

## Neon Postgres

SQLite з проєкту прибрано. Застосунок не стартує без `DATABASE_URL`, тому у `.env` потрібно вказати Neon Postgres:

```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST/neondb?sslmode=require
NEON_WAKE_ENABLED=1
NEON_API_KEY=replace-with-neon-api-key
NEON_PROJECT_ID=replace-with-neon-project-id
NEON_ENDPOINT_ID=ep-royal-sea-adqsh3oh
NEON_WAKE_TIMEOUT=8
```

`NEON_PROJECT_ID` береться з Neon dashboard або URL/API відповіді проєкту, `NEON_ENDPOINT_ID` для поточного connection host: `ep-royal-sea-adqsh3oh`. Якщо база недоступна і `NEON_WAKE_ENABLED=1`, middleware викликає Neon API:

```text
POST https://console.neon.tech/api/v2/projects/{project_id}/endpoints/{endpoint_id}/start
```

Поки compute endpoint запускається, сайт повертає сторінку `503 База даних прокидається`.

## Cloudinary

У `.env` потрібно вказати:

```env
CLOUDINARY_CLOUD_NAME=your-cloud-name
CLOUDINARY_API_KEY=your-api-key
CLOUDINARY_API_SECRET=your-api-secret
```

Після цього нові завантаження моделей (`avatar`, `logo`, `image`, `evidence_file`) зберігаються в Cloudinary. Якщо форма не збережена через помилки або сторінку оновили до submit, файл не записується у storage. Якщо файл замінили або відмітили видалення поточного файлу, старий файл видаляється зі storage після успішного збереження форми.

Завантажити дизайн-фото з `static/images/photos` у Cloudinary і записати CDN URL у manifest:

```bash
python manage.py upload_design_assets
```

Перевірити, чи сторінки віддають оптимізовані Cloudinary URL, і заміряти час завантаження перших зображень:

```bash
python manage.py measure_images / /initiatives/ /organizations/
python manage.py measure_images / /initiatives/ /organizations/ --fetch --limit 4
```

Прогріти CDN-кеш Cloudinary після seed або деплою, щоб перший користувач не чекав створення трансформацій:

```bash
python manage.py warm_cloudinary_images --limit 220 --workers 6
```

Перевірити або видалити Cloudinary-файли, які вже не використовуються в БД чи design manifest:

```bash
python manage.py cleanup_cloudinary_assets
python manage.py cleanup_cloudinary_assets --delete --min-age-hours 1
```

Після ручного масового видалення ініціатив або організацій можна перевірити й прибрати записи, що втратили зв'язки:

```bash
python manage.py cleanup_orphaned_records --dry-run
python manage.py cleanup_orphaned_records
```

Перенести вже наявні локальні файли з `media/` у Cloudinary:

```bash
python manage.py migrate_media_to_cloudinary
python manage.py migrate_media_to_cloudinary --delete-local
```

## Deploy на Render

Для Render у проєкті є `build.sh`. Він встановлює залежності, збирає статичні файли й виконує міграції:

```bash
pip install -r requirements.txt
python manage.py collectstatic --no-input --upload-unhashed-files
python manage.py migrate
if [ "${CLOUDINARY_CLEANUP_ON_START:-1}" = "1" ]; then
  python manage.py cleanup_cloudinary_assets --delete --min-age-hours "${CLOUDINARY_CLEANUP_MIN_AGE_HOURS:-1}" || true
fi
python manage.py warm_cloudinary_images --limit 220 --workers 6 || true
```

У Render потрібно створити Python Web Service з GitHub-репозиторію та вказати:

```text
Build Command: ./build.sh
Start Command: ./start_render.sh
```

Обов'язкові Environment Variables на Render:

```env
DEBUG=0
SECRET_KEY=generate-a-secure-secret
DATABASE_URL=postgresql://USER:PASSWORD@HOST/neondb?sslmode=require
CLOUDINARY_CLOUD_NAME=your-cloud-name
CLOUDINARY_API_KEY=your-api-key
CLOUDINARY_API_SECRET=your-api-secret
CLOUDINARY_CLEANUP_ON_START=1
CLOUDINARY_CLEANUP_MIN_AGE_HOURS=1
NEON_WAKE_ENABLED=1
NEON_API_KEY=your-neon-api-key
NEON_PROJECT_ID=your-neon-project-id
NEON_ENDPOINT_ID=your-neon-endpoint-id
NEON_WAKE_TIMEOUT=12
```

`ALLOWED_HOSTS` можна не заповнювати для стандартного домену Render: застосунок автоматично додає `RENDER_EXTERNAL_HOSTNAME`. Для власного домену додайте його в `ALLOWED_HOSTS`.

## Архітектура

Застосунок реалізовано як серверний модульний моноліт:

- `config/` — налаштування Django
- `apps/hub/models.py` — доменна модель платформи
- `apps/hub/forms.py` — серверна валідація форм
- `apps/hub/views.py` — сторінки та workflow
- `apps/hub/services.py` — бізнес-логіка, сповіщення, сертифікати, аудит
- `apps/hub/management/commands/seed.py` — демодані
- `templates/` — Django Templates
- `static/` — CSS, JS, favicon, локальні зображення
- `media/` — локальні завантаження

## Особливості дизайну

Дизайн побудовано навколо концепції **Civic Mission Control**: теплий паперовий фон, карта-сітка, місійні картки, стрічки терміновості, impact-rings, статусні бейджі, операційні панелі та адаптивні картки.

## Обмеження

- Реальна email-розсилка не підключена, сповіщення локальні.
- Сертифікат друкується через браузерну функцію друку.
- HTMX реалізовано локальним lightweight-скриптом для часткового оновлення фільтрів без CDN.
