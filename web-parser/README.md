# Парсер каталога сайта → Excel

Скрипт обходит каталог интернет-магазина со всеми страницами пагинации, открывает карточку каждого товара
и складывает данные в готовую таблицу Excel (плюс CSV). Ничего не нужно собирать руками: одна команда —
один файл.

Демо работает на публичной учебной песочнице <https://books.toscrape.com/> — сайте, который специально
создан для тренировки парсинга. Данные там вымышленные, никакие чужие каталоги не использовались.

## Что собирается

Для каждого товара: название, цена (число), остаток на складе (число), рейтинг 1–5 (число), категория,
UPC (артикул), ссылка на картинку, ссылка на карточку товара.

Файл `.xlsx` содержит два листа:

- **Books** — таблица товаров: оформленная шапка, автофильтр, закреплённая первая строка, ширина столбцов,
  цена и остаток — настоящие числа (по ним работают сортировка, фильтр и формулы), ссылка на карточку —
  кликабельная.
- **Summary** — сводка: количество книг по категориям, средняя / минимальная / максимальная цена и итоговая строка.

Рядом лежит `.csv` в UTF-8 с BOM — Excel открывает его с правильной кодировкой.

## Как запустить

Python 3.9+.

```bash
python -m venv .venv
.venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

python catalog_parser.py --limit 60 --out sample-output/books.xlsx     # первые 60 книг
python catalog_parser.py --category Mystery --out output/mystery.xlsx  # одна категория целиком
python catalog_parser.py --out output/books.xlsx                       # весь каталог (1000 книг)
```

| Параметр | Что делает |
|---|---|
| `--limit N` | остановиться после N товаров (лишние страницы не запрашиваются) |
| `--category Имя` | только одна категория, имя как на сайте (без учёта регистра); при ошибке покажет список доступных |
| `--out путь.xlsx` | куда сохранить; CSV и файл контрольной точки ложатся рядом |
| `--delay 0.7` | пауза между запросами, секунды (к ней добавляется небольшой случайный разброс) |
| `--retries 4` | сколько раз повторять запрос при сбое |
| `--checkpoint путь` / `--fresh` | свой файл контрольной точки / начать заново |
| `--base-url`, `--user-agent`, `--timeout` | адрес старта, имя клиента, таймаут запроса |

## Вежливый и устойчивый обход

- Пауза между запросами и собственный `User-Agent` с описанием скрипта; сайт не перегружается.
- Повторы с нарастающей паузой (1,5 → 3 → 6 → 12 с) при обрыве связи, таймауте, ответах 429 и 5xx;
  заголовок `Retry-After` учитывается. Ответ 404 не повторяется — это факт о странице, а не сбой.
- Контрольная точка: каждый собранный товар сразу дописывается в `*.checkpoint.jsonl`. Если обход прервали
  (Ctrl+C, обрыв сети), та же команда продолжит с места остановки, а не начнёт заново. Повторный запуск с
  большим `--limit` скачивает только недостающие товары.
- Страница с ошибкой не роняет весь прогон: она пропускается, в конце скрипт сообщает, сколько пропущено.
- Файлы записываются через временный файл с последующим переименованием — оборванный запуск не оставит
  наполовину записанный `.xlsx`.

## Результат

Реальный прогон `--limit 60`: 60 товаров, 63 запроса (3 страницы каталога + 60 карточек), около 50 секунд.
Весь каталог (1000 товаров, 50 страниц) при тех же настройках — порядка 15 минут (оценка по этому прогону).
Файлы — в [`sample-output/`](sample-output). Первые 5 строк листа Books:

| Title | Price, GBP | In stock | Rating | Category | UPC |
|---|---:|---:|---:|---|---|
| A Light in the Attic | 51.77 | 22 | 3 | Poetry | a897fe39b1053632 |
| Tipping the Velvet | 53.74 | 20 | 1 | Historical Fiction | 90fa61229261140a |
| Soumission | 50.10 | 20 | 1 | Fiction | 6957f44c3847a760 |
| Sharp Objects | 47.82 | 20 | 4 | Mystery | e00eb4fd7b871a48 |
| Sapiens: A Brief History of Humankind | 54.23 | 20 | 5 | History | 4165285e1663650f |

В столбцах также есть `Image URL` и `Product URL` — ссылки на картинку и карточку товара.

## Как адаптировать под другой сайт

Всё, что знает разметку сайта, собрано в пяти небольших функциях `catalog_parser.py`:
`parse_listing` (ссылки на товары на странице списка), `find_next_page` (следующая страница),
`parse_categories` (список категорий), `parse_product` (поля карточки) и список `COLUMNS` (какие столбцы
попадут в таблицу). Пауза, повторы, контрольная точка, запись в Excel/CSV и командная строка от сайта не
зависят. Типовая адаптация: поменять CSS-селекторы под новый сайт, добавить или убрать поля — и
обновить тест на сохранённой странице нового сайта.

## Тесты

```bash
pytest -q
```

38 тестов, работают без интернета на четырёх HTML-страницах, один раз скачанных с сайта (`fixtures/`: первая и
последняя страницы каталога, страница категории, карточка товара): разбор карточки (цена, остаток, рейтинг, категория, UPC, картинка), товар «нет в
наличии» и страница другого сайта, определение следующей страницы и последней страницы, категории,
обход с поддельным сервером (лимит, пагинация, категория, продолжение с контрольной точки, оборванная
последняя строка контрольной точки, пропуск битой карточки), повторы с нарастающей паузой и учётом
`Retry-After`, типы и оформление в `.xlsx`, лист Summary, кодировка CSV.

## Границы

- Парсер читает обычный HTML. Сайты, где каталог строится JavaScript'ом, требуют браузерного режима или
  обращения к их API — это отдельная доработка.
- Перед парсингом реального сайта проверяют его правила (`robots.txt`, условия использования) и
  подбирают паузу под него. Обход закрытых разделов, капчи и защиты от ботов в задачу не входит.
- Демо проверено на одном сайте; для другого сайта селекторы и тест нужно проверить заново.

Автор: Максим.

---

## English summary

A command-line crawler that walks a paginated product catalogue, opens every product page and writes the
result to a formatted Excel workbook (header row, autofilter, frozen header, numeric price / stock /
rating columns, a Summary sheet with per-category counts and average price) plus a CSV.

The demo target is the public scraping sandbox <https://books.toscrape.com/>.

```bash
pip install -r requirements.txt
python catalog_parser.py --limit 60 --out sample-output/books.xlsx
python catalog_parser.py --category Mystery --out output/mystery.xlsx
pytest -q          # 38 offline tests on saved HTML fixtures
```

Polite by design: delay with jitter between requests, an identifying User-Agent, retries with exponential
backoff (honours `Retry-After`), and a JSONL checkpoint so an interrupted run resumes instead of restarting.
Site-specific markup lives in a handful of small functions (`parse_listing`, `find_next_page`,
`parse_categories`, `parse_product`, `COLUMNS`), so adapting it to another HTML catalogue means changing
selectors and fields. JavaScript-rendered sites need a browser-based or API-based variant.

Author: Maxim.
