# Form Leads Router — заявки с сайта в таблицу, Telegram и почту

Автор: Максим. Небольшой веб-сервис (Python, Flask): принимает заявки из форм на Tilda,
WordPress (Contact Form 7) или из любой самописной формы и сразу раскладывает каждую заявку в три места:

1. строка в Google Таблице;
2. сообщение в Telegram (личка, группа или канал);
3. письмо на почту.

Заявка не теряется, даже если один из каналов временно недоступен: она сохраняется в локальной
базе (SQLite) и досылается автоматически с нарастающей паузой.

*English summary is at the bottom.*

## Что получает клиент

- Каждая заявка приходит сразу в три канала: менеджер видит её в Telegram, бухгалтер в таблице, отдел продаж на почте.
- Телефон приводится к виду `+79991234567` (из `8 (999) 123-45-67`, `+7 999 123 45 67`, `9991234567`).
- Проверяется email; нужен хотя бы телефон или email. Ошибки возвращаются понятным JSON, а не молча теряются.
- Защита от спама: скрытое поле-ловушка (honeypot). Бот его заполняет, человек не видит. Заявка бота тихо отбрасывается.
- Защита от дублей: повторная отправка (двойной клик, повтор от Tilda с тем же `tranid`, та же заявка в течение
  10 минут) не создаёт вторую запись.
- Если Telegram, почта или Google лежат, заявка остаётся в очереди и уходит позже. Посетитель сайта при этом видит
  «успешно отправлено».
- Проверка из Tilda при сохранении вебхука (`test=test`) отвечает `200 ok` и ничего никуда не отправляет.
- Включены только те каналы, для которых заполнены настройки. Не нужна почта: оставьте `SMTP_*` пустыми.

## Как выглядит результат

Сообщение в Telegram:

```text
Новая заявка с сайта
Имя: Анна Петрова
Телефон: +79991234567
Email: anna.petrova@example.com
Сообщение: Нужен лендинг на Тильде, срок две недели.
Источник: Tilda
Форма: form123456
Город: Казань
Время: 14.10.2026 20:46
```

Строка в Google Таблице (первая строка с заголовками создаётся сама):

| Дата | Имя | Телефон | Email | Сообщение | Источник | Форма | Страница | Доп. поля | ID заявки |
|---|---|---|---|---|---|---|---|---|---|
| 2026-10-14 20:46:40 | Анна Петрова | +79991234567 | anna.petrova@example.com | Нужен лендинг на Тильде, срок две недели. | Tilda | form123456 |  | Город=Казань | a1b2c3d4 |

Письмо: тема `Новая заявка с сайта: Анна Петрова`, в теле те же поля; в `Reply-To` стоит email клиента,
так что «Ответить» пишет сразу ему.

## Установка

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt        # Windows: .venv\Scripts\pip
cp .env.example .env                              # заполнить своими значениями
.venv/bin/python -m leadrouter serve --port 8000  # для разработки
```

Секреты (токен бота, пароль почты, JSON сервисного аккаунта) лежат только в `.env` и в файле JSON на вашем сервере.
В репозиторий они не попадают (`.gitignore`).

### Что нужно подготовить

| Канал | Что сделать |
|---|---|
| Google Таблица | В Google Cloud создать сервисный аккаунт, скачать JSON-ключ, включить Google Sheets API. Открыть таблицу, дать доступ «Редактор» адресу `client_email` из JSON. В `.env`: `SHEETS_CREDENTIALS_FILE`, `SHEETS_SPREADSHEET_ID` (часть URL между `/d/` и `/edit`), при необходимости `SHEETS_WORKSHEET`. |
| Telegram | Создать бота у @BotFather, взять токен; добавить бота в нужный чат (для канала сделать администратором); узнать `chat_id`. В `.env`: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. |
| Почта | Данные SMTP вашего провайдера (для Gmail и Яндекса нужен пароль приложения). В `.env`: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TO`. Порт 465 это SSL, остальные работают через STARTTLS. |

## Подключение Tilda

1. Опубликуйте сервис (см. «Развёртывание») и возьмите адрес вида
   `https://leads.example.com/webhook?key=ВАШ_WEBHOOK_SECRET`.
2. В Tilda: **Настройки сайта → Формы → Webhook** (раздел «Другие сервисы / Webhook») и вставьте этот URL, сохраните.
   Tilda отправит тестовый запрос `test=test`; сервис ответит `200 ok`.
3. В блоке с формой задайте латиницей имена переменных полей: `Name`, `Phone`, `Email`, `Textarea` (или `Comments`).
   Любые другие поля (например, `Город`, `Бюджет`) попадут в колонку «Доп. поля» и в сообщения.
4. Ловушка от ботов: добавьте в форму скрытое поле с именем `website` (в Tilda поле типа Hidden; если его нет в вашем блоке формы, ловушку можно добавить в Zero Block)
   и оставьте его пустым. Имена ловушек настраиваются в `HONEYPOT_FIELDS`.
5. Отправьте заявку с сайта и проверьте три канала.

Tilda передаёт данные как `application/x-www-form-urlencoded` (в UTF-8, кириллица поддерживается) и добавляет
служебные `tranid`, `formid`, `COOKIES`. `tranid` используется для защиты от дублей и в таблицу не попадает.

## Подключение WordPress (Contact Form 7)

1. Установите любой плагин, который отправляет заявки Contact Form 7 вебхуком в формате JSON
   (например, «CF7 to Webhook»), и укажите URL `https://leads.example.com/webhook?key=ВАШ_WEBHOOK_SECRET`.
2. Имена полей CF7 по умолчанию распознаются сразу: `your-name`, `your-phone`, `your-email`, `your-message`
   (также `name`, `phone`/`tel`, `email`, `message`/`comment`). Служебные поля `_wpcf7*` отбрасываются.
3. Для ловушки добавьте в форму скрытое поле `website` (плагины honeypot для CF7 тоже подходят: впишите
   имя их поля в `HONEYPOT_FIELDS`).

Самописная форма отправляет обычный `fetch`:

```js
fetch("https://leads.example.com/webhook?key=ВАШ_WEBHOOK_SECRET", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ name: "Иван", phone: "8 913 555 00 11", email: "ivan@mail.ru",
                         message: "Перезвоните", website: "" })   // website = ловушка, должно быть пустым
});
```

Ответ JSON: `{"status": "accepted", "lead_id": "...", "delivery": {"sheets": "done", "telegram": "pending", "email": "done"}}`.
Статусы: `accepted`, `duplicate`, `spam`, `test`. Ошибка валидации: HTTP 422 и `{"status": "invalid", "errors": {"phone": "Некорректный телефон"}}`.
Для запросов Tilda (форма) ответ всегда простой текст `ok`.

## Очередь и повторные отправки

Сначала заявка записывается в SQLite (таблицы `leads` и `outbox`), и только потом идёт в каналы. Если канал не ответил,
запись остаётся `pending` и повторяется с паузой 30 с, 1 мин, 2 мин ... (максимум 1 час), по умолчанию 8 попыток,
затем `dead` (заявка в базе остаётся, видна в `status`). Настройки: `MAX_ATTEMPTS`, `BACKOFF_BASE_SEC`, `BACKOFF_MAX_SEC`.

```bash
python -m leadrouter status            # сколько в очереди и какие ошибки
python -m leadrouter retry             # один проход по тем, кому пора (код выхода 1, если что-то не ушло)
python -m leadrouter retry --force     # игнорировать паузу
python -m leadrouter retry --loop 60   # крутиться и повторять раз в минуту
```

Простейший вариант: cron `* * * * * cd /opt/leadrouter && .venv/bin/python -m leadrouter retry` или отдельный
сервис с `retry --loop 60`. Повтор касается только того канала, который не сработал: остальные не дублируются.
Оговорка: если Google ответил ошибкой уже после записи строки (редкий случай), при повторе строка может появиться дважды;
поле «ID заявки» в таблице позволяет их найти.

## Развёртывание

Подойдёт любой VPS или Render/Railway-подобный хостинг, где можно запустить Python-процесс с HTTPS.

**VPS (Ubuntu), коротко**

```bash
git clone <репозиторий> /opt/leadrouter && cd /opt/leadrouter
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env && nano .env
.venv/bin/gunicorn "leadrouter.server:create_app_from_env()" --bind 127.0.0.1:8000 --workers 2
```

Поставьте перед ним nginx/Caddy с HTTPS (Let's Encrypt), а gunicorn запустите как systemd-сервис. Второй сервис или cron
выполняет `retry`. Проверка работоспособности: `GET /health`.

**Render и аналоги**: Build `pip install -r requirements.txt`, Start `gunicorn "leadrouter.server:create_app_from_env()"`
(есть `Procfile`), переменные из `.env.example` задайте в панели. На бесплатных тарифах диск временный: подключите
постоянный диск и укажите путь в `DB_PATH`, иначе очередь и список дублей обнулятся при перезапуске. Для `retry` нужен
второй процесс (Background Worker / Cron Job) с тем же диском.

## Тесты

```bash
pip install -r requirements-dev.txt
pytest -q
```

Тесты работают офлайн: Google, Telegram и SMTP подменены. Проверяются разбор Tilda (в том числе кириллица), JSON из
WordPress, ошибки валидации, дубли, honeypot, отказ одного канала с досылкой через очередь, тестовый запрос Tilda,
секретный ключ в URL, защита от подстановки заголовков письма.

## Структура

```text
leadrouter/normalize.py   разбор полей, телефон/email, Lead
leadrouter/router.py      конвейер: ловушка, валидация, дубли, очередь, рассылка, повтор
leadrouter/sinks.py       Google Sheets (gspread), Telegram (httpx), SMTP; интерфейс Sink
leadrouter/store.py       SQLite: дубли, заявки, очередь
leadrouter/server.py      Flask: POST /webhook, GET /health
leadrouter/cli.py         serve / retry / status
tests/                    pytest, офлайн
```

---

## English summary

A small Flask webhook service that takes site-form submissions (Tilda form-urlencoded webhooks, or JSON from
WordPress Contact Form 7 / any custom form), validates and normalises them (phone to `+7XXXXXXXXXX`, email check,
honeypot field, duplicate protection by `tranid` or content hash within 10 minutes) and fans each lead out to Google
Sheets (gspread, service account), a Telegram chat (Bot API) and email (SMTP).

A lead is written to a SQLite outbox before any network call. If one channel fails, only that channel is retried with
exponential backoff (`python -m leadrouter retry`, optionally `--loop 60`); the others are not repeated and nothing is
lost. Tilda's `test=test` ping returns `200 ok` without sending anything. Configuration is through environment
variables (`.env.example`, no secrets in the repository). Run `pytest -q`: the tests are fully offline with fake sinks.

Setup: Tilda: Site Settings, Forms, Webhook, URL `https://your-host/webhook?key=SECRET`; WordPress: any CF7-to-webhook
plugin pointed at the same URL. Deploy with gunicorn behind HTTPS on any VPS or PaaS (a persistent disk for `DB_PATH`
is required so the queue survives restarts).
