# Ozon Seller API ⇄ Excel: товары, цены, остатки, заказы FBS

Консольная программа на Python. Забирает данные магазина из Ozon Seller API в аккуратный `.xlsx`,
принимает обратно таблицу, которую вы отредактировали, и обновляет цены и остатки — сначала показывает,
что изменится, и только с флагом `--apply` отправляет. Автор: Максим.

Это демонстрационный проект. Данные в `ozon_sync/fixtures/` и в `sample-output/` **синтетические** (выдуманный магазин,
выдуманные цифры). Реальный API в тестах не вызывается: ключей нет, все 54 теста идут офлайн.
Подробности о том, что проверено, а что нет, — в разделе «Что проверено и что нет».

## Что получает продавец

| Команда | Результат |
|---|---|
| `export-products` | `.xlsx` со всеми товарами: артикул, название, цена, цена до скидки, минимальная цена, остатки FBS (с резервом) и FBO. Заголовок закреплён, фильтры включены, редактируемые столбцы подсвечены |
| `update файл.xlsx` | **Dry-run по умолчанию**: таблица «было → станет» по каждому изменённому полю, ничего не отправляется |
| `update файл.xlsx --apply` | Отправка пачками в рамках лимитов API, при 429 — повтор с паузой; в конце отчёт по каждому товару |
| `export-postings --from … --to …` | `.xlsx` с отправлениями FBS за период: по строке на товарную позицию, время в вашем часовом поясе, сумма по строке |
| `warehouses` | Список складов и их `warehouse_id` (нужен для обновления остатков) |

Что защищает от ошибок при загрузке таблицы:

- пустая ячейка означает «не менять»; строки, где ничего не изменилось, в отправку не попадают;
- неизвестный артикул, дубликат артикула, отрицательный или дробный остаток, текст вместо числа,
  цена ≤ 0, «цена до скидки» не выше цены, «минимальная цена» выше цены — программа показывает таблицу ошибок с номерами
  строк Excel и **ничего не отправляет** (или с `--skip-invalid` пропускает только плохие строки);
- изменение цены больше чем на 50 % (типичная опечатка: 1290 → 12900) помечается «!», и `--apply` его не отправит
  без `--allow-big-change`;
- если нужно менять остатки, а складов несколько, `--warehouse-id` обязателен; цены в этом случае тоже не уходят
  (всё или ничего).

## Как получить Client-Id и Api-Key

1. Личный кабинет продавца Ozon → **Настройки → API-ключи**.
2. **Сгенерировать ключ**, выбрать роль. Для этой программы достаточно роли с доступом к товарам, ценам, остаткам и
   отправлениям FBS; для режима «только выгрузка» — роли только на чтение.
3. `Client-Id` — числовой идентификатор продавца, `Api-Key` — длинная строка-ключ (показывается при создании).
4. Положите их в файл `.env` рядом с программой (образец — `.env.example`; `.env` не попадает в Git) или задайте переменные
   окружения `OZON_CLIENT_ID`, `OZON_API_KEY`. Ключи нигде не печатаются.

## Установка и команды

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt     # только openpyxl

# 1. выгрузка каталога
.venv\Scripts\python -m ozon_sync export-products -o out\products.xlsx

# 2. правите жёлтые столбцы в Excel, затем
.venv\Scripts\python -m ozon_sync update out\products.xlsx                      # показать изменения (dry-run)
.venv\Scripts\python -m ozon_sync warehouses                                    # узнать warehouse_id
.venv\Scripts\python -m ozon_sync update out\products.xlsx --apply --warehouse-id 22134510000

# 3. заказы FBS за период (включительно, часовой пояс по умолчанию Москва, UTC+3)
.venv\Scripts\python -m ozon_sync export-postings --from 2026-10-01 --to 2026-10-07 -o out\orders.xlsx
.venv\Scripts\python -m ozon_sync export-postings --from 2026-10-01 --to 2026-10-31 --status delivered
```

**Попробовать без ключей:** добавьте `--demo` перед командой, и программа поработает на встроенных синтетических
данных (изменения живут только в памяти процесса):

```powershell
.venv\Scripts\python -m ozon_sync --demo update sample-output\products_edited.xlsx
```

Коды возврата: `0` — готово; `1` — API отклонил часть изменений или сбой; `2` — вход не принят (ошибки в таблице, нет ключей,
неверные аргументы), ничего не отправлено.

## Пример вывода

`update sample-output\products_edited.xlsx` (dry-run, файл `sample-output/update_dry_run.txt`):

```text
Артикул    Поле            Сейчас      Станет  Внимание
---------  --------------  ------  --  ------  --------
KR-350-WH  Цена            390     ->  420
KR-350-WH  Остаток FBS     120     ->  150
PL-150-GR  Цена            1290    ->  1390
PL-150-GR  Цена до скидки  1790    ->  1890
SH-LED-3M  Остаток FBS     0       ->  40
TR-USB-C1  Остаток FBS     210     ->  190

Строк без изменений: 10. К отправке: цены — 2 товаров, остатки — 3 товаров.
Режим dry-run: ничего не отправлено. Добавьте --apply, чтобы применить.
```

`update sample-output\products_edited_with_errors.xlsx` (`sample-output/update_with_errors.txt`):

```text
Строк с ошибками в таблице: 4
Строка  Артикул      Код                    Проблема
------  -----------  ---------------------  -----------------------------------------------------------
8       CT-BAM-S     negative_stock         отрицательный остаток: -5
10      OR-BOX-3     bad_number             price: «тысяча» не число
13      LM-DSK-W     old_price_below_price  цена до скидки (2490) должна быть больше цены (12900) или 0
16      NO-SUCH-SKU  unknown_sku            артикул не найден в каталоге Ozon

Ничего не отправлено. Исправьте файл или запустите с --skip-invalid.
```

Выгрузка товаров (`sample-output/products.xlsx`, первые строки):

| Артикул | ID товара | Название | Цена | Цена до скидки | Мин. цена | Остаток FBS | Резерв | Остаток FBO |
|---|---|---|---|---|---|---|---|---|
| KR-350-WH | 1804000100 | Кружка керамическая 350 мл, белая | 390 | 520 | 340 | 120 | 4 | 80 |
| KR-350-BK | 1804000107 | Кружка керамическая 350 мл, чёрная | 390 | 520 | 340 | 95 | 2 | 60 |
| PL-150-GR | 1804000114 | Плед флисовый 150x200 см, серый | 1290 | 1790 | 1100 | 34 | 3 | 12 |

Выгрузка заказов (`sample-output/postings_2026-10-01_07.xlsx`): 5 отправлений, 7 товарных строк за 1–7 октября.

## Какие методы Ozon используются

| Задача | Метод | Пагинация и лимит в программе |
|---|---|---|
| Список товаров | `POST /v3/product/list` | `last_id`, по 1000, до пустой страницы |
| Названия | `POST /v3/product/info/list` | до 1000 `offer_id` за запрос |
| Цены | `POST /v5/product/info/prices` | `cursor`, до 1000 `offer_id` за запрос |
| Остатки | `POST /v4/product/info/stocks` | `cursor`, до 1000 `offer_id` за запрос |
| Обновить остатки | `POST /v2/products/stocks` | до 100 позиций за запрос |
| Обновить цены | `POST /v1/product/import/prices` | до 1000 позиций за запрос |
| Отправления FBS | `POST /v3/posting/fbs/list` | `offset` + `has_next`, страницы по 100; `filter.since` / `filter.to` в UTC |
| Склады | `POST /v1/warehouse/list` | — |

Базовый адрес `https://api-seller.ozon.ru`, заголовки `Client-Id` и `Api-Key`. Лимиты вынесены в константы
`ozon_sync/client.py`, а тестовый сервер отвечает 400 при их превышении, так что тесты на пачки не «проходят вхолостую».

Источник: справочник методов Ozon Seller API, <https://docs.ozon.ru/api/seller/>; смена версий методов — в
уведомлениях Ozon об изменениях API (<https://t.me/s/OzonEnSellerAPI>). Дата обращения к источникам: **2026-10-19**.

## Что проверено и что нет

- **Проверено:** вся логика программы (пагинация, пачки, diff, валидация, повтор при 429, фильтр дат, форматы xlsx) на
  локальном тестовом сервере и записанных синтетических ответах; повтор при 429 дополнительно — по настоящему
  HTTP-соединению к локальному серверу.
- **Не проверено:** вызовы настоящего Ozon (нет ключей). 2026-10-19 страница `docs.ozon.ru/api/seller` не открылась при
  автоматическом чтении (бесконечные редиректы), поэтому пути методов сверены по перечню методов и уведомлениям об изменениях
  (январь–февраль 2026: `/v3/product/list`, `/v5/product/info/prices`, `/v4/product/info/stocks`, `/v3/posting/fbs/list`
  — методы актуальны), а точные имена полей ответов и числовые лимиты (100 / 1000 / размер страницы отправлений) взяты из
  справочника в том виде, как он мне известен. Перед первым боевым запуском нужна сверка со справочником и один пробный
  `export-products` с read-only ключом — в первую очередь поля `price` в ответе `/v5/product/info/prices` и `auto_action_enabled` /
  `price_strategy_enabled` в `/v1/product/import/prices`. Если поле называется иначе, правка занимает одно место в `ozon_sync/client.py`.
- Остаток `stock` в `/v2/products/stocks` — это новое количество на выбранном складе FBS; «Остаток FBS» в таблице — сумма
  `present` по записям типа `fbs`. Типы остатков кроме `fbs`/`fbo` (например, rFBS) не выгружаются.
- Лимит Ozon на частоту обновлений (например, не чаще раза в час на цену одного товара) программа не отслеживает: при ответе с
  ошибкой она будет показана в отчёте по товару.
- Время отправлений в Excel показано в часовом поясе `--utc-offset` (по умолчанию Москва), в запросе к API — в UTC.

## Ограничения. Wildberries

Wildberries **не реализован**. Как его добавить:

1. Слой таблиц (`sheets.py`) и план изменений (`plan.py`: валидация, diff, защита от опечаток) от площадки не зависят.
2. Нужен второй клиент с тем же набором методов, что у `OzonClient`: `fetch_catalog()`, `update_prices()`, `update_stocks()`,
   `list_postings()`. У Wildberries несколько доменов API и токен в заголовке `Authorization`; часть методов — `GET`/`PUT`, поэтому
   интерфейс `Transport` расширяется до `request(method, path, payload)` — это изменение в одном файле (`transport.py`).
3. Ключ строки — артикул продавца (`vendorCode`) / баркод размера, остатки идут по складу (`warehouseId`) через баркоды, цены и
   скидка — отдельным методом. Точные пути и лимиты нужно взять из актуальной документации <https://dev.wildberries.ru> —
   в этом проекте они не проверялись.
4. Тесты строятся так же: фальшивый сервер с лимитами, фикстуры, те же сценарии (страницы, пачки, 429, ошибки таблицы).

## Структура

```text
ozon_sync/transport.py   HTTP-слой: интерфейс Transport, HttpTransport (urllib), RetryingTransport (429/502/503/504)
ozon_sync/client.py      методы Ozon: пагинация, пачки, разбор ответов
ozon_sync/plan.py        проверка таблицы продавца, diff, вывод таблиц
ozon_sync/sheets.py      чтение и запись .xlsx (openpyxl)
ozon_sync/fake.py        локальный «Ozon» для тестов и --demo (лимиты, курсоры, фильтр дат)
ozon_sync/fixtures/      синтетические ответы (tools/generate_fixtures.py)
tests/                   54 офлайн-теста pytest
sample-output/           примеры файлов и вывода
```

Запуск тестов: `.venv\Scripts\python -m pip install -r requirements-dev.txt` и `.venv\Scripts\python -m pytest -q`.

---

## English summary

A Python CLI (author: Maxim) that syncs an Ozon seller account with Excel through the Ozon Seller API
(`https://api-seller.ozon.ru`, headers `Client-Id` / `Api-Key`):

- `export-products` writes products with prices and FBS/FBO stocks to a formatted `.xlsx`;
- `update file.xlsx` compares the edited sheet with live data and prints a before/after diff; it is a **dry run by default**,
  `--apply` sends the changes in batches within the API limits (stocks 100 per request, prices 1000), retrying 429 with back-off
  and honouring `Retry-After`; a sheet with a bad SKU, a negative or fractional stock, text instead of a number or inconsistent prices is
  rejected as a whole before anything is sent;
- `export-postings --from --to` writes FBS postings for a date range (inclusive, in the seller's timezone).

The HTTP layer sits behind a one-method `Transport` interface, so all 54 pytest tests run offline against an in-memory fake API
(plus one local HTTP server for the 429 round trip). No real Ozon calls were made: there are no keys, the fixtures are synthetic,
and the exact response field names and limits must be checked against the live reference before the first production run (see
"Что проверено и что нет"). Wildberries is not implemented; the table and diff layers are marketplace-independent, a second
client with the same four methods would be added next to `OzonClient`.

`python -m ozon_sync --demo update sample-output/products_edited.xlsx` runs the whole flow with no keys.
