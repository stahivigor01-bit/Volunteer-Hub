from datetime import time, timedelta
from decimal import Decimal
from pathlib import Path
from collections import defaultdict
import os
import secrets

from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.hub.models import (
    Application, AuditLog, Certificate, Initiative, InitiativeCategory, Message,
    MessageThread, Notification, Organization, Shift, Skill, User,
    VolunteerAvailability, VolunteerHour, VolunteerSkill,
)
from apps.hub.utils import slug_base

try:
    import cloudinary
    import cloudinary.uploader
except ImportError:  # pragma: no cover - cloudinary is optional in tests without media
    cloudinary = None


PHOTO_FILES = [
    'aid-packing.jpg',
    'community-care.jpg',
    'outdoor-aid.jpg',
    'donation-work.jpg',
    'hero-volunteers.jpg',
    'default-initiative.jpg',
]

CITIES = [
    'Київ', 'Львів', 'Івано-Франківськ', 'Тернопіль', 'Чернівці', 'Рівне',
    'Вінниця', 'Полтава', 'Дніпро', 'Черкаси', 'Луцьк', 'Ужгород',
]

MANAGER_NAMES = [
    'Олег Сокирко', 'Наталія Дорошенко', 'Андрій Матвіїв', 'Галина Черній',
    'Павло Кравченко', 'Марина Шевчук',
]

COORDINATOR_NAMES = [
    'Ірина Ковальчук', 'Тарас Гончар', 'Вікторія Романюк', 'Богдан Лисенко',
    'Катерина Мороз', 'Юрій Пилипчук', 'Олена Гнатюк', 'Михайло Савчук',
]

VOLUNTEER_NAMES = [
    'Марко Савчук', 'Анна Мельник', 'Дмитро Павлюк', 'Оксана Литвин',
    'Назар Крамар', 'Юлія Бондар', 'Роман Яценко', 'Віра Кулик',
    'Іван Прокопів', 'Соломія Руденко', 'Артем Козак', 'Дарина Семенюк',
    'Максим Черненко', 'Лілія Остапчук', 'Владислав Клим', 'Тетяна Савка',
    'Олексій Яворський', 'Зоряна Петренко', 'Руслан Бабій', 'Аліна Стеценко',
    'Денис Кравець', 'Марта Ткачук', 'Сергій Волошин', 'Надія Кушнір',
    'Василь Коваль', 'Емілія Бойчук', 'Петро Гринь', 'Христина Дяк',
    'Орест Левицький', 'Ніна Стасюк', 'Єгор Мазур', 'Анастасія Поліщук',
    'Тимофій Захарченко', 'Ярина Гуменюк', 'Арсен Куценко', 'Софія Біла',
    'Мирослав Гаврилюк', 'Вероніка Луцик', 'Степан Гайдук', 'Олеся Коваль',
    'Матвій Сорока', 'Ксенія Харченко', 'Давид Омельчук', 'Єва Ковтун',
    'Любомир Шевців', 'Роксолана Чорна', 'Станіслав Терещук', 'Меланія Білик',
]

PERSONAL_DOMAINS = ['gmail.com', 'ukr.net', 'i.ua', 'meta.ua', 'outlook.com', 'proton.me', 'icloud.com', 'email.ua']

ORG_DOMAINS = [
    'helppoint.org.ua', 'greencity.org.ua', 'youthsupport.org.ua', 'animalrescue.org.ua',
    'communitykitchen.org.ua', 'educationbarriers.org.ua', 'mistoturboty.org.ua',
    'dobralogistyka.org.ua', 'maysternia.org.ua', 'teplyikontakt.org.ua',
    'kulturnyirukh.org.ua', 'rapidaid.org.ua', 'inclusionhub.org.ua',
    'digitalhelp.org.ua', 'susidska.org.ua', 'ekovarta.org.ua',
    'medvarta.org.ua', 'svitloosvity.org.ua',
]

CATEGORY_DATA = [
    ('Гуманітарна допомога', 'humanitarian-aid', 'Підтримка родин, шелтерів і локальних пунктів видачі допомоги.', '✚', '#f97316'),
    ('Екологія та відновлення', 'environment-recovery', 'Прибирання просторів, сортування, озеленення та відновлення міської інфраструктури.', '♻', '#4f6f52'),
    ('Освіта і менторство', 'education-mentoring', 'Навчальні програми, наставництво, цифрова грамотність і підтримка дітей.', '✎', '#2563eb'),
    ('Медична підтримка', 'medical-support', 'Донорські кампанії, базова перша допомога та супровід медичних подій.', '+', '#dc2626'),
    ('Допомога літнім людям', 'elderly-care', 'Домашні візити, телефонна підтримка, доставка продуктів та соціальна присутність.', '☉', '#16324f'),
    ('Підтримка тварин', 'animal-care', 'Допомога притулкам, вигул, соціалізація тварин і збір корму.', '🐾', '#9b6b43'),
    ('Культура та події', 'culture-events', 'Громадські події, культурні вечори, реєстрація гостей і навігація.', '◆', '#d97706'),
    ('Молодіжні програми', 'youth-programs', 'Проєкти для підлітків, кар’єрні зустрічі, клуби та практичні воркшопи.', '✦', '#7c3aed'),
    ('Громадська кухня', 'community-kitchen', 'Приготування, пакування й доставка гарячих обідів для вразливих груп.', '◍', '#c2410c'),
    ('Логістика допомоги', 'aid-logistics', 'Складська робота, маршрутизація, пакування й контроль залишків.', '▣', '#0f766e'),
    ('Цифрова підтримка', 'digital-support', 'Допомога з онлайн-сервісами, CRM, формами, реєстраціями та базовою технікою.', '⌘', '#0891b2'),
    ('Психосоціальна підтримка', 'psychosocial-support', 'Безпечні простори, групові зустрічі, підтримка сімей і супровід фасилітаторів.', '◇', '#be185d'),
    ('Інклюзія та доступність', 'inclusion-accessibility', 'Адаптація подій, супровід учасників і перевірка доступності локацій.', '◎', '#4338ca'),
    ('Фандрейзинг', 'fundraising', 'Збір ресурсів, партнерські кампанії, комунікація з донорами та прозора звітність.', '$', '#65a30d'),
    ('Відбудова громад', 'community-rebuild', 'Легкі ремонтні роботи, облаштування просторів і координація локальних потреб.', '△', '#b45309'),
    ('Безпека подій', 'event-safety', 'Навігація потоків, контроль входу, інструктажі та підтримка безпечної поведінки.', '□', '#334155'),
    ('Комунікації', 'communications', 'Фото, відео, соціальні мережі, тексти, опитування та історії впливу.', '◒', '#0284c7'),
    ('Термінове реагування', 'rapid-response', 'Швидка мобілізація волонтерів, короткі зміни й підтримка критичних запитів.', '!', '#b91c1c'),
]

SKILL_DATA = [
    ('Логістика гуманітарної допомоги', 'Логістика'),
    ('Складський облік', 'Логістика'),
    ('Пакування наборів', 'Логістика'),
    ('Планування маршрутів', 'Логістика'),
    ('Водіння легкового авто', 'Транспорт'),
    ('Водіння мікроавтобуса', 'Транспорт'),
    ('Перша домедична допомога', 'Медицина'),
    ('Підтримка донорських кампаній', 'Медицина'),
    ('Комунікація з учасниками', 'Комунікації'),
    ('Модерація груп', 'Комунікації'),
    ('Соціальні мережі', 'Комунікації'),
    ('Фото та відеофіксація', 'Комунікації'),
    ('Копірайтинг українською', 'Комунікації'),
    ('Переклад англійською', 'Мови'),
    ('Переклад польською', 'Мови'),
    ('Навчання дітей', 'Освіта'),
    ('Наставництво підлітків', 'Освіта'),
    ('Цифрова грамотність', 'Освіта'),
    ('Робота з літніми людьми', 'Соціальна підтримка'),
    ('Телефонна підтримка', 'Соціальна підтримка'),
    ('Супровід людей з інвалідністю', 'Інклюзія'),
    ('Організація подій', 'Події'),
    ('Реєстрація учасників', 'Події'),
    ('Навігація гостей', 'Події'),
    ('Безпека подій', 'Події'),
    ('Громадська кухня', 'Харчування'),
    ('Санітарні норми кухні', 'Харчування'),
    ('Сортування вторсировини', 'Екологія'),
    ('Озеленення', 'Екологія'),
    ('Догляд за тваринами', 'Тварини'),
    ('Вигул тварин', 'Тварини'),
    ('CRM та таблиці', 'Цифрові інструменти'),
    ('Базова технічна підтримка', 'Цифрові інструменти'),
    ('Фандрейзингові кампанії', 'Фандрейзинг'),
    ('Комунікація з партнерами', 'Фандрейзинг'),
    ('Польова координація', 'Координація'),
    ('Лідерство малих груп', 'Координація'),
    ('Оцінка потреб громади', 'Аналітика'),
    ('Опитування мешканців', 'Аналітика'),
    ('Документування результатів', 'Аналітика'),
    ('Ремонтні роботи', 'Відбудова'),
    ('Монтаж меблів', 'Відбудова'),
]

ORG_THEMES = [
    ('HelpPoint Ukraine', 'helppoint-ukraine', 'Львів', 'Координує адресну гуманітарну допомогу для сімей, шелтерів і локальних пунктів підтримки. Команда поєднує складську логістику, облік потреб та швидку видачу наборів.'),
    ('Green City Team', 'green-city-team', 'Київ', 'Проводить екологічні акції, сортування вторсировини й озеленення районів. Організація працює з ОСББ, школами та молодіжними просторами.'),
    ('Youth Support Center', 'youth-support-center', 'Івано-Франківськ', 'Розвиває менторські програми для підлітків і молоді. Фокус команди - практичні навички, кар’єрні зустрічі та безпечні освітні середовища.'),
    ('Animal Rescue Group', 'animal-rescue-group', 'Тернопіль', 'Допомагає притулкам із доглядом за тваринами, кормом, вигулом і соціалізацією. Волонтери проходять короткий інструктаж перед змінами.'),
    ('Community Kitchen Львів', 'community-kitchen-lviv', 'Львів', 'Готує гарячі обіди для літніх людей, переселенців і сімей у кризі. Команда тримає високі стандарти гігієни й чіткий облік доставок.'),
    ('Education Without Barriers', 'education-without-barriers', 'Київ', 'Створює доступні навчальні формати для дітей, дорослих і людей з інвалідністю. Працює з цифровою грамотністю та адаптацією матеріалів.'),
    ('Місто Турботи', 'misto-turboty', 'Чернівці', 'Підтримує літніх людей через домашні візити, закупівлі, телефонні дзвінки та соціальні зустрічі. Робота побудована на стабільних мікрокомандах.'),
    ('Добра Логістика', 'dobra-logistyka', 'Рівне', 'Організовує склади, маршрути, водіїв і видачу допомоги для партнерських ініціатив. Має процеси контролю залишків та пріоритезації запитів.'),
    ('Відкрита Майстерня', 'vidkryta-maysternia', 'Вінниця', 'Облаштовує громадські простори, проводить легкі ремонтні роботи та майстер-класи з відновлення. Команда працює з локальними громадами.'),
    ('Теплий Контакт', 'teplyi-kontakt', 'Полтава', 'Надає психосоціальну підтримку сім’ям, волонтерам і людям у складних життєвих обставинах. Залучає фасилітаторів та асистентів груп.'),
    ('Культурний Рух', 'kulturnyi-rukh', 'Дніпро', 'Проводить благодійні події, культурні вечори, лекторії та виставки для збору коштів. Волонтери підтримують події від реєстрації до звітності.'),
    ('Rapid Aid Network', 'rapid-aid-network', 'Черкаси', 'Швидко збирає волонтерські групи на термінові локальні запити. Команда фокусується на коротких змінах, прозорому звітуванні та безпеці.'),
    ('Інклюзивний Простір', 'inkliuzyvnyi-prostir', 'Луцьк', 'Перевіряє доступність локацій, супроводжує учасників і адаптує події для різних потреб. Працює з консультантами та волонтерами-супровідниками.'),
    ('Digital Help Desk', 'digital-help-desk', 'Ужгород', 'Допомагає громадським командам із формами, CRM, таблицями, технікою та онлайн-сервісами. Має черги звернень і дистанційні зміни.'),
    ('Фонд Сусідської Підтримки', 'fond-susidskoi-pidtrymky', 'Київ', 'Об’єднує локальні групи для адресної взаємодопомоги у районах. Підтримує продуктові набори, дрібні ремонти та соціальні візити.'),
    ('ЕкоВарта Захід', 'ekovarta-zakhid', 'Львів', 'Моніторить зелені зони, проводить сортувальні станції та волонтерські екопатрулі. Команда готує регулярні звіти для громад.'),
    ('Медична Вартиця', 'medychna-vartytsia', 'Тернопіль', 'Проводить навчання з першої допомоги, підтримує донорські дні й медичні інформаційні кампанії. Залучає волонтерів з різним рівнем досвіду.'),
    ('Світло Освіти', 'svitlo-osvity', 'Івано-Франківськ', 'Організовує клуби, репетиторські зустрічі та короткі практичні курси. Особлива увага - дітям ВПО та підліткам з малих громад.'),
]

MISSION_THEMES = [
    ('Пакування сімейних продуктових наборів', 'Підготовка збалансованих наборів для родин, які отримують адресну підтримку.', 0, 9),
    ('Сортувальна станція для району', 'Сортування вторсировини, консультації мешканців і підготовка мішків до відвантаження.', 1, 10),
    ('Менторська субота для підлітків', 'Практична зустріч про навчання, кар’єрні кроки та безпечну комунікацію.', 2, 11),
    ('Кампанія донорства крові', 'Реєстрація донорів, навігація, комунікація та супровід інформаційної зони.', 3, 7),
    ('Домашні візити до літніх людей', 'Доставка продуктів, коротке спілкування, перевірка побутових потреб і фіксація запитів.', 4, 18),
    ('Ранкова зміна у притулку', 'Вигул, прибирання вольєрів, соціалізація тварин і підготовка корму.', 5, 29),
    ('Реєстрація гостей благодійного вечора', 'Привітання, навігація, контроль списків, допомога з донат-зонами та фотофіксація.', 6, 21),
    ('Кар’єрний клуб для молоді', 'Міні-лекції, вправи з резюме, індивідуальні консультації та робота в групах.', 7, 16),
    ('Вечірня громадська кухня', 'Нарізка, фасування гарячих обідів, пакування доставок і прибирання кухні.', 8, 25),
    ('Маршрут доставки гуманітарної допомоги', 'Планування маршрутів, завантаження, доставка пакунків і фіксація отримання.', 9, 3),
    ('Цифрова приймальня для громади', 'Допомога з онлайн-заявками, таблицями, електронною поштою та перевіркою документів.', 10, 17),
    ('Група підтримки для сімей', 'Підготовка простору, реєстрація учасників, нотування запитів і супровід фасилітатора.', 11, 19),
    ('Аудит доступності локації', 'Перевірка входів, навігації, санітарних зон і підготовка короткого звіту.', 12, 20),
    ('Фандрейзингова вулична точка', 'Комунікація з перехожими, збір контактів, пояснення цілі кампанії та прозорий облік.', 13, 33),
    ('Оновлення громадської кімнати', 'Легкі ремонтні роботи, монтаж меблів, прибирання та підготовка простору до відкриття.', 14, 40),
    ('Безпечна навігація масової події', 'Координація потоків людей, підказки учасникам, зв’язок зі штабом і контроль зон.', 15, 24),
    ('Історії впливу для партнерів', 'Фото, короткі інтерв’ю, тексти для соціальних мереж і підготовка матеріалів звітності.', 16, 11),
    ('Терміновий пункт видачі', 'Швидке розгортання столів, перевірка списків, видача допомоги й контроль залишків.', 17, 35),
]


class Command(BaseCommand):
    help = 'Rebuild Volunteer Hub with a full production-like seed dataset.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-media',
            action='store_true',
            help='Do not upload seed images. Used by tests and offline development.',
        )

    def handle(self, *args, **options):
        self.skip_media = options['skip_media']
        self.photos_dir = settings.BASE_DIR / 'static' / 'images' / 'photos'
        self.accounts = []
        self.media_cache = {}
        self.cloudinary_ready = self.configure_cloudinary()

        self.clear_database()
        admin = self.create_users()
        categories = self.create_categories()
        skills = self.create_skills()
        managers = list(User.objects.filter(role=User.Roles.ORGANIZATION_MANAGER).order_by('email'))
        coordinators = list(User.objects.filter(role=User.Roles.COORDINATOR).order_by('email'))
        volunteers = list(User.objects.filter(role=User.Roles.VOLUNTEER).order_by('email'))
        organizations = self.create_organizations(managers, coordinators)
        initiatives = self.create_initiatives(organizations, coordinators, categories, skills)
        shifts = self.create_shifts(initiatives)
        applications = self.create_applications(volunteers, initiatives, shifts)
        hours = self.create_hours(volunteers, applications, coordinators)
        self.create_certificates(hours)
        self.create_messages(applications, coordinators)
        self.create_notifications(admin, managers, coordinators, volunteers)
        self.create_audit_logs(admin, managers, coordinators, initiatives)
        self.write_accounts_file()
        cache.delete('dashboard_numbers')

        counts = {
            'users': User.objects.count(),
            'organizations': Organization.objects.count(),
            'categories': InitiativeCategory.objects.count(),
            'skills': Skill.objects.count(),
            'initiatives': Initiative.objects.count(),
            'shifts': Shift.objects.count(),
            'applications': Application.objects.count(),
            'hours': VolunteerHour.objects.count(),
            'certificates': Certificate.objects.count(),
            'threads': MessageThread.objects.count(),
            'notifications': Notification.objects.count(),
        }
        for key, value in counts.items():
            self.stdout.write(f'{key}: {value}')
        self.stdout.write(self.style.SUCCESS('Volunteer Hub database was rebuilt with the new seed dataset.'))

    def configure_cloudinary(self):
        if self.skip_media:
            return False
        cfg = settings.CLOUDINARY_STORAGE
        required = [cfg.get('CLOUD_NAME'), cfg.get('API_KEY'), cfg.get('API_SECRET')]
        if not cloudinary or not all(required):
            self.stdout.write(self.style.WARNING('Cloudinary is not configured; seed images will be left empty.'))
            return False
        cloudinary.config(
            cloud_name=cfg['CLOUD_NAME'],
            api_key=cfg['API_KEY'],
            api_secret=cfg['API_SECRET'],
            secure=True,
        )
        return True

    def clear_database(self):
        for model in [
            Message, MessageThread, Notification, Certificate, VolunteerHour, Application,
            Shift, Initiative, Organization, VolunteerAvailability, VolunteerSkill, Skill,
            InitiativeCategory, AuditLog, User,
        ]:
            model.objects.all().delete()
        Session.objects.all().delete()

    def account(self, email, full_name, role, password, **extra):
        user = User(
            username=email,
            email=email,
            full_name=full_name,
            role=role,
            status=User.Statuses.ACTIVE,
            **extra,
        )
        user.set_password(password)
        user.save()
        self.accounts.append((role, full_name, email, password))
        return user

    def person_email(self, full_name, domain):
        local = slug_base(full_name, 'user').replace('-', '.')
        return f'{local}@{domain}'

    def generated_password(self, env_name=''):
        env_value = os.getenv(env_name, '').strip() if env_name else ''
        return env_value or secrets.token_urlsafe(18)

    def create_users(self):
        admin = self.account(
            'ihor.stakhiv@volunteerhub.org.ua',
            'Стахів Ігор',
            User.Roles.ADMIN,
            self.generated_password('SEED_ADMIN_PASSWORD'),
            is_staff=True,
            is_superuser=True,
            city='Київ',
            phone='+380671000001',
            bio='Адміністратор платформи, відповідає за модерацію користувачів, довідники, аналітику та якість даних.',
        )
        for idx, full_name in enumerate(MANAGER_NAMES, start=1):
            self.account(
                self.person_email(full_name, ORG_DOMAINS[(idx - 1) % len(ORG_DOMAINS)]),
                full_name,
                User.Roles.ORGANIZATION_MANAGER,
                self.generated_password(),
                city=CITIES[idx % len(CITIES)],
                phone=f'+38067210{idx:04d}',
                bio='Менеджер партнерської організації: відповідає за стратегію ініціатив, команду координаторів та якість звітності.',
        )
        for idx, full_name in enumerate(COORDINATOR_NAMES, start=1):
            self.account(
                self.person_email(full_name, ORG_DOMAINS[(idx + 5) % len(ORG_DOMAINS)]),
                full_name,
                User.Roles.COORDINATOR,
                self.generated_password(),
                city=CITIES[(idx + 3) % len(CITIES)],
                phone=f'+38067320{idx:04d}',
                bio='Координатор зміни: перевіряє заявки, планує волонтерські слоти, підтверджує години та веде комунікацію з учасниками.',
            )
        for idx, full_name in enumerate(VOLUNTEER_NAMES, start=1):
            avatar = self.upload_seed_image('avatars', f'volunteer-{idx:02d}', PHOTO_FILES[idx % len(PHOTO_FILES)])
            volunteer = self.account(
                self.person_email(full_name, PERSONAL_DOMAINS[(idx - 1) % len(PERSONAL_DOMAINS)]),
                full_name,
                User.Roles.VOLUNTEER,
                self.generated_password(),
                city=CITIES[(idx + 5) % len(CITIES)],
                phone=f'+38067430{idx:04d}',
                bio=f'Волонтер із досвідом участі у громадських ініціативах. Готовий працювати у змінах, комунікувати з командою та фіксувати результати роботи. Основний інтерес: {SKILL_DATA[idx % len(SKILL_DATA)][0].lower()}.',
                avatar=avatar,
            )
            VolunteerAvailability.objects.create(
                volunteer=volunteer,
                weekdays=idx % 2 == 0,
                weekends=True,
                mornings=idx % 3 == 0,
                afternoons=True,
                evenings=idx % 4 != 0,
                remote_only=idx % 11 == 0,
                preferred_city=volunteer.city,
            )
        return admin

    def create_categories(self):
        categories = []
        for name, slug, description, icon, color in CATEGORY_DATA:
            categories.append(InitiativeCategory.objects.create(
                name=name,
                slug=slug,
                description=description,
                icon=icon,
                color=color,
            ))
        return categories

    def create_skills(self):
        skills = []
        for name, category in SKILL_DATA:
            skills.append(Skill.objects.create(name=name, category=category))
        volunteers = list(User.objects.filter(role=User.Roles.VOLUNTEER).order_by('email'))
        for idx, volunteer in enumerate(volunteers):
            selected = [skills[(idx + offset * 5) % len(skills)] for offset in range(7)]
            VolunteerSkill.objects.bulk_create(
                [VolunteerSkill(volunteer=volunteer, skill=skill) for skill in selected],
                ignore_conflicts=True,
            )
        return skills

    def create_organizations(self, managers, coordinators):
        organizations = []
        for idx, (name, slug, city, description) in enumerate(ORG_THEMES):
            domain = ORG_DOMAINS[idx % len(ORG_DOMAINS)]
            logo = self.upload_seed_image('organizations', slug, PHOTO_FILES[idx % len(PHOTO_FILES)])
            org = Organization.objects.create(
                name=name,
                slug=slug,
                description=description,
                logo=logo,
                city=city,
                address=f'{city}, вул. Волонтерська, {idx + 7}',
                contact_email=f'office@{domain}',
                phone=f'+38067540{idx + 1:04d}',
                website=f'https://{domain}',
                status=Organization.Statuses.ACTIVE,
                manager=managers[idx % len(managers)],
            )
            org.coordinators.add(
                coordinators[idx % len(coordinators)],
                coordinators[(idx + 3) % len(coordinators)],
            )
            organizations.append(org)
        return organizations

    def create_initiatives(self, organizations, coordinators, categories, skills):
        initiatives = []
        today = timezone.localdate()
        urgency_values = [
            Initiative.Urgency.LOW,
            Initiative.Urgency.MEDIUM,
            Initiative.Urgency.HIGH,
            Initiative.Urgency.EMERGENCY,
        ]
        format_values = [
            Initiative.Formats.OFFLINE,
            Initiative.Formats.HYBRID,
            Initiative.Formats.ONLINE,
        ]
        status_values = [Initiative.Statuses.PUBLISHED]
        for org_index, org in enumerate(organizations):
            org_coordinators = list(org.coordinators.all().order_by('email')) or coordinators
            for local_index in range(10):
                theme_index = (org_index * 5 + local_index) % len(MISSION_THEMES)
                title_base, short_base, category_index, skill_index = MISSION_THEMES[theme_index]
                city = CITIES[(org_index + local_index) % len(CITIES)]
                title = f'{title_base}: {org.city} #{local_index + 1}'
                slug = f'{slug_base(title_base, "initiative")}-{org.slug}-{local_index + 1}'
                start_date = today + timedelta(days=(org_index * 2) + local_index + 1)
                image = self.upload_seed_image('initiatives', slug, PHOTO_FILES[theme_index % len(PHOTO_FILES)])
                initiative = Initiative.objects.create(
                    organization=org,
                    category=categories[category_index % len(categories)],
                    title=title,
                    slug=slug,
                    short_description=short_base,
                    description=(
                        f'{short_base} Ініціатива має чіткий план зміни, відповідального координатора, '
                        f'реєстрацію учасників і післязмінне підтвердження годин. Команда очікує волонтерів, '
                        f'які можуть працювати уважно, вчасно приходити на локацію та коректно фіксувати виконані задачі.'
                    ),
                    image=image,
                    urgency_level=urgency_values[(org_index + local_index) % len(urgency_values)],
                    format=format_values[(org_index + local_index) % len(format_values)],
                    city=city,
                    location_address=f'{city}, громадський простір "{org.name}", зал {local_index + 1}',
                    start_date=start_date,
                    end_date=start_date + timedelta(days=7 + local_index),
                    required_volunteers_count=18 + ((org_index + local_index) % 9),
                    approved_volunteers_count=0,
                    beginner_friendly=local_index % 2 == 0,
                    accessibility_notes='Локація має зрозумілу навігацію; за потреби координатор забезпечує додатковий супровід.',
                    safety_notes='Перед початком зміни проводиться інструктаж щодо безпеки, контактів штабу та правил взаємодії з учасниками.',
                    contact_person=org_coordinators[local_index % len(org_coordinators)].full_name,
                    expected_impact=f'{80 + org_index * 7 + local_index * 11} отримувачів або учасників протягом тижня',
                    status=status_values[(org_index + local_index) % len(status_values)],
                    created_by=org_coordinators[local_index % len(org_coordinators)],
                )
                initiative.required_skills.set([
                    skills[(skill_index + offset * 3 + org_index) % len(skills)]
                    for offset in range(5)
                ])
                initiatives.append(initiative)
        return initiatives

    def create_shifts(self, initiatives):
        pending = []
        start_times = [(9, 0), (13, 30), (17, 0)]
        for idx, initiative in enumerate(initiatives):
            for slot, (hour, minute) in enumerate(start_times, start=1):
                start = time(hour, minute)
                end = time(min(hour + 3, 22), minute)
                pending.append(Shift(
                    initiative=initiative,
                    title=f'Зміна {slot}: {["ранкова", "денна", "вечірня"][slot - 1]}',
                    shift_date=initiative.start_date + timedelta(days=slot - 1),
                    start_time=start,
                    end_time=end,
                    location=initiative.location_address,
                    max_volunteers=8 + ((idx + slot) % 5),
                    approved_count=0,
                    status=Shift.Statuses.OPEN,
                ))
        created = Shift.objects.bulk_create(pending, batch_size=500)
        shifts_by_initiative = defaultdict(list)
        for shift in created:
            shifts_by_initiative[shift.initiative_id].append(shift)
        return shifts_by_initiative

    def create_applications(self, volunteers, initiatives, shifts_by_initiative):
        pending = []
        initiative_counts = defaultdict(int)
        shift_counts = defaultdict(int)
        status_cycle = [
            Application.Statuses.APPROVED,
            Application.Statuses.ATTENDED,
            Application.Statuses.SUBMITTED,
            Application.Statuses.UNDER_REVIEW,
            Application.Statuses.APPROVED,
            Application.Statuses.REJECTED,
            Application.Statuses.CANCELLED,
            Application.Statuses.MISSED,
        ]
        for volunteer_index, volunteer in enumerate(volunteers):
            for offset in range(16):
                initiative = initiatives[(volunteer_index * 7 + offset * 3) % len(initiatives)]
                shifts = shifts_by_initiative[initiative.id]
                shift = shifts[offset % len(shifts)]
                status = status_cycle[(volunteer_index + offset) % len(status_cycle)]
                pending.append(Application(
                    volunteer=volunteer,
                    initiative=initiative,
                    shift=shift,
                    status=status,
                    motivation_text=(
                        f'Хочу долучитися до ініціативи "{initiative.title}", бо маю релевантний досвід, '
                        f'можу працювати в команді та готовий відповідально закрити зміну.'
                    ),
                    coordinator_comment=(
                        'Заявку опрацьовано: волонтер отримав базові інструкції та може бути залучений до зміни.'
                        if status in [Application.Statuses.APPROVED, Application.Statuses.ATTENDED]
                        else ''
                    ),
                    rejection_reason='Не збіглася доступність із графіком зміни.' if status == Application.Statuses.REJECTED else '',
                    cancel_reason='Волонтер повідомив про зміну особистого графіка.' if status == Application.Statuses.CANCELLED else '',
                ))
                if status in [Application.Statuses.APPROVED, Application.Statuses.ATTENDED]:
                    initiative_counts[initiative.id] += 1
                    shift_counts[shift.id] += 1
        applications = Application.objects.bulk_create(pending, batch_size=1000)
        for initiative in initiatives:
            initiative.approved_volunteers_count = initiative_counts[initiative.id]
        Initiative.objects.bulk_update(initiatives, ['approved_volunteers_count'], batch_size=500)
        all_shifts = [shift for shifts in shifts_by_initiative.values() for shift in shifts]
        for shifts in shifts_by_initiative.values():
            for shift in shifts:
                shift.approved_count = shift_counts[shift.id]
                shift.status = Shift.Statuses.FULL if shift.approved_count >= shift.max_volunteers else Shift.Statuses.OPEN
        Shift.objects.bulk_update(all_shifts, ['approved_count', 'status'], batch_size=500)
        return applications

    def create_hours(self, volunteers, applications, coordinators):
        pending = []
        apps_by_volunteer = {}
        for app in applications:
            apps_by_volunteer.setdefault(app.volunteer_id, []).append(app)
        for volunteer_index, volunteer in enumerate(volunteers):
            eligible = [
                app for app in apps_by_volunteer[volunteer.id]
                if app.status in [Application.Statuses.APPROVED, Application.Statuses.ATTENDED]
            ]
            source_apps = eligible or apps_by_volunteer[volunteer.id]
            while len(source_apps) < 16:
                source_apps = source_apps + source_apps
            for offset, app in enumerate(source_apps[:16]):
                status = VolunteerHour.Statuses.APPROVED if offset < 13 else (
                    VolunteerHour.Statuses.SUBMITTED if offset == 13 else VolunteerHour.Statuses.REJECTED
                )
                reviewed = status != VolunteerHour.Statuses.SUBMITTED
                pending.append(VolunteerHour(
                    volunteer=volunteer,
                    initiative=app.initiative,
                    shift=app.shift,
                    hours=Decimal(str(2 + ((volunteer_index + offset) % 5) + Decimal('0.5'))),
                    description=(
                        f'Виконав задачі зміни "{app.shift.title if app.shift else "Загальна участь"}": '
                        f'підготовка матеріалів, робота з учасниками, фіксація результатів і передача інформації координатору.'
                    ),
                    status=status,
                    reviewed_by=coordinators[(volunteer_index + offset) % len(coordinators)] if reviewed else None,
                    review_comment='Години підтверджені за описом і звітом координатора.' if status == VolunteerHour.Statuses.APPROVED else (
                        'Потрібно уточнити підтвердження участі.' if status == VolunteerHour.Statuses.REJECTED else ''
                    ),
                    submitted_at=timezone.now() - timedelta(days=offset + volunteer_index),
                    reviewed_at=timezone.now() - timedelta(days=offset) if reviewed else None,
                ))
        return VolunteerHour.objects.bulk_create(pending, batch_size=1000)

    def create_certificates(self, hours):
        certificate_index = 1
        pending = []
        for hour in hours:
            if hour.status != VolunteerHour.Statuses.APPROVED:
                continue
            pending.append(Certificate(
                volunteer=hour.volunteer,
                initiative=hour.initiative,
                organization=hour.initiative.organization,
                approved_hours=hour.hours,
                certificate_number=f'VH-2026-{certificate_index:05d}',
                issue_date=timezone.localdate() - timedelta(days=certificate_index % 60),
                status=Certificate.Statuses.ISSUED,
            ))
            certificate_index += 1
        Certificate.objects.bulk_create(pending, batch_size=1000)

    def create_messages(self, applications, coordinators):
        statuses = [
            MessageThread.Statuses.OPEN,
            MessageThread.Statuses.WAITING_FOR_VOLUNTEER,
            MessageThread.Statuses.WAITING_FOR_COORDINATOR,
            MessageThread.Statuses.RESOLVED,
        ]
        org_coordinators = {
            org.id: list(org.coordinators.all().order_by('email'))
            for org in Organization.objects.prefetch_related('coordinators')
        }
        pending_threads = []
        thread_coordinators = []
        for idx, app in enumerate(applications):
            available = org_coordinators[app.initiative.organization_id]
            coordinator = available[idx % len(available)]
            pending_threads.append(MessageThread(
                volunteer=app.volunteer,
                coordinator=coordinator,
                initiative=app.initiative,
                application=app,
                subject=f'Участь у «{app.initiative.title}»',
                status=statuses[idx % len(statuses)],
            ))
            thread_coordinators.append(coordinator)
        threads = MessageThread.objects.bulk_create(pending_threads, batch_size=1000)
        messages = []
        for idx, thread in enumerate(threads):
            app = applications[idx]
            coordinator = thread_coordinators[idx]
            messages.append(Message(
                thread=thread,
                sender=app.volunteer,
                message_text='Доброго дня! Підтверджую готовність долучитися та прошу надіслати короткі інструкції щодо зміни.',
                is_read=idx % 3 == 0,
            ))
            messages.append(Message(
                thread=thread,
                sender=coordinator,
                message_text='Вітаю! Дякую за заявку. За день до зміни надішлемо фінальні деталі, адресу збору та контакт відповідального.',
                is_read=idx % 4 == 0,
            ))
        Message.objects.bulk_create(messages, batch_size=1000)

    def create_notifications(self, admin, managers, coordinators, volunteers):
        pending = []
        for idx in range(22):
            pending.append(Notification(
                user=admin,
                type='admin_digest',
                title=f'Адмін-дайджест #{idx + 1}',
                body='Платформа має нові заявки, оновлені години та записи журналу дій для перегляду адміністратором.',
                is_read=idx % 2 == 0,
            ))
        for user_group, prefix in [(managers, 'manager_digest'), (coordinators, 'coordinator_queue')]:
            for user_index, user in enumerate(user_group):
                for idx in range(16):
                    pending.append(Notification(
                        user=user,
                        type=prefix,
                        title=f'Оновлення черги #{idx + 1}',
                        body='У ваших організаціях є заявки, зміни або години, які потребують перегляду та координації.',
                        is_read=(idx + user_index) % 3 == 0,
                    ))
        for volunteer_index, volunteer in enumerate(volunteers):
            for idx in range(18):
                pending.append(Notification(
                    user=volunteer,
                    type='volunteer_activity',
                    title=f'Оновлення участі #{idx + 1}',
                    body='Статус заявки, години або сертифікат оновлено. Перевірте деталі у своєму кабінеті волонтера.',
                    is_read=(idx + volunteer_index) % 4 == 0,
                ))
        Notification.objects.bulk_create(pending, batch_size=1000)

    def create_audit_logs(self, admin, managers, coordinators, initiatives):
        actors = [admin] + managers + coordinators
        actions = [
            'seed_created_user', 'seed_created_organization', 'seed_published_initiative',
            'seed_reviewed_application', 'seed_approved_hours', 'seed_issued_certificate',
        ]
        pending = []
        for idx, initiative in enumerate(initiatives[:72]):
            pending.append(AuditLog(
                actor=actors[idx % len(actors)],
                action=actions[idx % len(actions)],
                entity_type='Initiative',
                entity_id=initiative.id,
                details_json={
                    'seed': True,
                    'title': initiative.title,
                    'organization': initiative.organization.name,
                },
            ))
        AuditLog.objects.bulk_create(pending, batch_size=500)

    def upload_seed_image(self, kind, slug, filename):
        if self.skip_media or not self.cloudinary_ready:
            return ''
        cache_key = (kind, slug)
        if cache_key in self.media_cache:
            return self.media_cache[cache_key]
        source = self.photos_dir / filename
        if not source.exists():
            self.stdout.write(self.style.WARNING(f'Missing seed photo: {source}'))
            return ''
        public_id = f'media/seed/{kind}/{slug}'
        try:
            result = cloudinary.uploader.upload(
                str(source),
                public_id=public_id,
                overwrite=True,
                invalidate=True,
                resource_type='image',
                tags=['volunteer_hub_seed'],
            )
            self.media_cache[cache_key] = result['public_id']
            return result['public_id']
        except Exception as exc:  # pragma: no cover - depends on external service
            self.stdout.write(self.style.WARNING(f'Cloudinary upload failed for {slug}: {exc}'))
            return ''

    def write_accounts_file(self):
        output_dir = settings.BASE_DIR / 'output'
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / 'seed_accounts.md'
        role_names = dict(User.Roles.choices)
        lines = [
            '# Seed accounts',
            '',
            'Цей файл перезаписується командою `python manage.py seed`.',
            '',
            '| Роль | ПІБ | Email | Пароль |',
            '| --- | --- | --- | --- |',
        ]
        for role, full_name, email, password in self.accounts:
            lines.append(f'| {role_names.get(role, role)} | {full_name} | `{email}` | `{password}` |')
        path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        self.stdout.write(f'accounts: {path}')
