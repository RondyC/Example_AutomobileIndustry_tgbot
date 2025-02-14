# Этап 1: Подготовка базы знаний телеграмм-бота

В этом примере используется статься из англоязычной версии википедии Automotive_industry
"""

# Отключим предупреждения в колабе. Будет меньше лишней информации в выводе
import warnings
warnings.filterwarnings('ignore')

!pip install openai mwclient mwparserfromhell tiktoken

# imports
import mwclient  # библиотека для работы с MediaWiki API для загрузки примеров статей Википедии
import mwparserfromhell  # Парсер для MediaWiki
import openai  # будем использовать для токинизации
import pandas as pd  # В DataFrame будем хранить базу знаний и результат токинизации базы знаний
import re  # для вырезания ссылок <ref> из статей Википедии
import tiktoken  # для подсчета токенов

# Задаем категорию и англоязычную версию Википедии для поиска
CATEGORY_TITLE = "Category:Automotive_industry"
WIKI_SITE = "en.wikipedia.org"

# Соберем заголовки всех статей
def titles_from_category(
    category: mwclient.listing.Category, # Задаем типизированный параметр категории статей
    max_depth: int # Определяем глубину вложения статей
) -> set[str]:
    """Возвращает набор заголовков страниц в данной категории Википедии и ее подкатегориях."""
    titles = set() # Используем множество для хранения заголовков статей
    for cm in category.members(): # Перебираем вложенные объекты категории
        if type(cm) == mwclient.page.Page: # Если объект является страницей
            titles.add(cm.name) # в хранилище заголовков добавляем имя страницы
        elif isinstance(cm, mwclient.listing.Category) and max_depth > 0: # Если объект является категорией и глубина вложения не достигла максимальной
            deeper_titles = titles_from_category(cm, max_depth=max_depth - 1) # вызываем рекурсивно функцию для подкатегории
            titles.update(deeper_titles) # добавление в множество элементов из другого множества
    return titles

# Инициализация объекта MediaWiki
# WIKI_SITE ссылается на англоязычную часть Википедии
site = mwclient.Site(WIKI_SITE)

# Загрузка раздела заданной категории
category_page = site.pages[CATEGORY_TITLE]
# Получение множества всех заголовков категории с вложенностью на один уровень
titles = titles_from_category(category_page, max_depth=1)


print(f"Создано {len(titles)} заголовков статей в категории {CATEGORY_TITLE}.")

# Задаем секции, которые будут отброшены при парсинге статей
SECTIONS_TO_IGNORE = [
    "See also",
    "References",
    "External links",
    "Further reading",
    "Footnotes",
    "Bibliography",
    "Sources",
    "Citations",
    "Literature",
    "Footnotes",
    "Notes and references",
    "Photo gallery",
    "Works cited",
    "Photos",
    "Gallery",
    "Notes",
    "References and sources",
    "References and notes",
]

# Функция возвращает список всех вложенных секций для заданной секции страницы Википедии

def all_subsections_from_section(
    section: mwparserfromhell.wikicode.Wikicode, # текущая секция
    parent_titles: list[str], # Заголовки родителя
    sections_to_ignore: set[str], # Секции, которые необходимо проигнорировать
) -> list[tuple[list[str], str]]:
    """
    Из раздела Википедии возвращает список всех вложенных секций.
    Каждый подраздел представляет собой кортеж, где:
      - первый элемент представляет собой список родительских секций, начиная с заголовка страницы
      - второй элемент представляет собой текст секции
    """

    # Извлекаем заголовки текущей секции
    headings = [str(h) for h in section.filter_headings()]
    title = headings[0]
    # Заголовки Википедии имеют вид: "== Heading =="

    if title.strip("=" + " ") in sections_to_ignore:
        # Если заголовок секции в списке для игнора, то пропускаем его
        return []

    # Объединим заголовки и подзаголовки, чтобы сохранить контекст для chatGPT
    titles = parent_titles + [title]

    # Преобразуем wikicode секции в строку
    full_text = str(section)

    # Выделяем текст секции без заголовка
    section_text = full_text.split(title)[1]
    if len(headings) == 1:
        # Если один заголовок, то формируем результирующий список
        return [(titles, section_text)]
    else:
        first_subtitle = headings[1]
        section_text = section_text.split(first_subtitle)[0]
        # Формируем результирующий список из текста до первого подзаголовка
        results = [(titles, section_text)]
        for subsection in section.get_sections(levels=[len(titles) + 1]):
            results.extend(
                # Вызываем функцию получения вложенных секций для заданной секции
                all_subsections_from_section(subsection, titles, sections_to_ignore)
                )  # Объединяем результирующие списки данной функции и вызываемой
        return results

# Функция возвращает список всех секций страницы, за исключением тех, которые отбрасываем
def all_subsections_from_title(
    title: str, # Заголовок статьи Википедии, которую парсим
    sections_to_ignore: set[str] = SECTIONS_TO_IGNORE, # Секции, которые игнорируем
    site_name: str = WIKI_SITE, # Ссылка на сайт википедии
) -> list[tuple[list[str], str]]:
    """
    Из заголовка страницы Википедии возвращает список всех вложенных секций.
    Каждый подраздел представляет собой кортеж, где:
      - первый элемент представляет собой список родительских секций, начиная с заголовка страницы
      - второй элемент представляет собой текст секции
    """

    # Инициализация объекта MediaWiki
    # WIKI_SITE ссылается на англоязычную часть Википедии
    site = mwclient.Site(site_name)

    # Запрашиваем страницу по заголовку
    page = site.pages[title]

    # Получаем текстовое представление страницы
    text = page.text()

    # Удобный парсер для MediaWiki
    parsed_text = mwparserfromhell.parse(text)
    # Извлекаем заголовки
    headings = [str(h) for h in parsed_text.filter_headings()]
    if headings: # Если заголовки найдены
        # В качестве резюме берем текст до первого заголовка
        summary_text = str(parsed_text).split(headings[0])[0]
    else:
        # Если нет заголовков, то весь текст считаем резюме
        summary_text = str(parsed_text)
    results = [([title], summary_text)] # Добавляем резюме в результирующий список
    for subsection in parsed_text.get_sections(levels=[2]): # Извлекаем секции 2-го уровня
        results.extend(
            # Вызываем функцию получения вложенных секций для заданной секции
            all_subsections_from_section(subsection, [title], sections_to_ignore)
        ) # Объединяем результирующие списки данной функции и вызываемой
    return results

# Разбивка статей на секции
# придется немного подождать, так как на парсинг 100 статей требуется около минуты
wikipedia_sections = []
for title in titles:
    wikipedia_sections.extend(all_subsections_from_title(title))
print(f"Найдено {len(wikipedia_sections)} секций на {len(titles)} страницах")

# Очистка текста секции от ссылок <ref>xyz</ref>, начальных и конечных пробелов
def clean_section(section: tuple[list[str], str]) -> tuple[list[str], str]:
    titles, text = section
    # Удаляем ссылки
    text = re.sub(r"<ref.*?</ref>", "", text)
    # Удаляем пробелы вначале и конце
    text = text.strip()
    return (titles, text)

# Применим функцию очистки ко всем секциям с помощью генератора списков
wikipedia_sections = [clean_section(ws) for ws in wikipedia_sections]

# Отфильтруем короткие и пустые секции
def keep_section(section: tuple[list[str], str]) -> bool:
    """Возвращает значение True, если раздел должен быть сохранен, в противном случае значение False."""
    titles, text = section
    # Фильтруем по произвольной длине, можно выбрать и другое значение
    if len(text) < 16:
        return False
    else:
        return True


original_num_sections = len(wikipedia_sections)
wikipedia_sections = [ws for ws in wikipedia_sections if keep_section(ws)]
print(f"Отфильтровано {original_num_sections-len(wikipedia_sections)} секций, осталось {len(wikipedia_sections)} секций.")

for ws in wikipedia_sections[:5]:
    print(ws[0])
    display(ws[1][:50] + "...")
    print()

GPT_MODEL = "gpt-3.5-turbo"  # only matters insofar as it selects which tokenizer to use

# Функция подсчета токенов
def num_tokens(text: str, model: str = GPT_MODEL) -> int:
    """Возвращает число токенов в строке."""
    encoding = tiktoken.encoding_for_model(model)
    return len(encoding.encode(text))

# Функция разделения строк
def halved_by_delimiter(string: str, delimiter: str = "\n") -> list[str, str]:
    """Разделяет строку надвое с помощью разделителя (delimiter), пытаясь сбалансировать токены с каждой стороны."""

    # Делим строку на части по разделителю, по умолчанию \n - перенос строки
    chunks = string.split(delimiter)
    if len(chunks) == 1:
        return [string, ""]  # разделитель не найден
    elif len(chunks) == 2:
        return chunks  # нет необходимости искать промежуточную точку
    else:
        # Считаем токены
        total_tokens = num_tokens(string)
        halfway = total_tokens // 2
        # Предварительное разделение по середине числа токенов
        best_diff = halfway
        # В цикле ищем какой из разделителей, будет ближе всего к best_diff
        for i, chunk in enumerate(chunks):
            left = delimiter.join(chunks[: i + 1])
            left_tokens = num_tokens(left)
            diff = abs(halfway - left_tokens)
            if diff >= best_diff:
                break
            else:
                best_diff = diff
        left = delimiter.join(chunks[:i])
        right = delimiter.join(chunks[i:])
        # Возвращаем левую и правую часть оптимально разделенной строки
        return [left, right]


# Функция обрезает строку до максимально разрешенного числа токенов
def truncated_string(
    string: str, # строка
    model: str, # модель
    max_tokens: int, # максимальное число разрешенных токенов
    print_warning: bool = True, # флаг вывода предупреждения
) -> str:
    """Обрезка строки до максимально разрешенного числа токенов."""
    encoding = tiktoken.encoding_for_model(model)
    encoded_string = encoding.encode(string)
    # Обрезаем строку и декодируем обратно
    truncated_string = encoding.decode(encoded_string[:max_tokens])
    if print_warning and len(encoded_string) > max_tokens:
        print(f"Предупреждение: Строка обрезана с {len(encoded_string)} токенов до {max_tokens} токенов.")
    # Усеченная строка
    return truncated_string

# Функция делит секции статьи на части по максимальному числу токенов
def split_strings_from_subsection(
    subsection: tuple[list[str], str], # секции
    max_tokens: int = 1000, # максимальное число токенов
    model: str = GPT_MODEL, # модель
    max_recursion: int = 5, # максимальное число рекурсий
) -> list[str]:
    """
    Разделяет секции на список из частей секций, в каждой части не более max_tokens.
    Каждая часть представляет собой кортеж родительских заголовков [H1, H2, ...] и текста (str).
    """
    titles, text = subsection
    string = "\n\n".join(titles + [text])
    num_tokens_in_string = num_tokens(string)
    # Если длина соответствует допустимой, то вернет строку
    if num_tokens_in_string <= max_tokens:
        return [string]
    # если в результате рекурсия не удалось разделить строку, то просто усечем ее по числу токенов
    elif max_recursion == 0:
        return [truncated_string(string, model=model, max_tokens=max_tokens)]
    # иначе разделим пополам и выполним рекурсию
    else:
        titles, text = subsection
        for delimiter in ["\n\n", "\n", ". "]: # Пробуем использовать разделители от большего к меньшему (разрыв, абзац, точка)
            left, right = halved_by_delimiter(text, delimiter=delimiter)
            if left == "" or right == "":
                # если какая-либо половина пуста, повторяем попытку с более простым разделителем
                continue
            else:
                # применим рекурсию на каждой половине
                results = []
                for half in [left, right]:
                    half_subsection = (titles, half)
                    half_strings = split_strings_from_subsection(
                        half_subsection,
                        max_tokens=max_tokens,
                        model=model,
                        max_recursion=max_recursion - 1, # уменьшаем максимальное число рекурсий
                    )
                    results.extend(half_strings)
                return results
    # иначе никакого разделения найдено не было, поэтому просто обрезаем строку (должно быть очень редко)
    return [truncated_string(string, model=model, max_tokens=max_tokens)]

# Делим секции на части
MAX_TOKENS = 1600
wikipedia_strings = []
for section in wikipedia_sections:
    wikipedia_strings.extend(split_strings_from_subsection(section, max_tokens=MAX_TOKENS))

print(f"{len(wikipedia_sections)} секций Википедии поделены на {len(wikipedia_strings)} строк.")

# Напечатаем пример строки
print(wikipedia_strings[1])

from openai import OpenAI
import os
import getpass

EMBEDDING_MODEL = "text-embedding-ada-002"  # Модель токенизации от OpenAI

os.environ["OPENAI_API_KEY"] = getpass.getpass("Введите OpenAI API Key:")
client = OpenAI(api_key = os.environ.get("OPENAI_API_KEY"))

# Функция отправки chatGPT строки для ее токенизации (вычисления эмбедингов)
def get_embedding(text, model="text-embedding-ada-002"):

   return client.embeddings.create(input = [text], model=model).data[0].embedding

df = pd.DataFrame({"text": wikipedia_strings[:10]})

df['embedding'] = df.text.apply(lambda x: get_embedding(x, model='text-embedding-ada-002'))

SAVE_PATH = "./Automotive_industry"

# Сохранение результата
df.to_csv(SAVE_PATH, index=False)

df.head()

"""# Этап 2: Создание телеграмм бота, использующего базу знаний



---

* Установка необходимых библиотек
"""

!pip install openai
!pip install --upgrade aiogram --pre
!pip install nest_asyncio

"""* Импорт модулей и настройка асинхронного цикла"""

import nest_asyncio
nest_asyncio.apply()

import asyncio
from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import Command
import getpass
import pandas as pd
import numpy as np
import openai
import ast

"""* Загрузка базы знаний"""

SAVE_PATH = "./Automotive_industry"
df = pd.read_csv(SAVE_PATH)

"""* Функция получения эмбеддингов"""

async def get_embedding(text, model="text-embedding-ada-002"):
    text = text.replace("\n", " ")
    response = await openai.Embedding.acreate(
        input=text,
        model=model
    )
    embedding = response['data'][0]['embedding']
    return embedding

if 'embedding' not in df.columns or df['embedding'].isnull().any():
    print("Эмбеддинги не найдены или некорректны. Пересчитываем эмбеддинги...")

    async def compute_embeddings():
        embeddings = []
        for text in df['text']:
            embedding = await get_embedding(text)
            embeddings.append(embedding)
        df['embedding'] = embeddings
        # Сохранение базы знаний с новыми эмбеддингами
        df.to_csv(SAVE_PATH, index=False)

    # Запускаем асинхронную функцию
    await compute_embeddings()
else:
    # Преобразуем строки в списки чисел
    df['embedding'] = df['embedding'].apply(ast.literal_eval)

"""* Инициализация бота и диспетчера"""

# Установка OpenAI API ключа
openai.api_key = getpass.getpass("Введите ваш OpenAI API Key:")

# Инициализация бота и диспетчера
bot_token = getpass.getpass("Введите токен вашего бота:")
bot = Bot(token=bot_token)
dp = Dispatcher()
router = Router()

"""* Обработчики команд /start и /help"""

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    welcome_text = (
        "Привет! Я бот, который может отвечать на вопросы по теме 'Автомобильная индустрия'.\n"
        "Введите команду /help для получения дополнительной информации."
    )
    await message.answer(welcome_text)

@router.message(Command("help"))
async def cmd_help(message: types.Message):
    knowledge_base_info = (
        "📚 *Информация о базе знаний:*\n"
        f"- Тематика: *Automotive Industry*\n"
        f"- Количество записей: *{len(df)}*\n\n"
        "💡 *Пример вопроса:* 'What is the history of the automotive industry?'\n\n"
        "Задайте мне вопрос по этой теме, и я постараюсь помочь!"
    )
    await message.answer(knowledge_base_info, parse_mode="Markdown")

"""* Функция для поиска ответов"""

def search_knowledge_base(user_embedding, df, n=5):
    embeddings = np.array(df['embedding'].tolist())
    user_embedding = np.array(user_embedding)
    # Нормализация эмбеддингов
    embeddings_norm = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
    user_embedding_norm = user_embedding / np.linalg.norm(user_embedding)
    # Вычисление косинусного сходства
    similarities = np.dot(embeddings_norm, user_embedding_norm)
    df['similarity'] = similarities
    top_n = df.nlargest(n, 'similarity')
    return top_n

"""* Функция для генерации ответа"""

async def generate_answer(question, context):
    prompt = (
        f"Вопрос: {question}\n\n"
        f"Контекст:\n{context}\n\n"
        "Пожалуйста, предоставьте подробный и точный ответ на вопрос, используя предоставленный контекст."
    )
    response = await openai.ChatCompletion.acreate(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=500,
        n=1,
    )
    answer = response['choices'][0]['message']['content'].strip()
    return answer

"""* Обработка пользовательских запросов"""

@router.message()
async def handle_user_message(message: types.Message):
    user_question = message.text

    user_embedding = await get_embedding(user_question)

    top_n = search_knowledge_base(user_embedding, df, n=5)

    context = "\n\n".join(top_n['text'].tolist())

    max_context_length = 3000
    context = context[:max_context_length]

    answer = await generate_answer(user_question, context)

    await message.answer(answer)

"""* Регистрация роутера"""

dp.include_router(router)

"""* Запуск бота"""

async def main():
    await dp.start_polling(bot)

await main()
