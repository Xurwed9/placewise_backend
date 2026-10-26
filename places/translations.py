import re
from pathlib import Path


CATEGORY_SEED = [
    {
        "key": "restaurants",
        "slug": "restaurants",
        "name": {
            "ru": "Рестораны",
            "tg": "Тарабхонаҳо",
            "en": "Restaurants",
        },
        "icon": "utensils",
        "sort_order": 1,
    },
    {
        "key": "pharmacies",
        "slug": "pharmacies",
        "name": {
            "ru": "Аптеки",
            "tg": "Дорухонаҳо",
            "en": "Pharmacies",
        },
        "icon": "pill",
        "sort_order": 2,
    },
    {
        "key": "supermarkets",
        "slug": "supermarkets",
        "name": {
            "ru": "Супермаркеты",
            "tg": "Супермаркетҳо",
            "en": "Supermarkets",
        },
        "icon": "shopping-cart",
        "sort_order": 3,
    },
    {
        "key": "flowers",
        "slug": "flowers",
        "name": {
            "ru": "Цветы",
            "tg": "Гулҳо",
            "en": "Flowers",
        },
        "icon": "flower",
        "sort_order": 4,
    },
    {
        "key": "bakery",
        "slug": "bakery",
        "name": {
            "ru": "Выпечка",
            "tg": "Нонвойӣ",
            "en": "Bakery",
        },
        "icon": "bread",
        "sort_order": 5,
    },
    {
        "key": "electronics",
        "slug": "electronics",
        "name": {
            "ru": "Электроника",
            "tg": "Электроника",
            "en": "Electronics",
        },
        "icon": "smartphone",
        "sort_order": 6,
    },
    {
        "key": "beauty",
        "slug": "beauty",
        "name": {
            "ru": "Красота",
            "tg": "Зебоӣ",
            "en": "Beauty",
        },
        "icon": "sparkles",
        "sort_order": 7,
    },
    {
        "key": "powerbanks",
        "slug": "powerbanks",
        "name": {
            "ru": "Павербанки",
            "tg": "Павербанкҳо",
            "en": "Power banks",
        },
        "icon": "battery-charging",
        "sort_order": 8,
    },
    {
        "key": "home_care",
        "slug": "home-care",
        "name": {
            "ru": "Дом и уход",
            "tg": "Хона ва нигоҳубин",
            "en": "Home & care",
        },
        "icon": "home",
        "sort_order": 9,
    },
]


CATEGORY_FILENAME_ALIASES = {
    "restaurants": "restaurants",
    "ресторан": "restaurants",
    "рестораны": "restaurants",
    "pharmacies": "pharmacies",
    "аптека": "pharmacies",
    "аптеки": "pharmacies",
    "supermarkets": "supermarkets",
    "супермаркет": "supermarkets",
    "супермаркеты": "supermarkets",
    "flowers": "flowers",
    "цветок": "flowers",
    "цветы": "flowers",
    "bakery": "bakery",
    "выпечка": "bakery",
    "электроника": "electronics",
    "electronics": "electronics",
    "beauty": "beauty",
    "красота": "beauty",
    "powerbanks": "powerbanks",
    "павербанк": "powerbanks",
    "павербанки": "powerbanks",
    "home_care": "home_care",
    "home-care": "home_care",
    "дом и уход": "home_care",
    "дом": "home_care",
}


SUBCATEGORY_TRANSLATIONS = {
    "быстрое питание": {
        "ru": "Быстрое питание",
        "tg": "Хӯроки тез",
        "en": "Fast food",
    },
    "фастфуд": {
        "ru": "Фастфуд",
        "tg": "Хӯроки тез",
        "en": "Fast food",
    },
    "ресторан": {
        "ru": "Ресторан",
        "tg": "Тарабхона",
        "en": "Restaurant",
    },
    "кафе": {
        "ru": "Кафе",
        "tg": "Қаҳвахона",
        "en": "Cafe",
    },
    "кофейня": {
        "ru": "Кофейня",
        "tg": "Қаҳвахона",
        "en": "Coffee shop",
    },
    "пиццерия": {
        "ru": "Пиццерия",
        "tg": "Пиццерия",
        "en": "Pizzeria",
    },
    "суши": {
        "ru": "Суши",
        "tg": "Суши",
        "en": "Sushi",
    },
    "бургеры": {
        "ru": "Бургеры",
        "tg": "Бургерҳо",
        "en": "Burgers",
    },
    "шаурма": {
        "ru": "Шаурма",
        "tg": "Шаурма",
        "en": "Shawarma",
    },
    "национальная кухня": {
        "ru": "Национальная кухня",
        "tg": "Таомҳои миллӣ",
        "en": "National cuisine",
    },
    "аптека": {
        "ru": "Аптека",
        "tg": "Дорухона",
        "en": "Pharmacy",
    },
    "супермаркет": {
        "ru": "Супермаркет",
        "tg": "Супермаркет",
        "en": "Supermarket",
    },
    "продуктовый магазин": {
        "ru": "Продуктовый магазин",
        "tg": "Магазини маҳсулот",
        "en": "Grocery store",
    },
    "цветы": {
        "ru": "Цветы",
        "tg": "Гулҳо",
        "en": "Flowers",
    },
    "цветочный магазин": {
        "ru": "Цветочный магазин",
        "tg": "Дӯкони гул",
        "en": "Flower shop",
    },
    "выпечка": {
        "ru": "Выпечка",
        "tg": "Нонвойӣ",
        "en": "Bakery",
    },
    "хлеб": {
        "ru": "Хлеб",
        "tg": "Нон",
        "en": "Bread",
    },
    "кондитерская": {
        "ru": "Кондитерская",
        "tg": "Қаннодӣ",
        "en": "Confectionery",
    },
    "электроника": {
        "ru": "Электроника",
        "tg": "Электроника",
        "en": "Electronics",
    },
    "бытовая техника": {
        "ru": "Бытовая техника",
        "tg": "Техникаи рӯзгор",
        "en": "Home appliances",
    },
    "мобильные телефоны": {
        "ru": "Мобильные телефоны",
        "tg": "Телефонҳои мобилӣ",
        "en": "Mobile phones",
    },
    "аксессуары": {
        "ru": "Аксессуары",
        "tg": "Лавозимот",
        "en": "Accessories",
    },
    "красота": {
        "ru": "Красота",
        "tg": "Зебоӣ",
        "en": "Beauty",
    },
    "косметика": {
        "ru": "Косметика",
        "tg": "Косметика",
        "en": "Cosmetics",
    },
    "парфюмерия": {
        "ru": "Парфюмерия",
        "tg": "Атторӣ",
        "en": "Perfumery",
    },
    "салон красоты": {
        "ru": "Салон красоты",
        "tg": "Салонҳои зебоӣ",
        "en": "Beauty salon",
    },
    "парикмахерская": {
        "ru": "Парикмахерская",
        "tg": "Ороишгоҳ",
        "en": "Hair salon",
    },
    "ногтевая студия": {
        "ru": "Ногтевая студия",
        "tg": "Студияи нохун",
        "en": "Nail studio",
    },
    "павербанк": {
        "ru": "Павербанк",
        "tg": "Павербанк",
        "en": "Power bank",
    },
    "зарядные устройства": {
        "ru": "Зарядные устройства",
        "tg": "Дастгоҳҳои пуркунанда",
        "en": "Chargers",
    },
    "дом и уход": {
        "ru": "Дом и уход",
        "tg": "Хона ва нигоҳубин",
        "en": "Home & care",
    },
    "хозяйственные товары": {
        "ru": "Хозяйственные товары",
        "tg": "Молҳои хоҷагӣ",
        "en": "Household goods",
    },
    "чистящие средства": {
        "ru": "Чистящие средства",
        "tg": "Воситаҳои тозакунӣ",
        "en": "Cleaning products",
    },
    "бытовая химия": {
        "ru": "Бытовая химия",
        "tg": "Химияи рӯзгор",
        "en": "Household chemicals",
    },
    "мыло": {
        "ru": "Мыло",
        "tg": "Собун",
        "en": "Soap",
    },
    "шампунь": {
        "ru": "Шампунь",
        "tg": "Шампун",
        "en": "Shampoo",
    },
    "доставка": {
        "ru": "Доставка",
        "tg": "Расонидан",
        "en": "Delivery",
    },
    "банк": {
        "ru": "Банк",
        "tg": "Бонк",
        "en": "Bank",
    },
    "обмен валют": {
        "ru": "Обмен валют",
        "tg": "Мубодилаи асъор",
        "en": "Currency exchange",
    },
    "банкомат": {
        "ru": "Банкомат",
        "tg": "Банкомат",
        "en": "ATM",
    },
    "гостиница": {
        "ru": "Гостиница",
        "tg": "Меҳмонхона",
        "en": "Hotel",
    },
    "отель": {
        "ru": "Отель",
        "tg": "Ҳотел",
        "en": "Hotel",
    },
    "фитнес": {
        "ru": "Фитнес",
        "tg": "Фитнес",
        "en": "Fitness",
    },
    "спортзал": {
        "ru": "Спортзал",
        "tg": "Толори варзиш",
        "en": "Gym",
    },
    "стоматология": {
        "ru": "Стоматология",
        "tg": "Стоматология",
        "en": "Dentistry",
    },
    "клиника": {
        "ru": "Клиника",
        "tg": "Клиника",
        "en": "Clinic",
    },
    "больница": {
        "ru": "Больница",
        "tg": "Беморхона",
        "en": "Hospital",
    },
    "школа": {
        "ru": "Школа",
        "tg": "Мактаб",
        "en": "School",
    },
    "детский сад": {
        "ru": "Детский сад",
        "tg": "Кӯдакистон",
        "en": "Kindergarten",
    },
    "автосервис": {
        "ru": "Автосервис",
        "tg": "Хидматрасонии мошин",
        "en": "Car service",
    },
    "автомойка": {
        "ru": "Автомойка",
        "tg": "Мошиншӯӣ",
        "en": "Car wash",
    },
    "заправка": {
        "ru": "Заправка",
        "tg": "Пуркунандаи сӯзишворӣ",
        "en": "Gas station",
    },
    "магазин": {
        "ru": "Магазин",
        "tg": "Дӯкон",
        "en": "Store",
    },
    "одежда": {
        "ru": "Одежда",
        "tg": "Либос",
        "en": "Clothing",
    },
    "обувь": {
        "ru": "Обувь",
        "tg": "Пойафзол",
        "en": "Shoes",
    },
    "ювелирный магазин": {
        "ru": "Ювелирный магазин",
        "tg": "Дӯкони заргарӣ",
        "en": "Jewelry store",
    },
    "книжный магазин": {
        "ru": "Книжный магазин",
        "tg": "Дӯкони китоб",
        "en": "Bookstore",
    },
    "зоомагазин": {
        "ru": "Зоомагазин",
        "tg": "Дӯкони ҳайвонот",
        "en": "Pet shop",
    },
    "оптика": {
        "ru": "Оптика",
        "tg": "Оптика",
        "en": "Optics",
    },
    "фотосалон": {
        "ru": "Фотосалон",
        "tg": "Фотосалон",
        "en": "Photo studio",
    },
    "ремонт обуви": {
        "ru": "Ремонт обуви",
        "tg": "Таъмири пойафзол",
        "en": "Shoe repair",
    },
    "химчистка": {
        "ru": "Химчистка",
        "tg": "Химияи тозакунӣ",
        "en": "Dry cleaning",
    },
    "прачечная": {
        "ru": "Прачечная",
        "tg": "Ҷомашӯйхона",
        "en": "Laundry",
    },
    "ателье": {
        "ru": "Ателье",
        "tg": "Ателье",
        "en": "Tailor",
    },
    "мебель": {
        "ru": "Мебель",
        "tg": "Мебел",
        "en": "Furniture",
    },
    "строительные материалы": {
        "ru": "Строительные материалы",
        "tg": "Маводи сохтмон",
        "en": "Building materials",
    },
}


SUBCATEGORY_ALIASES = {
    "cafe": "кафе",
    "restaurant": "ресторан",
    "pizza": "пиццерия",
    "pizzeria": "пиццерия",
    "fast food": "быстрое питание",
    "sushi": "суши",
    "burger": "бургеры",
    "burgers": "бургеры",
    "shawarma": "шаурма",
    "national cuisine": "национальная кухня",
    "pharmacy": "аптека",
    "supermarket": "супермаркет",
    "grocery store": "продуктовый магазин",
    "flowers": "цветы",
    "flower shop": "цветочный магазин",
    "bakery": "выпечка",
    "bread": "хлеб",
    "confectionery": "кондитерская",
    "electronics": "электроника",
    "home appliances": "бытовая техника",
    "mobile phones": "мобильные телефоны",
    "accessories": "аксессуары",
    "beauty": "красота",
    "cosmetics": "косметика",
    "perfumery": "парфюмерия",
    "beauty salon": "салон красоты",
    "hair salon": "парикмахерская",
    "nail studio": "ногтевая студия",
    "power bank": "павербанк",
    "chargers": "зарядные устройства",
    "home & care": "дом и уход",
    "household goods": "хозяйственные товары",
    "cleaning products": "чистящие средства",
    "household chemicals": "бытовая химия",
    "soap": "мыло",
    "shampoo": "шампунь",
    "delivery": "доставка",
    "bank": "банк",
    "currency exchange": "обмен валют",
    "atm": "банкомат",
    "hotel": "гостиница",
    "fitness": "фитнес",
    "gym": "спортзал",
    "dentistry": "стоматология",
    "clinic": "клиника",
    "hospital": "больница",
    "school": "школа",
    "kindergarten": "детский сад",
    "car service": "автосервис",
    "car wash": "автомойка",
    "gas station": "заправка",
    "store": "магазин",
    "clothing": "одежда",
    "shoes": "обувь",
    "jewelry store": "ювелирный магазин",
    "bookstore": "книжный магазин",
    "pet shop": "зоомагазин",
    "optics": "оптика",
    "photo studio": "фотосалон",
    "shoe repair": "ремонт обуви",
    "dry cleaning": "химчистка",
    "laundry": "прачечная",
    "tailor": "ателье",
    "furniture": "мебель",
    "building materials": "строительные материалы",
}
SUBCATEGORY_ALIASES["powerbanks"] = "павербанк"

for _alias, _canonical in SUBCATEGORY_ALIASES.items():
    if _canonical in SUBCATEGORY_TRANSLATIONS:
        SUBCATEGORY_TRANSLATIONS.setdefault(
            _alias,
            SUBCATEGORY_TRANSLATIONS[_canonical],
        )


def normalize_label(value):
    if not isinstance(value, str):
        return ""
    value = value.casefold().strip().replace("ё", "е")
    value = re.sub(r"[_\-–—]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" .,:;!?()[]{}")


def filename_label(filename):
    stem = Path(filename).stem.casefold().replace("ё", "е")
    stem = re.sub(r"^\s*\d+\s*[_\-.)]*\s*", "", stem)
    stem = re.sub(r"[_\-–—]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem)
    return stem.strip(" .,:;!?()[]{}")


def resolve_category_key_from_filename(filename):
    label = filename_label(filename)
    if not label:
        return None
    return CATEGORY_FILENAME_ALIASES.get(label)


def translate_subcategory(value):
    original = (value or "").strip()
    if not original:
        return {}

    label = normalize_label(original)
    translation = SUBCATEGORY_TRANSLATIONS.get(label)

    if translation is None:
        for key, candidate in SUBCATEGORY_TRANSLATIONS.items():
            if key in label or (len(label) >= 5 and label in key):
                translation = candidate
                break

    if translation is None:
        return {"ru": original}

    return {
        "ru": translation["ru"],
        "tg": translation["tg"],
        "en": translation["en"],
    }
