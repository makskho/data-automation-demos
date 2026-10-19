# Образцы: перевод и редактура / Samples: translation and editing

Автор образцов: Максим. Author of the samples: Maxim.

**Честно о происхождении.** Это демонстрационные образцы для портфолио. Ни один из них не является работой для клиента.
Переводы сделаны на открытых текстах (лицензии ниже), «черновики» для редактуры я написал сам специально для этого набора.

**Honest about origin.** These are portfolio demonstration samples. None of them is client work. The translations use openly
licensed or public-domain source texts (licences below); the "drafts" for the editing samples were written by me for this set.

---

## Русский

### Что здесь

| № | Образец | Файлы (папка `docx/`) | Что показывает |
|---|---|---|---|
| 1 | Перевод RU → EN, ~700 слов оригинала (история самоваров в России) | `01_RU-EN_samovar_side-by-side.docx` — таблица «оригинал / перевод» по абзацам, глоссарий, заметки, отчёт проверки; `01_RU-EN_samovar_clean-EN.docx` — чистый английский текст | исторический и информационный текст, имена, даты, числа, старые меры (пуд, фунт), единая транслитерация |
| 2 | Перевод EN → RU, ~580 слов оригинала (истощение подземных вод, USGS) | `02_EN-RU_groundwater_side-by-side.docx`; `02_EN-RU_groundwater_clean-RU.docx` | научно-популярный текст, терминология (водоносный горизонт, дебит скважины, вторжение солёных вод), единицы измерения, **найденная ошибка в оригинале** (см. заметки переводчика) |
| 3 | Литературная редактура (RU), рассказ ~930 слов | `03_literary-editing_RU_markup.docx` — правка с цветной разметкой (красное зачёркнутое — удалено, зелёное подчёркнутое — добавлено) и комментариями на полях, плюс «Заметка редактора»; `03_literary-editing_RU_tracked-changes.docx` — та же правка режимом исправлений Word; `…_draft.docx` — черновик; `…_edited.docx` — чистовик | стиль, ритм, повторы, штампы, тавтология, оформление прямой речи (тире, абзацы, регистр слов автора), запятые, согласование времён, вопросы к автору |
| 4 | Деловая редактура (EN), онбординг-документ стартапа ~410 слов | `04_business-editing_EN_markup.docx` (разметка, комментарии, таблица «Сводка изменений», вопросы к автору); `…_tracked-changes.docx`; `…_draft.docx`; `…_edited.docx` | правка грамматики и орфографии, жаргона, структуры, единообразия (время, числа, регистр), тона; вопросы автору вместо «додумывания» фактов |

### Источники и лицензии

| Образец | Источник | Лицензия | Примечание |
|---|---|---|---|
| 1 | [Википедия, «Самовар», раздел «В России»](https://ru.wikipedia.org/w/index.php?title=%D0%A1%D0%B0%D0%BC%D0%BE%D0%B2%D0%B0%D1%80&oldid=152954284) (ревизия 152954284 от 2026-05-02, получено 2026-10-19; авторы — участники русской Википедии, список в истории страницы) | CC BY-SA 4.0 | Перевод — производная работа и распространяется на тех же условиях, CC BY-SA 4.0. |
| 2 | [USGS, «Groundwater Decline and Depletion»](https://www.usgs.gov/water-science-school/science/groundwater-decline-and-depletion) (получено 2026-10-19) | Общественное достояние (работа федерального агентства США); указание источника — USGS, без подразумеваемого одобрения | Взяты 7 абзацев; фраза, вводившая список, опущена (пояснено в заметках). |
| 3 | Рассказ «Возвращение» — текст автора образцов | свой текст | Написан специально для демонстрации в стиле «авторского черновика» с типичными ошибками. Чужая рукопись не используется. |
| 4 | Онбординг-документ вымышленного стартапа «Pebblepath» | свой текст | Компания, люди и адреса электронной почты вымышлены. |

### Как проверялось качество

* **Числа** — автоматически: для каждой пары абзацев сверяется набор чисел (римские и порядковые формы, разделители тысяч,
  десятичный знак приводятся к одному виду). В образцах 1 и 2 расхождений нет (40 и 9 числовых значений).
* **Непереведённые слова** — автоматически: в английском тексте нет кириллицы; в русском нет латиницы, кроме цитаты
  библиографической ссылки (она оставлена на языке оригинала намеренно).
* **Единообразие терминов** — каждый термин из глоссария должен встречаться в переводе (12/12 и 16/16).
* **Имена, меры, числительные словами** — вручную по оригиналу, см. «Примечания переводчика» в файлах.
* Сборка завершается ошибкой, если проверка не пройдена.

### Как пересобрать

Тексты лежат в `src/` (Markdown), документы собирает `build_samples.py`:

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python build_samples.py
```

Для образцов 3 и 4 один исходный файл содержит и черновик, и правку (`{-удалено-}{+добавлено+}`, `^[комментарий]`), поэтому
«черновик», «чистовик» и версия с пометками не могут разойтись.

---

## English

### What is here

| # | Sample | Files (folder `docx/`) | What it shows |
|---|---|---|---|
| 1 | RU → EN translation, ~700 source words (history of the samovar in Russia) | `01_RU-EN_samovar_side-by-side.docx` — two-column table (source / translation) aligned by paragraph, glossary, notes, QA report; `01_RU-EN_samovar_clean-EN.docx` — clean English text | historical / informational text, names, dates, numbers, old units (pood, pound), consistent transliteration |
| 2 | EN → RU translation, ~580 source words (groundwater depletion, USGS) | `02_EN-RU_groundwater_side-by-side.docx`; `02_EN-RU_groundwater_clean-RU.docx` | popular-science text, hydrogeology terminology, units, **an error found in the source** (see the translator's notes) |
| 3 | Literary editing (Russian), a ~930-word short story | `03_literary-editing_RU_markup.docx` — coloured markup (red strikethrough = deleted, green underline = added) with margin comments and an editor's note; `03_literary-editing_RU_tracked-changes.docx` — the same edit as Word tracked changes; `…_draft.docx`; `…_edited.docx` | style, rhythm, repetition, clichés, tautology, Russian dialogue punctuation, commas, tense consistency, queries to the author |
| 4 | Business editing (English), a startup onboarding document of ~410 words | `04_business-editing_EN_markup.docx` (markup, comments, change-summary table, queries to the author); `…_tracked-changes.docx`; `…_draft.docx`; `…_edited.docx` | grammar and spelling, jargon, structure, consistency (time, numbers, capitalisation), tone; queries instead of invented facts |

### Sources and licences

| Sample | Source | Licence | Note |
|---|---|---|---|
| 1 | [Russian Wikipedia, "Самовар", section "В России"](https://ru.wikipedia.org/w/index.php?title=%D0%A1%D0%B0%D0%BC%D0%BE%D0%B2%D0%B0%D1%80&oldid=152954284) (revision 152954284 of 2026-05-02, retrieved 2026-10-19; authors: contributors to Russian Wikipedia, see the page history) | CC BY-SA 4.0 | The translation is a derivative work and is shared under the same licence, CC BY-SA 4.0. |
| 2 | [USGS, "Groundwater Decline and Depletion"](https://www.usgs.gov/water-science-school/science/groundwater-decline-and-depletion) (retrieved 2026-10-19) | Public domain (U.S. federal agency work); credit USGS, no endorsement implied | Seven paragraphs; a sentence that introduced a list was left out (explained in the notes). |
| 3 | The short story "Возвращение" — written by the author of these samples | own text | Written for this demo in the style of a rough author's draft with typical mistakes. No third-party manuscript is used. |
| 4 | Onboarding document of a fictional startup, "Pebblepath" | own text | The company, people and e-mail addresses are fictional. |

### How quality was checked

* **Numbers** — automatically: for each paragraph pair the multiset of numbers is compared (roman and ordinal forms, thousand
  separators and decimal signs are normalised). No differences in samples 1 and 2 (40 and 9 numeric values).
* **Untranslated words** — automatically: no Cyrillic in the English text; no Latin in the Russian text except the bibliographic
  reference, which is kept in its original language on purpose.
* **Terminology consistency** — every glossary rendering must appear in the translation (12/12 and 16/16).
* **Names, units, number words** — by hand against the source; see "Translator's notes" inside the files.
* The build fails if a check fails.

### How to rebuild

Texts live in `src/` (Markdown); `build_samples.py` generates the documents:

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python build_samples.py
```

For samples 3 and 4 one source file holds both the draft and the edit (`{-deleted-}{+added+}`, `^[comment]`), so the draft,
the clean edited text and the marked-up version cannot drift apart.
