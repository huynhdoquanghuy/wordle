import json
import re
import sys
import os
import random
import shutil

from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError

# DAILY WORDLE

BASE_DIR = Path(__file__).resolve().parent

MAX_GUESSES = 6
WORD_LENGTH = 5

SAVE_FILE = BASE_DIR / "save.json"

CACHE_DIR = BASE_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)

REWARD_DIR = CACHE_DIR / "rewards"
REWARD_DIR.mkdir(exist_ok=True)

COLLECTION_FILE = CACHE_DIR / "collection.json"

GACHA_COST = 100
GACHA_10_COST = 900
GACHA_100_COST = 8800
SELL_PRICES = {
    "R": 25,
    "SR": 100,
    "SSR": 1000,
    "UR": 5000,
}


# COLORS

RESET = "\033[0m"

BLACK = "\033[30m"
WHITE = "\033[97m"

GREEN_BG = "\033[42;30m"
YELLOW_BG = "\033[43;30m"
GRAY_BG = "\033[100;37m"

CYAN = "\033[96m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"

DIM = "\033[90m"
BOLD = "\033[1m"


RARITY_ASCII = {
    "R": "R",
    "SR": "SR",
    "SSR": "SSR",
    "UR": "UR",
}


# RARITIES

RARITIES = {
    "R": {
        "color": "#A8A8A8",
        "weight": 70.0,
    },

    "SR": {
        "color": "#55B7FF",
        "weight": 22.0,
    },

    "SSR": {
        "color": "#C86CFF",
        "weight": 7.0,
    },

    "UR": {
        "color": "#FFD84D",
        "weight": 1.0,
    },
}


# UI HELPERS

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def enable_ansi():
    if sys.platform == "win32":
        try:
            os.system("")
        except Exception:
            pass


def pause(message="Press ENTER to continue..."):
    try:
        input(f"\n{DIM}{message}{RESET}")
    except EOFError:
        pass


def money(save):
    return int(save.get("money", 0))


def add_money(save, amount):
    save["money"] = max(0, money(save) + amount)
    save_game(save)


def rarity_level(rarity):
    return {
        "R": 1,
        "SR": 2,
        "SSR": 3,
        "UR": 4,
    }.get(rarity, 1)


def level_rarity(level):
    return {
        1: "R",
        2: "SR",
        3: "SSR",
        4: "UR",
    }.get(min(4, max(1, level)), "R")


def choose_gacha_rarity():
    rates = {
        "R": 80.0,
        "SR": 15.0,
        "SSR": 4.2,
        "UR": 0.8,
    }

    roll = random.uniform(0, 100)
    current = 0

    for rarity, rate in rates.items():
        current += rate

        if roll <= current:
            return rarity

    return "R"


def rarity_color_console(rarity):
    return {
        "R": DIM,
        "SR": CYAN,
        "SSR": MAGENTA,
        "UR": YELLOW,
    }.get(rarity, WHITE)


def rarity_text(rarity):
    c = rarity_color_console(rarity)
    return f"{c}{BOLD}{rarity}{RESET}"


# PANELS

def panel(title, lines=None, width=66):
    print()
    print(f"{CYAN}╭{'─' * (width - 2)}╮{RESET}")

    title_text = f"  {title}"
    print(
        f"{CYAN}│{RESET}"
        f"{BOLD}{title_text:<{width - 2}}{RESET}"
        f"{CYAN}│{RESET}"
    )

    print(f"{CYAN}├{'─' * (width - 2)}┤{RESET}")

    if lines:
        for line in lines:
            visible = str(line)

            if len(visible) > width - 4:
                visible = visible[:width - 7] + "..."

            print(
                f"{CYAN}│{RESET}"
                f"  {visible:<{width - 4}}"
                f"{CYAN}│{RESET}"
            )

    print(f"{CYAN}╰{'─' * (width - 2)}╯{RESET}")


def section_title(title):
    print()
    print(f"{BOLD}{CYAN}◆ {title}{RESET}")


def print_money(save):
    print(
        f"{YELLOW}◆{RESET} "
        f"{BOLD}{money(save):,}{RESET} coins"
    )


# VIETNAM TIME

def vietnam_now():
    return (
        datetime.now(timezone.utc)
        + timedelta(hours=7)
    )


def today_string():
    return vietnam_now().strftime("%Y-%m-%d")


# HTTP

REWARD_API = "https://nekos.best/api/v2"

REWARD_CONTACT = "https://github.com/huynhdoquanghuy/wordle"

REWARD_USER_AGENT = (
    f"DailyWordle/1.0 ({REWARD_CONTACT})"
)


def make_headers(accept="*/*"):
    return {
        "User-Agent": REWARD_USER_AGENT,
        "Accept": accept,
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
    }


def download_bytes(url, timeout=30, headers=None):
    if headers is None:
        headers = make_headers()

    req = Request(
        url,
        headers=headers
    )

    with urlopen(req, timeout=timeout) as response:
        return response.read()


def download_text(url, timeout=15):
    data = download_bytes(
        url,
        timeout=timeout,
        headers=make_headers()
    )

    return data.decode(
        "utf-8",
        errors="replace"
    )


# ============================================================
# SAVE
# ============================================================

DEFAULT_SAVE = {
    "last_played": None,
    "last_result": None,
    "last_guesses": 0,

    "streak": 0,
    "max_streak": 0,

    "wins": 0,
    "losses": 0,
    "total_games": 0,

    "last_win_date": None,
    "last_money_earned": 0,

    "money": 1000,
}


def load_save():
    if not SAVE_FILE.exists():
        return DEFAULT_SAVE.copy()

    try:
        with open(
            SAVE_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            data = json.load(f)

        if not isinstance(data, dict):
            data = {}

        for key, value in DEFAULT_SAVE.items():
            data.setdefault(key, value)

        return data

    except Exception:
        print(
            f"{RED}save.json bị lỗi, tạo save mới.{RESET}"
        )

        return DEFAULT_SAVE.copy()


def save_game(data):
    temp = SAVE_FILE.with_suffix(".tmp")

    with open(
        temp,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            data,
            f,
            indent=4,
            ensure_ascii=False
        )

    temp.replace(SAVE_FILE)


# ============================================================
# COLLECTION
# ============================================================

def load_collection():
    if not COLLECTION_FILE.exists():
        return {"items": []}

    try:
        with open(
            COLLECTION_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return {"items": []}

        if not isinstance(data.get("items"), list):
            data["items"] = []

        return data

    except Exception:
        print(
            f"{RED}collection.json bị lỗi.{RESET}"
        )

        return {"items": []}


def save_collection(data):
    temp = COLLECTION_FILE.with_suffix(".tmp")

    with open(
        temp,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            data,
            f,
            indent=4,
            ensure_ascii=False
        )

    temp.replace(COLLECTION_FILE)


def collection_counts():
    collection = load_collection()

    counts = {
        "R": 0,
        "SR": 0,
        "SSR": 0,
        "UR": 0,
    }

    for item in collection.get("items", []):
        rarity = item.get("rarity", "R")

        if rarity in counts:
            counts[rarity] += 1

    return counts


def next_collection_id():
    collection = load_collection()

    highest = 0

    for item in collection.get("items", []):
        try:
            highest = max(
                highest,
                int(item.get("id", 0))
            )
        except Exception:
            pass

    return highest + 1


def collected_urls():
    collection = load_collection()

    return {
        item.get("url")
        for item in collection.get("items", [])
        if item.get("url")
    }


# ============================================================
# WORDLE SOURCE
# ============================================================

WORDLE_META_URL = (
    "https://raw.githubusercontent.com/"
    "eithan/wordlelist/main/meta.json"
)

WORDLE_CURRENT_URL = (
    "https://raw.githubusercontent.com/"
    "eithan/wordlelist/main/current.txt"
)

WORDLE_WORDS_URL = (
    "https://raw.githubusercontent.com/"
    "eithan/wordlelist/main/solver-words.txt"
)


KNOWN_FALLBACKS = {
    "2026-10-07": "PROVE",
}


# ============================================================
# GET WORDLE
# ============================================================

def get_wordle_data():
    today = today_string()

    try:
        meta_text = download_text(
            WORDLE_META_URL
        )

        meta = json.loads(meta_text)

        puzzle_date = meta.get("wordle_date")

        current_text = download_text(
            WORDLE_CURRENT_URL
        )

        current_word = (
            current_text
            .strip()
            .upper()
        )

        if (
            puzzle_date == today
            and re.fullmatch(
                r"[A-Z]{5}",
                current_word
            )
        ):
            cache_answer(
                today,
                current_word
            )

            return (
                current_word,
                puzzle_date,
                "wordlelist"
            )

    except Exception as e:
        print(
            f"{DIM}"
            f"[Wordle source unavailable: {e}]"
            f"{RESET}"
        )

    if today in KNOWN_FALLBACKS:
        return (
            KNOWN_FALLBACKS[today],
            today,
            "verified fallback"
        )

    cache_file = CACHE_DIR / f"{today}.txt"

    if cache_file.exists():
        try:
            cached = (
                cache_file
                .read_text(
                    encoding="utf-8"
                )
                .strip()
                .upper()
            )

            if re.fullmatch(
                r"[A-Z]{5}",
                cached
            ):
                return (
                    cached,
                    today,
                    "local cache"
                )

        except Exception:
            pass

    return None, today, None


def cache_answer(date_string, answer):
    try:
        cache_file = (
            CACHE_DIR
            / f"{date_string}.txt"
        )

        cache_file.write_text(
            answer.upper(),
            encoding="utf-8"
        )

    except Exception:
        pass


# ============================================================
# VALID WORDS
# ============================================================

def get_valid_words(answer):
    cache_file = CACHE_DIR / "valid_words.txt"

    if cache_file.exists():
        try:
            text = cache_file.read_text(
                encoding="utf-8"
            )

            words = {
                x.strip().upper()
                for x in text.splitlines()
                if re.fullmatch(
                    r"[A-Z]{5}",
                    x.strip()
                )
            }

            if len(words) > 1000:
                words.add(answer)
                return words

        except Exception:
            pass

    try:
        text = download_text(
            WORDLE_WORDS_URL,
            timeout=20
        )

        words = set()

        for line in text.splitlines():
            line = line.strip().upper()

            if line.startswith("#"):
                continue

            if re.fullmatch(
                r"[A-Z]{5}",
                line
            ):
                words.add(line)

        if len(words) > 1000:
            cache_file.write_text(
                "\n".join(sorted(words)),
                encoding="utf-8"
            )

            words.add(answer)
            return words

    except Exception as e:
        print(
            f"{DIM}"
            f"[Could not download word list: {e}]"
            f"{RESET}"
        )

    return {
        answer,
        "CRANE",
        "SLATE",
        "STARE",
        "ARISE",
        "AUDIO",
        "ROATE",
        "ORATE",
        "RAISE",
        "HOUSE",
        "WORLD",
        "ABOUT",
        "THERE",
        "THEIR",
        "OTHER",
        "POINT",
        "RIGHT",
        "PLACE",
        "WATER",
        "LIGHT",
        "NIGHT",
        "HEART",
        "TRAIN",
        "WORDS",
        "GUESS",
        "SOLVE",
        "PROVE",
    }


# ============================================================
# WORDLE EVALUATION
# ============================================================

def evaluate_guess(guess, answer):
    result = ["gray"] * WORD_LENGTH

    answer_chars = list(answer)
    guess_chars = list(guess)

    for i in range(WORD_LENGTH):
        if guess_chars[i] == answer_chars[i]:
            result[i] = "green"

            answer_chars[i] = None
            guess_chars[i] = None

    for i in range(WORD_LENGTH):
        if guess_chars[i] is None:
            continue

        letter = guess_chars[i]

        if letter in answer_chars:
            result[i] = "yellow"

            index = answer_chars.index(letter)
            answer_chars[index] = None

    return result


def tile(letter, state):
    if state == "green":
        return f"{GREEN_BG} {letter} {RESET}"

    if state == "yellow":
        return f"{YELLOW_BG} {letter} {RESET}"

    if state == "gray":
        return f"{GRAY_BG} {letter} {RESET}"

    return f"{DIM}[ {letter} ]{RESET}"


def draw_board(guesses, results):
    print()

    print(
        f"{BOLD}{CYAN}"
        "              W O R D L E"
        f"{RESET}"
    )

    print()

    for i in range(MAX_GUESSES):
        if i < len(guesses):
            guess = guesses[i]
            result = results[i]

            print(
                "              "
                + " ".join(
                    tile(
                        letter,
                        state
                    )
                    for letter, state in zip(
                        guess,
                        result
                    )
                )
            )

        else:
            print(
                "              "
                + " ".join(
                    tile("_", "empty")
                    for _ in range(WORD_LENGTH)
                )
            )

    print()


# ============================================================
# KEYBOARD
# ============================================================

def keyboard_state(guesses, results):
    states = {}

    priority = {
        "gray": 0,
        "yellow": 1,
        "green": 2,
    }

    for guess, result in zip(
        guesses,
        results
    ):
        for letter, state in zip(
            guess,
            result
        ):
            old = states.get(letter)

            if (
                old is None
                or priority[state] > priority[old]
            ):
                states[letter] = state

    rows = [
        "QWERTYUIOP",
        " ASDFGHJKL",
        "  ZXCVBNM",
    ]

    print(f"{DIM}Keyboard{RESET}")

    for row in rows:
        output = []

        for letter in row:
            if letter == " ":
                output.append(" ")
                continue

            state = states.get(letter)

            if state == "green":
                output.append(
                    f"{GREEN_BG} {letter} {RESET}"
                )

            elif state == "yellow":
                output.append(
                    f"{YELLOW_BG} {letter} {RESET}"
                )

            elif state == "gray":
                output.append(
                    f"{GRAY_BG} {letter} {RESET}"
                )

            else:
                output.append(
                    f" {letter} "
                )

        print(" ".join(output))

    print()


# ============================================================
# DAILY HEADER
# ============================================================

def print_game_header(
    puzzle_date,
    source,
    save
):
    clear_screen()

    counts = collection_counts()
    total = sum(counts.values())

    print()
    print(
        f"{BOLD}{CYAN}"
        "╔══════════════════════════════════════════════════════════════╗"
        f"{RESET}"
    )

    print(
        f"{BOLD}{CYAN}"
        "║                     DAILY WORDLE                            ║"
        f"{RESET}"
    )

    print(
        f"{BOLD}{CYAN}"
        "╚══════════════════════════════════════════════════════════════╝"
        f"{RESET}"
    )

    print()

    print(
        f"  {DIM}DATE{RESET}       {puzzle_date}"
        f"        {DIM}SOURCE{RESET}   {source}"
    )

    print(
        f"  {DIM}STREAK{RESET}     "
        f"{YELLOW}{save.get('streak', 0)}{RESET}"
        f"          {DIM}BEST{RESET}     "
        f"{save.get('max_streak', 0)}"
    )

    print(
        f"  {DIM}COINS{RESET}      "
        f"{YELLOW}{money(save):,}{RESET}"
        f"        {DIM}COLLECTION{RESET} {total}"
    )

    print()


# ============================================================
# ALREADY PLAYED
# ============================================================

def already_played(save, today):
    if save.get("last_played") != today:
        return False

    clear_screen()

    result = save.get(
        "last_result",
        "unknown"
    )

    guesses = save.get(
        "last_guesses",
        0
    )

    panel(
        "TODAY'S WORDLE COMPLETE",
        [
            "Bạn đã hoàn thành Wordle hôm nay.",
            "",
            f"Result       : {result.upper()}",
            f"Guesses      : {guesses}/6",
            f"Current streak: {save.get('streak', 0)}",
            f"Coins        : {money(save):,}",
            "",
            "Quay lại vào ngày mai.",
        ]
    )

    return True


# ============================================================
# PLAY GAME
# ============================================================
def play_game(
    answer,
    puzzle_date,
    source,
    save
):
    # ========================================================
    # NORMALIZE ANSWER
    # ========================================================

    answer = str(answer).strip().upper()

    valid_words = get_valid_words(answer)

    guesses = []
    results = []

    while len(guesses) < MAX_GUESSES:

        print_game_header(
            puzzle_date,
            source,
            save
        )

        draw_board(
            guesses,
            results
        )

        keyboard_state(
            guesses,
            results
        )

        remaining = (
            MAX_GUESSES
            - len(guesses)
        )

        print(
            f"{DIM}"
            f"Attempts remaining: {remaining}"
            f"{RESET}"
        )

        print(
            f"{DIM}"
            "Nhập 5 chữ cái • EXIT để thoát"
            f"{RESET}"
        )

        print()

        raw = input(
            f"{CYAN}› {RESET}"
        ).strip().upper()

        # ====================================================
        # EXIT
        # ====================================================

        if raw == "EXIT":
            clear_screen()

            panel(
                "GAME CLOSED",
                [
                    "Today's attempt has NOT been used.",
                    "Bạn có thể quay lại chơi sau.",
                ]
            )

            return None

        # ====================================================
        # LENGTH
        # ====================================================

        if len(raw) != WORD_LENGTH:
            print(
                f"\n{RED}"
                "✕ Vui lòng nhập đúng 5 chữ."
                f"{RESET}"
            )

            pause()
            continue

        # ====================================================
        # ONLY LETTERS
        # ====================================================

        if not raw.isalpha():
            print(
                f"\n{RED}"
                "✕ Chỉ được nhập chữ cái."
                f"{RESET}"
            )

            pause()
            continue

        # ====================================================
        # VALID WORD
        # ====================================================

        if (
            raw not in valid_words
            and raw != answer
        ):
            print(
                f"\n{RED}"
                "✕ Từ này không có trong Wordle."
                f"{RESET}"
            )

            pause()
            continue

        # ====================================================
        # EVALUATE
        # ====================================================

        result = evaluate_guess(
            raw,
            answer
        )

        guesses.append(raw)
        results.append(result)

        # ====================================================
        # WIN
        # ====================================================

        if raw == answer:

            print_game_header(
                puzzle_date,
                source,
                save
            )

            draw_board(
                guesses,
                results
            )

            print(
                f"\n{GREEN}"
                f"{BOLD}"
                "✓ CORRECT!"
                f"{RESET}"
            )

            guesses_used = len(guesses)

            print(
                f"\n{DIM}"
                f"Solved in {guesses_used}/6 guesses."
                f"{RESET}"
            )

            money_earned = (
                100
                + (
                    MAX_GUESSES
                    - guesses_used
                ) * 50
            )

            print(
                f"\n{YELLOW}"
                f"💰 Wordle reward: +{money_earned} coins"
                f"{RESET}"
            )

            # ------------------------------------------------
            # SAVE IMMEDIATELY
            # ------------------------------------------------

            save["last_played"] = puzzle_date
            save["last_result"] = "win"
            save["last_guesses"] = guesses_used

            save_game(save)

            pause(
                "Press ENTER to continue..."
            )

            return {
                "result": "win",
                "guesses": guesses_used,
            }

        # ====================================================
        # NEXT ATTEMPT
        # ====================================================

        pause(
            "Press ENTER for next attempt..."
        )

    # ========================================================
    # LOSS
    # ========================================================

    clear_screen()

    print_game_header(
        puzzle_date,
        source,
        save
    )

    draw_board(
        guesses,
        results
    )

    panel(
        "GAME OVER",
        [
            f"The answer was: {answer}",
            "",
            "Today's puzzle is complete.",
        ]
    )

    # --------------------------------------------------------
    # SAVE IMMEDIATELY
    # --------------------------------------------------------

    save["last_played"] = puzzle_date
    save["last_result"] = "loss"
    save["last_guesses"] = MAX_GUESSES

    save_game(save)

    return {
        "result": "loss",
        "guesses": MAX_GUESSES,
    }
# ============================================================
# FINISH GAME
# ============================================================

def finish_game(save, today, result):
    save["last_played"] = today
    save["last_result"] = result["result"]
    save["last_guesses"] = result["guesses"]
    save["total_games"] += 1

    if result["result"] == "win":
        save["wins"] += 1

        previous_date = save.get(
            "last_win_date"
        )

        yesterday = (
            vietnam_now().date()
            - timedelta(days=1)
        ).strftime("%Y-%m-%d")

        if previous_date == yesterday:
            save["streak"] += 1
        else:
            save["streak"] = 1

        save["last_win_date"] = today

        save["max_streak"] = max(
            save["max_streak"],
            save["streak"]
        )

        money_earned = (
            100
            + (
                MAX_GUESSES
                - result["guesses"]
            ) * 50
        )

    else:
        save["losses"] += 1
        save["streak"] = 0

        money_earned = 25

    save["money"] = (
        save.get("money", 0)
        + money_earned
    )

    save["last_money_earned"] = money_earned

    save_game(save)


# ============================================================
# REWARD API
# ============================================================

def get_random_reward():
    old_urls = collected_urls()

    url = (
        f"{REWARD_API}/waifu?"
        f"{urlencode({'amount': 10})}"
    )

    print(
        f"{DIM}Rolling reward...{RESET}"
    )

    try:
        data = download_text(
            url,
            timeout=20
        )

        payload = json.loads(data)

        results = payload.get(
            "results",
            []
        )

        if not results:
            return None

        new_results = [
            item
            for item in results
            if item.get("url")
            and item.get("url")
            not in old_urls
        ]

        item = random.choice(
            new_results
            if new_results
            else results
        )

        image_url = item.get("url")

        if not image_url:
            return None

        dimensions = item.get(
            "dimensions",
            {}
        )

        return {
            "url": image_url,
            "artist": item.get("artist_name"),
            "artist_href": item.get("artist_href"),
            "source": item.get("source_url"),
            "width": dimensions.get("width"),
            "height": dimensions.get("height"),
        }

    except HTTPError as e:
        print(
            f"{RED}Reward API HTTP {e.code}{RESET}"
        )
        return None

    except URLError as e:
        print(
            f"{RED}Reward API connection error: {e}{RESET}"
        )
        return None

    except json.JSONDecodeError:
        print(
            f"{RED}Reward API returned invalid JSON.{RESET}"
        )
        return None

    except Exception as e:
        print(
            f"{RED}Reward API error: {e}{RESET}"
        )
        return None


# ============================================================
# DOWNLOAD REWARD
# ============================================================

def download_reward(
    reward,
    rarity,
    collection_id
):
    if not reward:
        return None

    image_url = reward.get("url")

    if not image_url:
        return None

    clean_url = image_url.split("?")[0]

    extension = (
        Path(clean_url)
        .suffix
        .lower()
        .replace(".", "")
    )

    if extension not in {
        "png",
        "jpg",
        "jpeg",
        "webp",
    }:
        extension = "jpg"

    rarity_dir = (
        REWARD_DIR
        / rarity
    )

    rarity_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    filename = (
        f"{collection_id:04d}_"
        f"{today_string()}."
        f"{extension}"
    )

    output_path = (
        rarity_dir
        / filename
    )

    try:
        data = download_bytes(
            image_url,
            timeout=30,
            headers={
                "User-Agent": REWARD_USER_AGENT,
                "Accept": "image/*,*/*;q=0.8",
            }
        )

        if not data:
            return None

        with open(
            output_path,
            "wb"
        ) as f:
            f.write(data)

        collection = load_collection()

        collection["items"].append({
            "id": collection_id,
            "rarity": rarity,
            "url": image_url,
            "local_path": str(output_path),
            "artist": reward.get("artist"),
            "artist_href": reward.get("artist_href"),
            "source": reward.get("source"),
            "width": reward.get("width"),
            "height": reward.get("height"),
            "date": today_string(),
        })

        save_collection(collection)

        return output_path

    except HTTPError as e:
        print(
            f"{RED}Image HTTP error {e.code}{RESET}"
        )
        return None

    except Exception as e:
        print(
            f"{RED}Download failed: {e}{RESET}"
        )
        return None


# ============================================================
# REWARD VIEWER
# ============================================================

def open_reward_image(
    path,
    rarity="R",
    collection_id=None,
    total_collected=0,
    parent=None
):
    if path is None:
        return False

    path = Path(path).resolve()

    if not path.exists():
        print(
            f"{RED}Image file does not exist.{RESET}"
        )
        return False

    try:
        import tkinter as tk
        from PIL import Image, ImageTk
    except ImportError:
        print(
            f"{RED}Thiếu Pillow.{RESET}"
        )
        print(
            "py -3 -m pip install pillow"
        )
        return False

    try:
        image = Image.open(path).convert("RGB")

        created_root = parent is None

        if created_root:
            window = tk.Tk()
        else:
            window = tk.Toplevel(parent)

        window.title(
            "DAILY WORDLE — REWARD"
        )

        window.configure(
            bg="#08080A"
        )

        window.attributes(
            "-fullscreen",
            True
        )

        window.bind(
            "<Escape>",
            lambda e: window.destroy()
        )

        screen_w = window.winfo_screenwidth()
        screen_h = window.winfo_screenheight()

        rarity_data = RARITIES.get(
            rarity,
            RARITIES["R"]
        )

        rarity_color = rarity_data["color"]

        header = tk.Label(
            window,
            text="✦  REWARD UNLOCKED  ✦",
            font=("Arial", 25, "bold"),
            fg="white",
            bg="#08080A"
        )

        header.pack(pady=(25, 4))

        rarity_label = tk.Label(
            window,
            text=f"{rarity}  REWARD",
            font=("Arial", 31, "bold"),
            fg=rarity_color,
            bg="#08080A"
        )

        rarity_label.pack()

        image.thumbnail(
            (
                screen_w - 180,
                screen_h - 230
            ),
            Image.Resampling.LANCZOS
        )

        photo = ImageTk.PhotoImage(
            image,
            master=window
        )

        image_label = tk.Label(
            window,
            image=photo,
            bg="#08080A",
            bd=0
        )

        image_label.image = photo

        image_label.pack(
            expand=True
        )

        if collection_id is not None:
            bottom_text = (
                f"COLLECTION #{collection_id:04d}"
                f"   •   TOTAL {total_collected}"
                f"   •   ESC TO CLOSE"
            )
        else:
            bottom_text = "ESC TO CLOSE"

        bottom = tk.Label(
            window,
            text=bottom_text,
            font=("Arial", 10, "bold"),
            fg="#777777",
            bg="#08080A"
        )

        bottom.pack(
            pady=(5, 20)
        )

        image_label.bind(
            "<Button-1>",
            lambda e: window.destroy()
        )

        try:
            window.attributes(
                "-alpha",
                0.0
            )

            def fade(alpha=0.0):
                alpha += 0.06

                if alpha >= 1:
                    window.attributes(
                        "-alpha",
                        1.0
                    )
                    return

                window.attributes(
                    "-alpha",
                    alpha
                )

                window.after(
                    20,
                    lambda: fade(alpha)
                )

            window.after(
                30,
                fade
            )

        except Exception:
            pass

        if created_root:
            window.mainloop()
        else:
            parent.wait_window(window)

        return True

    except Exception as e:
        print(
            f"{RED}Could not open viewer: {e}{RESET}"
        )
        return False


# ============================================================
# RARITY ROLL
# ============================================================

def choose_rarity(guess_count):
    speed = (
        MAX_GUESSES - guess_count
    ) / (
        MAX_GUESSES - 1
    )

    speed = max(
        0,
        min(1, speed)
    )

    rates = {
        "R": 70 - 35 * speed,
        "SR": 22 + 8 * speed,
        "SSR": 7 + 17 * speed,
        "UR": 1 + 10 * speed,
    }

    total = sum(rates.values())

    roll = random.uniform(
        0,
        total
    )

    current = 0

    for rarity, weight in rates.items():
        current += weight

        if roll <= current:
            return rarity, rates

    return "R", rates


# ============================================================
# REWARD SCREEN
# ============================================================

def reward_screen(
    guess_count,
    streak
):
    clear_screen()

    counts = collection_counts()
    total = sum(counts.values())

    panel(
        "VICTORY REWARD",
        [
            f"Solved in     : {guess_count}/6 guesses",
            f"Current streak: {streak}",
            "",
            f"Collection    : {total}",
            f"R             : {counts['R']}",
            f"SR            : {counts['SR']}",
            f"SSR           : {counts['SSR']}",
            f"UR            : {counts['UR']}",
            "",
            "1  →  Open random anime reward",
            "2  →  Skip",
        ]
    )

    choice = input(
        f"\n{CYAN}› {RESET}"
    ).strip()

    if choice != "1":
        return

    rarity, rates = choose_rarity(
        guess_count
    )

    print()

    print(
        f"{DIM}"
        f"R {rates['R']:.1f}%  •  "
        f"SR {rates['SR']:.1f}%  •  "
        f"SSR {rates['SSR']:.1f}%  •  "
        f"UR {rates['UR']:.1f}%"
        f"{RESET}"
    )

    print(
        f"\n{BOLD}"
        "Rolling..."
        f"{RESET}"
    )

    collection_id = next_collection_id()

    reward = get_random_reward()

    if reward is None:
        print(
            f"\n{RED}Không lấy được reward.{RESET}"
        )
        pause()
        return

    image_path = download_reward(
        reward,
        rarity,
        collection_id
    )

    if image_path is None:
        print(
            f"\n{RED}Không tải được ảnh.{RESET}"
        )
        pause()
        return

    new_counts = collection_counts()
    new_total = sum(new_counts.values())

    clear_screen()

    panel(
        f"{rarity} REWARD UNLOCKED",
        [
            f"Reward ID : #{collection_id:04d}",
            f"Rarity    : {rarity}",
            f"Collection: {new_total}",
            "",
            "Reward saved successfully.",
        ]
    )

    open_reward_image(
        image_path,
        rarity=rarity,
        collection_id=collection_id,
        total_collected=new_total
    )


# ============================================================
# GACHA
# ============================================================

def perform_gacha_pull(save):
    rarity = choose_gacha_rarity()
    collection_id = next_collection_id()

    reward = get_random_reward()

    if reward is None:
        return None

    image_path = download_reward(
        reward,
        rarity,
        collection_id
    )

    if image_path is None:
        return None

    return {
        "rarity": rarity,
        "id": collection_id,
        "path": image_path,
    }


def gacha_once(save):
    if money(save) < GACHA_COST:
        print(
            f"\n{RED}Not enough money.{RESET}"
        )
        return

    save["money"] -= GACHA_COST
    save_game(save)

    clear_screen()

    panel(
        "GACHA ×1",
        [
            f"Cost       : {GACHA_COST} coins",
            f"Remaining  : {money(save):,} coins",
            "",
            "Rolling reward...",
        ]
    )

    result = perform_gacha_pull(save)

    if result is None:
        save["money"] += GACHA_COST
        save_game(save)

        print(
            f"\n{RED}"
            "Gacha failed — money refunded."
            f"{RESET}"
        )

        pause()
        return

    counts = collection_counts()

    clear_screen()

    panel(
        f"{result['rarity']} GACHA!",
        [
            f"Reward ID : #{result['id']:04d}",
            f"Rarity    : {result['rarity']}",
            f"Coins     : {money(save):,}",
            f"Collection: {sum(counts.values())}",
        ]
    )

    open_reward_image(
        result["path"],
        rarity=result["rarity"],
        collection_id=result["id"],
        total_collected=sum(counts.values())
    )

def gacha_screen():
    save = load_save()

    while True:
        clear_screen()

        counts = collection_counts()

        panel(
            "GACHA",
            [
                f"Coins       : {money(save):,} coins",
                "",
                f"R   {counts['R']:>4}",
                f"SR  {counts['SR']:>4}",
                f"SSR {counts['SSR']:>4}",
                f"UR  {counts['UR']:>4}",
                "",
                f"1  Pull ×1    — {GACHA_COST:,} coins",
                f"2  Pull ×10   — {GACHA_10_COST:,} coins",
                f"3  Pull ×100  — {GACHA_100_COST:,} coins",
                "4  Back",
            ]
        )

        choice = input(
            f"\n{CYAN}› {RESET}"
        ).strip()

        # ====================================================
        # ×1
        # ====================================================

        if choice == "1":
            gacha_once(save)
            save = load_save()

        # ====================================================
        # ×10
        # ====================================================

        elif choice == "2":
            if money(save) < GACHA_10_COST:
                print(
                    f"\n{RED}Not enough money.{RESET}"
                )
                pause()
                continue

            # Trừ 900 ngay
            save["money"] -= GACHA_10_COST
            save_game(save)

            results = []

            for i in range(10):
                print(
                    f"\n{DIM}"
                    f"Pull {i + 1}/10..."
                    f"{RESET}"
                )

                result = perform_gacha_pull(save)

                if result is None:
                    # Pull lỗi → hoàn 100
                    save["money"] += GACHA_COST

                    print(
                        f"{RED}"
                        f"Pull failed — 100 refunded."
                        f"{RESET}"
                    )

                    continue

                results.append(result)

                print(
                    f"{GREEN}"
                    f"✓ #{result['id']:04d}"
                    f"  {result['rarity']}"
                    f"{RESET}"
                )

            # Lưu ngay sau khi hoàn thành
            save_game(save)

            clear_screen()

            lines = [
                f"Total cost : {GACHA_10_COST:,} coins",
                f"Successful : {len(results)}/10",
                f"Coins left : {money(save):,}",
                "",
            ]

            for result in results:
                lines.append(
                    f"#{result['id']:04d}"
                    f"   {result['rarity']}"
                )

            panel(
                "10-PULL COMPLETE",
                lines
            )

            pause()

        # ====================================================
        # ×100
        # ====================================================

        elif choice == "3":

            if money(save) < GACHA_100_COST:
                print(
                    f"\n{RED}"
                    f"Not enough money."
                    f"{RESET}"
                )
                pause()
                continue

            # ------------------------------------------------
            # Trừ 8,000 một lần
            # ------------------------------------------------

            save["money"] -= GACHA_100_COST
            save_game(save)

            results = []

            clear_screen()

            panel(
                "GACHA ×100",
                [
                    f"Cost      : {GACHA_100_COST:,} coins",
                    f"Coins left: {money(save):,} coins",
                    "",
                    "Rolling 100 rewards...",
                ]
            )

            # ------------------------------------------------
            # Roll 100 lần
            # ------------------------------------------------

            for i in range(100):

                print(
                    f"\n{DIM}"
                    f"Pull {i + 1}/100..."
                    f"{RESET}"
                )

                result = perform_gacha_pull(save)

                if result is None:

                    # Pull lỗi → hoàn 100
                    save["money"] += GACHA_COST

                    print(
                        f"{RED}"
                        f"✗ Failed — +100 refunded"
                        f"{RESET}"
                    )

                    continue

                results.append(result)

                print(
                    f"{GREEN}"
                    f"✓ #{result['id']:04d}"
                    f"  {result['rarity']}"
                    f"{RESET}"
                )

                # --------------------------------------------
                # Lưu tiền ngay
                # --------------------------------------------

                save_game(save)

            # ------------------------------------------------
            # Thống kê
            # ------------------------------------------------

            rarity_counts = {
                "R": 0,
                "SR": 0,
                "SSR": 0,
                "UR": 0,
            }

            for result in results:
                rarity = result["rarity"]

                if rarity in rarity_counts:
                    rarity_counts[rarity] += 1

            # Lưu lần cuối
            save_game(save)

            clear_screen()

            lines = [
                f"Total cost : {GACHA_100_COST:,} coins",
                f"Successful : {len(results)}/100",
                f"Coins left : {money(save):,} coins",
                "",
                f"R          : {rarity_counts['R']}",
                f"SR         : {rarity_counts['SR']}",
                f"SSR        : {rarity_counts['SSR']}",
                f"UR         : {rarity_counts['UR']}",
                "",
            ]

            # Hiển thị ID đã roll
            if results:
                lines.append("Rewards:")

                for result in results:
                    lines.append(
                        f"#{result['id']:04d}"
                        f"  {result['rarity']}"
                    )

            panel(
                "100-PULL COMPLETE",
                lines
            )

            pause()

        # ====================================================
        # BACK
        # ====================================================

        elif choice == "4":
            return

        else:
            print(
                f"\n{RED}"
                f"Invalid choice."
                f"{RESET}"
            )
            pause()

def sell_screen():
    save = load_save()

    while True:
        clear_screen()

        collection = load_collection()
        items = collection.get(
            "items",
            []
        )

        if not items:
            panel(
                "SELL",
                [
                    "Collection is empty."
                ]
            )
            pause()
            return

        lines = [
            f"Coins: {money(save):,}",
            "",
        ]

        for item in items:
            rarity = item.get(
                "rarity",
                "R"
            )

            item_id = int(
                item.get(
                    "id",
                    0
                )
            )

            price = SELL_PRICES.get(
                rarity,
                50
            )

            title = item.get(
                "fusion_title"
            )

            name = (
                f"Fusion: {title}"
                if title
                else "Anime Reward"
            )

            lines.append(
                f"#{item_id:04d}  "
                f"{rarity:<3}  "
                f"{price:>5}  "
                f"{name}"
            )

        lines.extend([
            "",
            "Nhập ID muốn bán:  1 2 7",
            "ALL để bán toàn bộ",
            "BACK để quay lại",
        ])

        panel(
            "SELL COLLECTION",
            lines
        )

        raw = input(
            f"\n{CYAN}› {RESET}"
        ).strip()

        if raw.upper() == "BACK":
            return

        # ====================================================
        # SELL ALL
        # ====================================================

        if raw.upper() == "ALL":
            selected = items.copy()

            total_value = sum(
                SELL_PRICES.get(
                    item.get("rarity", "R"),
                    50
                )
                for item in selected
            )

            print(
                f"\nSell ALL {len(selected)} item(s)"
                f" → {total_value:,} coins"
            )

            confirm = input(
                f"{RED}Confirm SELL ALL [Y/N]: {RESET}"
            ).strip().upper()

            if confirm != "Y":
                continue

            # Xóa file ảnh local
            for item in selected:
                local_path = item.get(
                    "local_path"
                )

                if local_path:
                    path = Path(local_path)

                    if not path.is_absolute():
                        path = BASE_DIR / path

                    try:
                        if path.exists():
                            path.unlink()
                    except Exception:
                        pass

            # Xóa toàn bộ collection
            collection["items"] = []

            save_collection(collection)

            # Cộng tiền
            save["money"] += total_value
            save_game(save)

            print(
                f"\n{GREEN}"
                f"✓ Sold ALL {len(selected)} item(s)"
                f" for {total_value:,} coins!"
                f"{RESET}"
            )

            pause()
            continue

        # ====================================================
        # SELL BY ID
        # ====================================================

        try:
            ids = list(dict.fromkeys(
                int(x)
                for x in raw.split()
            ))
        except ValueError:
            print(
                f"\n{RED}ID không hợp lệ.{RESET}"
            )
            pause()
            continue

        selected = [
            item
            for item in items
            if int(item.get("id", 0)) in ids
        ]

        if len(selected) != len(ids):
            print(
                f"\n{RED}"
                "Có ID không tồn tại."
                f"{RESET}"
            )
            pause()
            continue

        total_value = sum(
            SELL_PRICES.get(
                item.get("rarity", "R"),
                50
            )
            for item in selected
        )

        print(
            f"\nSell {len(selected)} item(s)"
            f" → {total_value:,} coins"
        )

        confirm = input(
            "Confirm [Y/N]: "
        ).strip().upper()

        if confirm != "Y":
            continue

        selected_ids = set(ids)

        for item in selected:
            local_path = item.get(
                "local_path"
            )

            if local_path:
                path = Path(local_path)

                if not path.is_absolute():
                    path = BASE_DIR / path

                try:
                    if path.exists():
                        path.unlink()
                except Exception:
                    pass

        collection["items"] = [
            item
            for item in items
            if int(item.get("id", 0))
            not in selected_ids
        ]

        save_collection(collection)

        save["money"] += total_value
        save_game(save)

        print(
            f"\n{GREEN}"
            f"✓ Sold for {total_value:,} coins!"
            f"{RESET}"
        )

        pause()
# ============================================================
# FUSION IMAGE
# ============================================================

def create_fusion_image(
    source_items,
    title,
    rarity,
    output_path
):
    try:
        from PIL import (
            Image,
            ImageOps,
            ImageDraw,
            ImageFont,
        )
    except ImportError:
        print(
            f"{RED}Cần Pillow.{RESET}"
        )
        return False

    width = 1600
    height = 1150

    canvas = Image.new(
        "RGB",
        (width, height),
        "#08080A"
    )

    draw = ImageDraw.Draw(canvas)

    def load_font(size, bold=False):
        candidates = []

        if bold:
            candidates += [
                "C:/Windows/Fonts/arialbd.ttf",
                "C:/Windows/Fonts/segoeuib.ttf",
            ]
        else:
            candidates += [
                "C:/Windows/Fonts/arial.ttf",
                "C:/Windows/Fonts/segoeui.ttf",
            ]

        for path in candidates:
            try:
                return ImageFont.truetype(
                    path,
                    size
                )
            except Exception:
                pass

        return ImageFont.load_default()

    title_font = load_font(
        56,
        True
    )

    rarity_font = load_font(
        35,
        True
    )

    small_font = load_font(22)

    rarity_color = RARITIES.get(
        rarity,
        RARITIES["R"]
    )["color"]

    title = title.strip() or "FUSION"

    box = draw.textbbox(
        (0, 0),
        title,
        font=title_font
    )

    title_w = box[2] - box[0]

    draw.text(
        (
            (width - title_w) / 2,
            25
        ),
        title,
        fill="white",
        font=title_font
    )

    rarity_text = (
        f"✦ {rarity} FUSION ✦"
    )

    box = draw.textbbox(
        (0, 0),
        rarity_text,
        font=rarity_font
    )

    rarity_w = box[2] - box[0]

    draw.text(
        (
            (width - rarity_w) / 2,
            90
        ),
        rarity_text,
        fill=rarity_color,
        font=rarity_font
    )

    margin_x = 45
    top = 165
    gap = 15

    columns = 5
    rows = 2

    cell_w = (
        width
        - margin_x * 2
        - gap * (columns - 1)
    ) // columns

    cell_h = 430

    for index, item in enumerate(source_items):
        path = Path(
            item.get(
                "local_path",
                ""
            )
        )

        if not path.is_absolute():
            path = BASE_DIR / path

        try:
            image = Image.open(
                path
            ).convert("RGB")

            image = ImageOps.fit(
                image,
                (cell_w, cell_h),
                method=Image.Resampling.LANCZOS
            )

            x = (
                margin_x
                + index % columns
                * (cell_w + gap)
            )

            y = (
                top
                + index // columns
                * (cell_h + gap)
            )

            canvas.paste(
                image,
                (x, y)
            )

            draw.rectangle(
                (
                    x,
                    y,
                    x + cell_w,
                    y + cell_h
                ),
                outline=rarity_color,
                width=3
            )

            draw.text(
                (
                    x + 8,
                    y + 8
                ),
                f"#{int(item.get('id', 0)):04d}",
                fill="white",
                font=small_font
            )

        except Exception:
            pass

    footer = "10 REWARDS FUSED"

    box = draw.textbbox(
        (0, 0),
        footer,
        font=small_font
    )

    footer_w = box[2] - box[0]

    draw.text(
        (
            (width - footer_w) / 2,
            height - 40
        ),
        footer,
        fill="#777777",
        font=small_font
    )

    try:
        canvas.save(output_path)
        return True
    except Exception:
        return False


# ============================================================
# FUSION
# ============================================================

def fusion_rarity(items):
    levels = [
        rarity_level(
            item.get("rarity", "R")
        )
        for item in items
    ]

    average = (
        sum(levels)
        / len(levels)
    )

    return level_rarity(
        int(average) + 1
    )


def fusion_screen():
    while True:
        clear_screen()

        collection = load_collection()

        items = collection.get(
            "items",
            []
        )

        if len(items) < 10:
            panel(
                "FUSION",
                [
                    "Fusion cần chính xác 10 ảnh.",
                    "",
                    f"Hiện có: {len(items)}/10",
                ]
            )

            pause()
            return

        lines = [
            "Chọn đúng 10 ID.",
            "",
        ]

        for item in items:
            item_id = int(
                item.get("id", 0)
            )

            rarity = item.get(
                "rarity",
                "R"
            )

            title = item.get(
                "fusion_title"
            )

            name = (
                f"Fusion: {title}"
                if title
                else "Anime Reward"
            )

            lines.append(
                f"#{item_id:04d}  "
                f"{rarity:<3}  "
                f"{name}"
            )

        lines.extend([
            "",
            "Ví dụ: 1 2 3 4 5 6 7 8 9 10",
            "BACK để quay lại",
        ])

        panel(
            "FUSION",
            lines
        )

        raw = input(
            f"\n{CYAN}› {RESET}"
        ).strip()

        if raw.upper() == "BACK":
            return

        try:
            ids = list(dict.fromkeys(
                int(x)
                for x in raw.split()
            ))
        except ValueError:
            print(
                f"{RED}ID không hợp lệ.{RESET}"
            )
            pause()
            continue

        if len(ids) != 10:
            print(
                f"{RED}"
                "Fusion cần đúng 10 ID khác nhau."
                f"{RESET}"
            )
            pause()
            continue

        selected = []

        for item_id in ids:
            found = next(
                (
                    item
                    for item in items
                    if int(
                        item.get("id", 0)
                    ) == item_id
                ),
                None
            )

            if found is None:
                break

            selected.append(found)

        if len(selected) != 10:
            print(
                f"{RED}"
                "Có ID không tồn tại."
                f"{RESET}"
            )
            pause()
            continue

        title = input(
            "\nFusion name: "
        ).strip()

        if not title:
            title = "Anime Fusion"

        rarity = fusion_rarity(
            selected
        )

        print(
            f"\nFusion result: "
            f"{rarity_text(rarity)}"
        )

        confirm = input(
            "Fuse these 10 items? [Y/N] "
        ).strip().upper()

        if confirm != "Y":
            continue

        collection_id = next_collection_id()

        rarity_dir = (
            REWARD_DIR
            / rarity
        )

        rarity_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        output_path = (
            rarity_dir
            / f"{collection_id:04d}_fusion.png"
        )

        success = create_fusion_image(
            selected,
            title,
            rarity,
            output_path
        )

        if not success:
            print(
                f"{RED}"
                "Fusion image creation failed."
                f"{RESET}"
            )
            pause()
            return

        selected_ids = {
            int(
                item.get("id", 0)
            )
            for item in selected
        }

        for item in selected:
            local_path = item.get(
                "local_path"
            )

            if local_path:
                path = Path(local_path)

                if not path.is_absolute():
                    path = BASE_DIR / path

                try:
                    if path.exists():
                        path.unlink()
                except Exception:
                    pass

        new_item = {
            "id": collection_id,
            "rarity": rarity,
            "url": None,
            "local_path": str(output_path),
            "artist": None,
            "artist_href": None,
            "source": None,
            "width": 1600,
            "height": 1150,
            "date": today_string(),
            "type": "fusion",
            "fusion_title": title,
            "materials": [
                int(
                    item.get("id", 0)
                )
                for item in selected
            ],
        }

        collection["items"] = [
            item
            for item in items
            if int(
                item.get("id", 0)
            ) not in selected_ids
        ]

        collection["items"].append(
            new_item
        )

        save_collection(
            collection
        )

        clear_screen()

        panel(
            f"{rarity} FUSION!",
            [
                f"Name      : {title}",
                f"Reward ID : #{collection_id:04d}",
                f"Rarity    : {rarity}",
                f"Collection: {len(collection['items'])}",
                "",
                "10 rewards have been fused!",
            ]
        )

        open_reward_image(
            output_path,
            rarity=rarity,
            collection_id=collection_id,
            total_collected=len(
                collection["items"]
            )
        )

        return


# ============================================================
# COLLECTION GALLERY
# ============================================================
def show_collection():
    try:
        import tkinter as tk
        from PIL import Image, ImageTk
    except ImportError:
        print(f"{RED}Thiếu Pillow.{RESET}")
        print("py -3 -m pip install pillow")
        return

    collection = load_collection()
    items = collection.get("items", [])

    if not items:
        clear_screen()

        panel(
            "COLLECTION",
            [
                "Collection hiện đang trống.",
                "",
                "Hãy chơi Wordle hoặc Gacha để nhận reward.",
            ]
        )

        pause()
        return

    root = tk.Tk()

    root.title("DAILY WORDLE — COLLECTION")
    root.configure(bg="#08080A")
    root.attributes("-fullscreen", True)

    root.bind(
        "<Escape>",
        lambda e: root.destroy()
    )

    counts = collection_counts()
    total = sum(counts.values())

    # ========================================================
    # HEADER
    # ========================================================

    title = tk.Label(
        root,
        text="✦  REWARD COLLECTION  ✦",
        font=("Arial", 25, "bold"),
        fg="white",
        bg="#08080A"
    )

    title.pack(pady=(20, 5))

    stats = tk.Label(
        root,
        text=(
            f"TOTAL {total}     "
            f"R {counts['R']}     "
            f"SR {counts['SR']}     "
            f"SSR {counts['SSR']}     "
            f"UR {counts['UR']}"
        ),
        font=("Arial", 12, "bold"),
        fg="#888888",
        bg="#08080A"
    )

    stats.pack(pady=(0, 15))

    # ========================================================
    # MAIN CONTAINER
    # ========================================================

    container = tk.Frame(
        root,
        bg="#08080A"
    )

    container.pack(
        fill="both",
        expand=True,
        padx=25
    )

    canvas = tk.Canvas(
        container,
        bg="#08080A",
        highlightthickness=0,
        bd=0
    )

    scrollbar = tk.Scrollbar(
        container,
        orient="vertical",
        command=canvas.yview
    )

    canvas.configure(
        yscrollcommand=scrollbar.set
    )

    scrollbar.pack(
        side="right",
        fill="y"
    )

    canvas.pack(
        side="left",
        fill="both",
        expand=True
    )

    # ========================================================
    # GALLERY
    # ========================================================

    gallery = tk.Frame(
        canvas,
        bg="#08080A"
    )

    gallery_window = canvas.create_window(
        (0, 0),
        window=gallery,
        anchor="nw"
    )

    # ========================================================
    # FORCE 4 COLUMNS TO SPREAD EVENLY
    # ========================================================

    columns = 4

    for column in range(columns):
        gallery.grid_columnconfigure(
            column,
            weight=1,
            uniform="collection_column"
        )

    image_refs = []

    # ========================================================
    # OPEN ITEM
    # ========================================================

    def open_item(item):
        local_path = item.get("local_path")

        if not local_path:
            return

        path = Path(local_path)

        if not path.is_absolute():
            path = BASE_DIR / path

        open_reward_image(
            path,
            rarity=item.get("rarity", "R"),
            collection_id=item.get("id"),
            total_collected=len(items),
            parent=root
        )

    # ========================================================
    # CREATE CARDS
    # ========================================================

    for index, item in enumerate(items):

        row = index // columns
        column = index % columns

        rarity = item.get(
            "rarity",
            "R"
        )

        rarity_color = RARITIES.get(
            rarity,
            RARITIES["R"]
        )["color"]

        # ----------------------------------------------------
        # CARD
        # ----------------------------------------------------

        card = tk.Frame(
            gallery,
            bg="#111116",
            highlightbackground=rarity_color,
            highlightthickness=2,
            padx=8,
            pady=8
        )

        card.grid(
            row=row,
            column=column,
            padx=14,
            pady=14,
            sticky="n"
        )

        # ----------------------------------------------------
        # IMAGE
        # ----------------------------------------------------

        local_path = item.get(
            "local_path"
        )

        try:
            path = Path(local_path)

            if not path.is_absolute():
                path = BASE_DIR / path

            image = Image.open(
                path
            ).convert("RGB")

            image.thumbnail(
                (220, 260),
                Image.Resampling.LANCZOS
            )

            photo = ImageTk.PhotoImage(
                image,
                master=root
            )

            image_refs.append(photo)

            button = tk.Button(
                card,
                image=photo,
                bg="#111116",
                activebackground="#222228",
                bd=0,
                highlightthickness=0,
                cursor="hand2",
                command=lambda current=item:
                    open_item(current)
            )

            button.pack()

        except Exception:

            missing = tk.Label(
                card,
                text="IMAGE\nMISSING",
                font=("Arial", 11, "bold"),
                fg="#555555",
                bg="#111116",
                width=23,
                height=12
            )

            missing.pack()

        # ----------------------------------------------------
        # ID + RARITY
        # ----------------------------------------------------

        label = tk.Label(
            card,
            text=(
                f"#{int(item.get('id', 0)):04d}"
                f"     {rarity}"
            ),
            font=("Arial", 13, "bold"),
            fg=rarity_color,
            bg="#111116"
        )

        label.pack(
            pady=(7, 2)
        )

        # ----------------------------------------------------
        # DATE
        # ----------------------------------------------------

        date_label = tk.Label(
            card,
            text=item.get("date", ""),
            font=("Arial", 9),
            fg="#666666",
            bg="#111116"
        )

        date_label.pack()

    # ========================================================
    # UPDATE CANVAS
    # ========================================================

    def update_scroll(event=None):

        gallery.update_idletasks()

        canvas_width = canvas.winfo_width()

        if canvas_width <= 1:
            return

        # Gallery luôn bằng đúng chiều rộng canvas.
        canvas.itemconfigure(
            gallery_window,
            width=canvas_width
        )

        canvas.configure(
            scrollregion=canvas.bbox("all")
        )

    gallery.bind(
        "<Configure>",
        update_scroll
    )

    canvas.bind(
        "<Configure>",
        update_scroll
    )

    # ========================================================
    # MOUSE WHEEL
    # ========================================================

    def mousewheel(event):

        if event.delta:
            canvas.yview_scroll(
                int(-1 * (event.delta / 120)),
                "units"
            )

    canvas.bind_all(
        "<MouseWheel>",
        mousewheel
    )

    # ========================================================
    # FOOTER
    # ========================================================

    footer = tk.Label(
        root,
        text=(
            "CLICK A REWARD TO OPEN"
            "    •    "
            "ESC TO CLOSE"
        ),
        font=("Arial", 10, "bold"),
        fg="#666666",
        bg="#08080A"
    )

    footer.pack(
        pady=(5, 15)
    )

    # ========================================================
    # INITIAL UPDATE
    # ========================================================

    root.after(
        100,
        update_scroll
    )

    root.mainloop()

# ============================================================
# MAIN
# ============================================================

def main():
    enable_ansi()

    # --------------------------------------------------------
    # COMMANDS
    # --------------------------------------------------------

    if len(sys.argv) > 1:
        command = (
            sys.argv[1]
            .strip()
            .lower()
        )

        if command in {
            "collection",
            "gallery",
            "--collection",
            "--gallery",
        }:
            show_collection()
            return

        if command == "gacha":
            gacha_screen()
            return

        if command == "sell":
            sell_screen()
            return

        if command == "fusion":
            fusion_screen()
            return

    # --------------------------------------------------------
    # DEFAULT DAILY WORDLE
    # --------------------------------------------------------

    save = load_save()

    answer, puzzle_date, source = (
        get_wordle_data()
    )

    if answer is None:
        clear_screen()

        panel(
            "WORDLE UNAVAILABLE",
            [
                "Không lấy được Wordle hôm nay.",
                "",
                "Hãy kiểm tra kết nối Internet.",
            ]
        )

        pause()
        return

    if already_played(
        save,
        puzzle_date
    ):
        pause()
        return

    result = play_game(
        answer,
        puzzle_date,
        source,
        save
    )

    # EXIT không tính lượt
    if result is None:
        return

    finish_game(
        save,
        puzzle_date,
        result
    )

    # --------------------------------------------------------
    # RESULT SUMMARY
    # --------------------------------------------------------

    save = load_save()

    clear_screen()

    if result["result"] == "win":
        earned = save.get(
            "last_money_earned",
            0
        )

        panel(
            "VICTORY",
            [
                "✓ Bạn đã giải được Wordle!",
                "",
                f"Guesses : {result['guesses']}/6",
                f"Streak  : {save['streak']}",
                f"Coins   : +{earned:,}",
                f"Balance : {money(save):,}",
            ]
        )

        reward_screen(
            result["guesses"],
            save["streak"]
        )

    else:
        earned = save.get(
            "last_money_earned",
            25
        )

        panel(
            "GAME OVER",
            [
                "Bạn đã dùng hết 6 lượt.",
                "",
                f"Coins   : +{earned:,}",
                f"Balance : {money(save):,}",
                f"Streak  : {save['streak']}",
            ]
        )

        pause()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        print(
            f"\n{DIM}Game interrupted.{RESET}"
        )

    except Exception as e:
        print()
        print(
            f"{RED}"
            "╔══════════════════════════════════════════════════════════════╗"
            f"{RESET}"
        )
        print(
            f"{RED}"
            "║                      UNEXPECTED ERROR                       ║"
            f"{RESET}"
        )
        print(
            f"{RED}"
            "╚══════════════════════════════════════════════════════════════╝"
            f"{RESET}"
        )
        print()
        print(
            f"{RED}{e}{RESET}"
        )
        print()
        pause()