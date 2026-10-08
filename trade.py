import os
import json
import socket
import struct
import base64
import secrets
import subprocess
import re
import time
from pathlib import Path


# ============================================================
# CONFIG
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

SAVE_FILE = BASE_DIR / "save.json"
CACHE_DIR = BASE_DIR / "cache"
COLLECTION_FILE = CACHE_DIR / "collection.json"
REWARD_DIR = CACHE_DIR / "rewards"

DEFAULT_PORT = 48555

BUFFER_SIZE = 65536

GAME_NAME = "Daily Wordle"
PROTOCOL_VERSION = 1


# ============================================================
# COLORS
# ============================================================

RESET = "\033[0m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
WHITE = "\033[97m"


def c(text, color):
    return f"{color}{text}{RESET}"


# ============================================================
# FILE HELPERS
# ============================================================

def load_json(path, default):
    try:
        if not path.exists():
            return default

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception:
        return default


def save_json(path, data):
    """
    Ghi JSON an toàn hơn:
    ghi ra file .tmp rồi replace file cũ.
    """

    path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = path.with_suffix(path.suffix + ".tmp")

    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    os.replace(temp_path, path)


def load_save():
    return load_json(SAVE_FILE, {
        "money": 0
    })


def load_collection():
    return load_json(COLLECTION_FILE, [])


def save_collection(collection):
    save_json(COLLECTION_FILE, collection)


def save_game(save):
    save_json(SAVE_FILE, save)


# ============================================================
# COLLECTION
# ============================================================

def find_card(card_id):
    collection = load_collection()

    for card in collection:
        try:
            if int(card.get("id")) == int(card_id):
                return card
        except Exception:
            continue

    return None


def next_collection_id(collection=None):
    if collection is None:
        collection = load_collection()

    max_id = 0

    for item in collection:
        try:
            max_id = max(max_id, int(item.get("id", 0)))
        except Exception:
            pass

    return max_id + 1


# ============================================================
# PATH
# ============================================================

def resolve_local_path(local_path):
    """
    collection.json của game có thể lưu:
        cache/rewards/SSR/xxx.jpg

    hoặc đường dẫn tuyệt đối.

    Hàm này xử lý cả hai.
    """

    if not local_path:
        return None

    path = Path(local_path)

    if path.is_absolute():
        return path

    return BASE_DIR / path


def make_relative_path(path):
    try:
        return str(path.relative_to(BASE_DIR)).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


# ============================================================
# RARITY
# ============================================================

RARITY_ORDER = {
    "R": 1,
    "SR": 2,
    "SSR": 3,
    "UR": 4
}


def rarity_color(rarity):
    rarity = str(rarity).upper()

    if rarity == "UR":
        return MAGENTA

    if rarity == "SSR":
        return YELLOW

    if rarity == "SR":
        return CYAN

    return WHITE


# ============================================================
# CARD DISPLAY
# ============================================================

def card_name(card):
    fusion_title = card.get("fusion_title")

    if fusion_title:
        return fusion_title

    artist = card.get("artist")

    if artist:
        return str(artist)

    return "Unknown Card"


def print_card(card, prefix=""):
    if not card:
        print(prefix + "Không có card.")
        return

    card_id = card.get("id")
    rarity = str(card.get("rarity", "?")).upper()

    print(
        prefix
        + f"[ID {card_id}] "
        + c(f"{rarity}", rarity_color(rarity))
        + f" - {card_name(card)}"
    )


# ============================================================
# CARD SERIALIZATION
# ============================================================

def read_card_image(card):
    """
    Đọc ảnh local của card và chuyển thành base64.

    Không gửi local_path của máy A sang máy B,
    vì đường dẫn đó không tồn tại trên máy B.
    """

    local_path = card.get("local_path")

    if not local_path:
        return None

    path = resolve_local_path(local_path)

    if not path or not path.exists():
        return None

    try:
        with open(path, "rb") as f:
            raw = f.read()

        return base64.b64encode(raw).decode("ascii")

    except Exception:
        return None


def sanitize_card(card, include_image=True):
    """
    Chuyển card thành dữ liệu có thể gửi qua mạng.

    Không gửi local_path cũ.
    ID cũ cũng chỉ mang tính tham khảo.
    """

    if not card:
        return None

    result = {}

    allowed_fields = [
        "id",
        "rarity",
        "url",
        "artist",
        "artist_href",
        "source",
        "width",
        "height",
        "date",
        "type",
        "fusion_title",
        "materials"
    ]

    for key in allowed_fields:
        if key in card:
            result[key] = card[key]

    if include_image:
        image_data = read_card_image(card)

        if image_data is None:
            return None

        result["_image"] = image_data

    return result


def reconstruct_card(remote_card):
    """
    Tạo card mới trên máy nhận.
    """

    collection = load_collection()

    new_id = next_collection_id(collection)

    rarity = str(remote_card.get("rarity", "R")).upper()

    if rarity not in RARITY_ORDER:
        rarity = "R"

    image_data = remote_card.get("_image")

    if not image_data:
        raise ValueError("Trade card không có dữ liệu ảnh.")

    try:
        image_bytes = base64.b64decode(image_data)
    except Exception:
        raise ValueError("Dữ liệu ảnh trade bị lỗi.")

    # --------------------------------------------------------
    # Chọn extension
    # --------------------------------------------------------

    image_ext = ".jpg"

    url = str(remote_card.get("url") or "").lower()

    if ".png" in url:
        image_ext = ".png"
    elif ".webp" in url:
        image_ext = ".webp"
    elif ".gif" in url:
        image_ext = ".gif"
    elif ".jpeg" in url:
        image_ext = ".jpeg"

    rarity_dir = REWARD_DIR / rarity
    rarity_dir.mkdir(parents=True, exist_ok=True)

    new_filename = f"trade_{int(time.time())}_{secrets.token_hex(4)}{image_ext}"

    new_path = rarity_dir / new_filename

    with open(new_path, "wb") as f:
        f.write(image_bytes)

    # --------------------------------------------------------
    # Tạo card mới
    # --------------------------------------------------------

    new_card = {}

    for key in [
        "rarity",
        "url",
        "artist",
        "artist_href",
        "source",
        "width",
        "height",
        "date",
        "type",
        "fusion_title",
        "materials"
    ]:
        if key in remote_card:
            new_card[key] = remote_card[key]

    new_card["id"] = new_id
    new_card["local_path"] = make_relative_path(new_path)

    # Metadata bổ sung, không ảnh hưởng game cũ
    new_card["trade_received"] = True

    return new_card


# ============================================================
# SOCKET PROTOCOL
# ============================================================

def send_packet(sock, data):
    """
    Gửi JSON theo dạng:

        [4 byte length][JSON data]

    Không dùng recv() trực tiếp cho JSON,
    tránh lỗi packet bị chia nhỏ.
    """

    raw = json.dumps(
        data,
        ensure_ascii=False,
        separators=(",", ":")
    ).encode("utf-8")

    header = struct.pack("!I", len(raw))

    sock.sendall(header + raw)


def recv_exact(sock, amount):
    data = bytearray()

    while len(data) < amount:
        chunk = sock.recv(amount - len(data))

        if not chunk:
            raise ConnectionError("Đối phương đã ngắt kết nối.")

        data.extend(chunk)

    return bytes(data)


def receive_packet(sock):
    header = recv_exact(sock, 4)

    length = struct.unpack("!I", header)[0]

    if length <= 0:
        raise ConnectionError("Packet không hợp lệ.")

    # chống packet quá lớn
    if length > 100 * 1024 * 1024:
        raise ConnectionError("Packet quá lớn.")

    raw = recv_exact(sock, length)

    return json.loads(raw.decode("utf-8"))


# ============================================================
# RADMIN IP
# ============================================================

def find_radmin_ips():
    """
    Radmin thường dùng IP 26.x.x.x.

    Không phụ thuộc ngôn ngữ Windows vì chỉ tìm
    pattern IPv4 bắt đầu bằng 26.
    """

    ips = []

    try:
        result = subprocess.check_output(
            "ipconfig",
            shell=True,
            stderr=subprocess.DEVNULL
        )

        text = result.decode(
            "utf-8",
            errors="ignore"
        )

        matches = re.findall(
            r"\b26\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
            text
        )

        for ip in matches:
            if ip not in ips:
                ips.append(ip)

    except Exception:
        pass

    return ips


def print_radmin_ips():
    ips = find_radmin_ips()

    if not ips:
        print(c(
            "Không tìm thấy IP Radmin 26.x.x.x tự động.",
            YELLOW
        ))
        return []

    print(c("IP Radmin VPN của máy này:", GREEN))

    for ip in ips:
        print(f"  → {ip}")

    return ips


# ============================================================
# HANDSHAKE
# ============================================================

def handshake(sock, token):
    send_packet(sock, {
        "type": "HELLO",
        "game": GAME_NAME,
        "version": PROTOCOL_VERSION,
        "token": token
    })

    response = receive_packet(sock)

    if response.get("type") != "HELLO_OK":
        raise ConnectionError(
            response.get("message", "Handshake thất bại.")
        )


def accept_handshake(sock, expected_token):
    packet = receive_packet(sock)

    if packet.get("type") != "HELLO":
        send_packet(sock, {
            "type": "ERROR",
            "message": "Không phải kết nối Daily Wordle."
        })

        raise ConnectionError("Handshake không hợp lệ.")

    if packet.get("game") != GAME_NAME:
        raise ConnectionError("Game không tương thích.")

    if packet.get("version") != PROTOCOL_VERSION:
        raise ConnectionError("Version trade không tương thích.")

    if packet.get("token") != expected_token:
        send_packet(sock, {
            "type": "ERROR",
            "message": "Room code không đúng."
        })

        raise ConnectionError("Room code không đúng.")

    send_packet(sock, {
        "type": "HELLO_OK"
    })


# ============================================================
# ROOM CODE
# ============================================================

def generate_room_code():
    return str(secrets.randbelow(900000) + 100000)


# ============================================================
# TRADE VALIDATION
# ============================================================

def validate_card(card_id):
    card = find_card(card_id)

    if not card:
        return None, "Không tìm thấy card."

    local_path = resolve_local_path(card.get("local_path"))

    if not local_path or not local_path.exists():
        return None, "Ảnh card không tồn tại trên máy."

    return card, None


def validate_money(amount):
    try:
        amount = int(amount)
    except Exception:
        return False

    return amount > 0


# ============================================================
# COMMIT HELPERS
# ============================================================

def remove_card(card_id):
    collection = load_collection()

    target = None

    for card in collection:
        try:
            if int(card.get("id")) == int(card_id):
                target = card
                break
        except Exception:
            pass

    if not target:
        return False

    # Xóa ảnh local
    local_path = resolve_local_path(target.get("local_path"))

    if local_path and local_path.exists():
        try:
            local_path.unlink()
        except Exception:
            pass

    collection.remove(target)

    save_collection(collection)

    return True


def add_card(remote_card):
    collection = load_collection()

    new_card = reconstruct_card(remote_card)

    collection.append(new_card)

    save_collection(collection)

    return new_card


def add_money(amount):
    save = load_save()

    save["money"] = int(save.get("money", 0)) + int(amount)

    save_game(save)


def remove_money(amount):
    save = load_save()

    money = int(save.get("money", 0))

    if money < amount:
        return False

    save["money"] = money - amount

    save_game(save)

    return True


# ============================================================
# TRADE: CARD -> MONEY
# ============================================================

def send_card_for_money(sock):
    collection = load_collection()

    if not collection:
        print(c("Bạn không có card nào.", RED))
        return

    print()
    print(c("=== CARD CỦA BẠN ===", CYAN))

    for card in collection:
        print_card(card)

    print()

    try:
        card_id = int(input("ID card muốn bán/trade: "))
    except ValueError:
        print(c("ID không hợp lệ.", RED))
        return

    card, error = validate_card(card_id)

    if error:
        print(c(error, RED))
        return

    try:
        amount = int(input("Số coin muốn nhận: "))
    except ValueError:
        print(c("Số coin không hợp lệ.", RED))
        return

    if not validate_money(amount):
        print(c("Số coin phải > 0.", RED))
        return

    remote_card = sanitize_card(card)

    if not remote_card:
        print(c("Không thể đọc ảnh card.", RED))
        return

    trade_id = secrets.token_hex(8)

    send_packet(sock, {
        "type": "TRADE_OFFER",
        "trade_id": trade_id,
        "mode": "CARD_MONEY",

        "card": remote_card,

        "money": amount
    })

    print()
    print(c("Đã gửi đề nghị trade.", GREEN))
    print("Đang chờ đối phương phản hồi...")

    response = receive_packet(sock)

    if response.get("type") == "TRADE_REJECT":
        print(c(
            "Đối phương đã từ chối trade.",
            YELLOW
        ))
        return

    if response.get("type") != "TRADE_ACCEPT":
        print(c(
            response.get("message", "Trade thất bại."),
            RED
        ))
        return

    # --------------------------------------------------------
    # Validate lại card trước khi commit
    # --------------------------------------------------------

    current_card = find_card(card_id)

    if not current_card:
        send_packet(sock, {
            "type": "TRADE_ABORT",
            "message": "Card không còn tồn tại."
        })

        print(c("Card không còn tồn tại.", RED))
        return

    # --------------------------------------------------------
    # Commit phía người gửi
    # --------------------------------------------------------

    if not remove_card(card_id):
        send_packet(sock, {
            "type": "TRADE_ABORT",
            "message": "Không thể xóa card."
        })

        print(c("Không thể commit trade.", RED))
        return

    add_money(amount)

    send_packet(sock, {
        "type": "TRADE_COMMIT",
        "trade_id": trade_id
    })

    final = receive_packet(sock)

    if final.get("type") == "TRADE_DONE":
        print()
        print(c("✓ TRADE THÀNH CÔNG!", GREEN))
        print(f"Bạn nhận được: {amount:,} coins")
        return

    print(c(
        "Trade phía bên kia có vấn đề.",
        RED
    ))


# ============================================================
# TRADE: CARD -> CARD
# ============================================================

def send_card_for_card(sock):
    collection = load_collection()

    if not collection:
        print(c("Bạn không có card nào.", RED))
        return

    print()
    print(c("=== CHỌN CARD CỦA BẠN ===", CYAN))

    for card in collection:
        print_card(card)

    print()

    try:
        card_id = int(input("ID card muốn đưa: "))
    except ValueError:
        print(c("ID không hợp lệ.", RED))
        return

    card, error = validate_card(card_id)

    if error:
        print(c(error, RED))
        return

    remote_card = sanitize_card(card)

    if not remote_card:
        print(c("Không thể đọc ảnh card.", RED))
        return

    print()
    print(
        "Bạn sẽ gửi card này và yêu cầu đối phương chọn "
        "một card của họ."
    )

    print_card(card, "  ")

    confirm = input("\nGửi đề nghị? [Y/N]: ").strip().lower()

    if confirm != "y":
        return

    trade_id = secrets.token_hex(8)

    send_packet(sock, {
        "type": "TRADE_OFFER",
        "trade_id": trade_id,
        "mode": "CARD_CARD",

        "card": remote_card
    })

    print()
    print(c("Đã gửi đề nghị.", GREEN))
    print("Đang chờ đối phương chọn card...")

    response = receive_packet(sock)

    if response.get("type") == "TRADE_REJECT":
        print(c(
            "Đối phương đã từ chối trade.",
            YELLOW
        ))
        return

    if response.get("type") != "TRADE_ACCEPT":
        print(c(
            response.get("message", "Trade thất bại."),
            RED
        ))
        return

    received_remote_card = response.get("card")

    if not received_remote_card:
        print(c("Đối phương không gửi card.", RED))
        return

    print()
    print(c("Đối phương gửi card:", CYAN))

    print_card(received_remote_card, "  ")

    confirm = input(
        "\nXác nhận giao dịch? [Y/N]: "
    ).strip().lower()

    if confirm != "y":
        send_packet(sock, {
            "type": "TRADE_ABORT",
            "message": "Người gửi hủy trade."
        })

        return

    # --------------------------------------------------------
    # Validate card của mình lần cuối
    # --------------------------------------------------------

    if not find_card(card_id):
        send_packet(sock, {
            "type": "TRADE_ABORT",
            "message": "Card của người gửi không còn tồn tại."
        })

        print(c(
            "Card của bạn đã không còn tồn tại.",
            RED
        ))
        return

    # --------------------------------------------------------
    # Commit
    # --------------------------------------------------------

    if not remove_card(card_id):
        send_packet(sock, {
            "type": "TRADE_ABORT",
            "message": "Không thể xóa card."
        })

        return

    try:
        new_card = add_card(received_remote_card)

    except Exception as e:
        print(c(
            f"Lỗi nhận card: {e}",
            RED
        ))

        return

    send_packet(sock, {
        "type": "TRADE_COMMIT",
        "trade_id": trade_id
    })

    final = receive_packet(sock)

    if final.get("type") == "TRADE_DONE":
        print()
        print(c("✓ TRADE THÀNH CÔNG!", GREEN))
        print("Bạn nhận được:")

        print_card(new_card, "  ")

    else:
        print(c(
            "Trade phía đối phương có vấn đề.",
            RED
        ))


# ============================================================
# RECEIVE CARD -> MONEY
# ============================================================

def receive_card_for_money(sock, offer):
    card = offer.get("card")
    amount = int(offer.get("money", 0))

    if not card:
        send_packet(sock, {
            "type": "TRADE_REJECT",
            "message": "Card không hợp lệ."
        })
        return

    if not validate_money(amount):
        send_packet(sock, {
            "type": "TRADE_REJECT",
            "message": "Số coin không hợp lệ."
        })
        return

    save = load_save()
    money = int(save.get("money", 0))

    print()
    print(c("================================", MAGENTA))
    print(c("        TRADE CARD → COINS       ", MAGENTA))
    print(c("================================", MAGENTA))

    print()
    print("Đối phương muốn gửi:")

    print_card(card, "  ")

    print()
    print(
        f"Bạn phải trả: "
        + c(f"{amount:,} coins", YELLOW)
    )

    print(
        f"Số dư hiện tại: "
        + c(f"{money:,} coins", GREEN)
    )

    if money < amount:
        print()
        print(c(
            "Bạn không đủ coin.",
            RED
        ))

        send_packet(sock, {
            "type": "TRADE_REJECT",
            "message": "Bạn không đủ coin."
        })

        return

    confirm = input(
        "\nChấp nhận giao dịch? [Y/N]: "
    ).strip().lower()

    if confirm != "y":
        send_packet(sock, {
            "type": "TRADE_REJECT",
            "message": "Đối phương từ chối."
        })

        return

    # --------------------------------------------------------
    # gửi ACCEPT
    # --------------------------------------------------------

    send_packet(sock, {
        "type": "TRADE_ACCEPT"
    })

    print()
    print("Đang chờ người gửi commit...")

    response = receive_packet(sock)

    if response.get("type") == "TRADE_ABORT":
        print(c(
            response.get("message", "Trade bị hủy."),
            YELLOW
        ))
        return

    if response.get("type") != "TRADE_COMMIT":
        print(c(
            "Trade commit không hợp lệ.",
            RED
        ))
        return

    # --------------------------------------------------------
    # Commit bên nhận
    # --------------------------------------------------------

    save = load_save()

    if int(save.get("money", 0)) < amount:
        send_packet(sock, {
            "type": "TRADE_ABORT",
            "message": "Coin đã không còn đủ."
        })
        return

    try:
        new_card = add_card(card)

    except Exception as e:
        send_packet(sock, {
            "type": "TRADE_ABORT",
            "message": f"Không thể lưu card: {e}"
        })

        return

    if not remove_money(amount):
        send_packet(sock, {
            "type": "TRADE_ABORT",
            "message": "Không thể trừ coin."
        })

        return

    send_packet(sock, {
        "type": "TRADE_DONE"
    })

    print()
    print(c("✓ TRADE THÀNH CÔNG!", GREEN))
    print(
        f"Đã trả {amount:,} coins và nhận:"
    )

    print_card(new_card, "  ")


# ============================================================
# RECEIVE CARD -> CARD
# ============================================================

def receive_card_for_card(sock, offer):
    offered_card = offer.get("card")

    if not offered_card:
        send_packet(sock, {
            "type": "TRADE_REJECT",
            "message": "Card không hợp lệ."
        })
        return

    collection = load_collection()

    if not collection:
        send_packet(sock, {
            "type": "TRADE_REJECT",
            "message": "Bạn không có card."
        })

        return

    print()
    print(c("================================", MAGENTA))
    print(c("         TRADE CARD ↔ CARD       ", MAGENTA))
    print(c("================================", MAGENTA))

    print()
    print(c("Đối phương muốn đưa:", CYAN))

    print_card(offered_card, "  ")

    print()
    print(c("=== CHỌN CARD CỦA BẠN ===", CYAN))

    for card in collection:
        print_card(card)

    print()

    try:
        card_id = int(
            input("ID card muốn đưa lại: ")
        )
    except ValueError:
        send_packet(sock, {
            "type": "TRADE_REJECT",
            "message": "ID card không hợp lệ."
        })
        return

    selected_card, error = validate_card(card_id)

    if error:
        print(c(error, RED))

        send_packet(sock, {
            "type": "TRADE_REJECT",
            "message": error
        })

        return

    print()
    print(c("Bạn chọn:", CYAN))
    print_card(selected_card, "  ")

    confirm = input(
        "\nChấp nhận giao dịch? [Y/N]: "
    ).strip().lower()

    if confirm != "y":
        send_packet(sock, {
            "type": "TRADE_REJECT",
            "message": "Đối phương từ chối."
        })

        return

    remote_selected_card = sanitize_card(selected_card)

    if not remote_selected_card:
        send_packet(sock, {
            "type": "TRADE_REJECT",
            "message": "Không thể đọc ảnh card."
        })

        return

    # --------------------------------------------------------
    # Gửi card mình chọn
    # --------------------------------------------------------

    send_packet(sock, {
        "type": "TRADE_ACCEPT",
        "card": remote_selected_card
    })

    print()
    print("Đang chờ người kia xác nhận...")

    response = receive_packet(sock)

    if response.get("type") == "TRADE_ABORT":
        print(c(
            response.get("message", "Trade bị hủy."),
            YELLOW
        ))
        return

    if response.get("type") != "TRADE_COMMIT":
        print(c(
            "Trade commit không hợp lệ.",
            RED
        ))
        return

    # --------------------------------------------------------
    # Commit
    # --------------------------------------------------------

    # Đảm bảo card của mình vẫn còn
    if not find_card(card_id):
        send_packet(sock, {
            "type": "TRADE_ABORT",
            "message": "Card của bạn đã không còn tồn tại."
        })

        return

    try:
        new_card = add_card(offered_card)

    except Exception as e:
        send_packet(sock, {
            "type": "TRADE_ABORT",
            "message": f"Không thể lưu card đối phương: {e}"
        })

        return

    if not remove_card(card_id):
        send_packet(sock, {
            "type": "TRADE_ABORT",
            "message": "Không thể xóa card."
        })

        return

    send_packet(sock, {
        "type": "TRADE_DONE"
    })

    print()
    print(c("✓ TRADE THÀNH CÔNG!", GREEN))
    print("Bạn nhận được:")

    print_card(new_card, "  ")


# ============================================================
# WAIT FOR TRADE
# ============================================================

def wait_for_trade(sock):
    print()
    print(c("Đang chờ đề nghị trade...", CYAN))
    print("Nhấn Ctrl+C để thoát.")

    while True:
        try:
            packet = receive_packet(sock)

        except KeyboardInterrupt:
            return

        except Exception as e:
            print()
            print(c(
                f"Mất kết nối: {e}",
                RED
            ))
            return

        packet_type = packet.get("type")

        if packet_type == "TRADE_OFFER":

            mode = packet.get("mode")

            if mode == "CARD_MONEY":
                receive_card_for_money(sock, packet)

            elif mode == "CARD_CARD":
                receive_card_for_card(sock, packet)

            else:
                send_packet(sock, {
                    "type": "TRADE_REJECT",
                    "message": "Loại trade không được hỗ trợ."
                })

            print()
            return

        elif packet_type == "PING":
            send_packet(sock, {
                "type": "PONG"
            })

        elif packet_type == "ERROR":
            print(c(
                packet.get("message", "Unknown error"),
                RED
            ))

            return


# ============================================================
# TRADE MENU
# ============================================================

def trade_menu(sock, role):
    while True:

        print()
        print(c("================================", CYAN))
        print(c("          DAILY WORDLE           ", CYAN))
        print(c("             TRADE               ", CYAN))
        print(c("================================", CYAN))

        save = load_save()

        print()
        print(
            "Coins:",
            c(f"{int(save.get('money', 0)):,}", YELLOW)
        )

        print()
        print("1. Card → Card")
        print("2. Card → Coins")
        print("3. Chờ người khác gửi trade")
        print("4. Xem collection")
        print("5. Ngắt kết nối")

        choice = input("\nChọn: ").strip()

        if choice == "1":
            send_card_for_card(sock)

        elif choice == "2":
            send_card_for_money(sock)

        elif choice == "3":
            wait_for_trade(sock)

        elif choice == "4":
            show_collection()

        elif choice == "5":
            try:
                send_packet(sock, {
                    "type": "GOODBYE"
                })
            except Exception:
                pass

            try:
                sock.close()
            except Exception:
                pass

            print()
            print("Đã ngắt kết nối.")
            return

        else:
            print(c(
                "Lựa chọn không hợp lệ.",
                RED
            ))


# ============================================================
# COLLECTION DISPLAY
# ============================================================

def show_collection():
    collection = load_collection()

    print()
    print(c("========== COLLECTION ==========", CYAN))

    if not collection:
        print("Collection trống.")
        return

    for card in collection:
        print_card(card)

    print()
    print(f"Tổng: {len(collection)} card")


# ============================================================
# HOST
# ============================================================

def create_room():
    print()
    print(c("================================", GREEN))
    print(c("          CREATE ROOM            ", GREEN))
    print(c("================================", GREEN))

    ips = print_radmin_ips()

    print()

    bind_ip = None

    if ips:
        bind_ip = ips[0]

        print(
            f"Đang dùng IP Radmin: "
            + c(bind_ip, GREEN)
        )

    else:
        bind_ip = input(
            "Nhập IP bind thủ công "
            "(Enter = 0.0.0.0): "
        ).strip()

        if not bind_ip:
            bind_ip = "0.0.0.0"

    try:
        port_input = input(
            f"Port [{DEFAULT_PORT}]: "
        ).strip()

        port = int(port_input) if port_input else DEFAULT_PORT

    except ValueError:
        print(c("Port không hợp lệ.", RED))
        return

    room_code = generate_room_code()

    server = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM
    )

    server.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1
    )

    try:
        server.bind((bind_ip, port))
        server.listen(1)

    except Exception as e:
        print()
        print(c(
            f"Không thể mở phòng: {e}",
            RED
        ))

        try:
            server.close()
        except Exception:
            pass

        return

    print()
    print(c("================================", GREEN))
    print(c("       PHÒNG ĐÃ ĐƯỢC TẠO        ", GREEN))
    print(c("================================", GREEN))

    if bind_ip == "0.0.0.0":
        if ips:
            print(
                "IP cho người khác:"
            )

            for ip in ips:
                print(
                    "  → "
                    + c(ip, GREEN)
                )
        else:
            print(
                "Hãy dùng IP Radmin của bạn."
            )

    else:
        print(
            "IP:"
            + c(f" {bind_ip}", GREEN)
        )

    print(
        "Port:"
        + c(f" {port}", GREEN)
    )

    print(
        "Room code:"
        + c(f" {room_code}", MAGENTA)
    )

    print()
    print("Đang chờ người chơi kết nối...")
    print()

    try:
        conn, address = server.accept()

    except KeyboardInterrupt:
        print()
        print("Đã hủy.")

        server.close()
        return

    except Exception as e:
        print(c(
            f"Lỗi kết nối: {e}",
            RED
        ))

        server.close()
        return

    finally:
        try:
            server.close()
        except Exception:
            pass

    print()
    print(
        "Đã nhận kết nối từ:",
        c(str(address), CYAN)
    )

    try:
        accept_handshake(
            conn,
            room_code
        )

    except Exception as e:
        print(c(
            f"Handshake thất bại: {e}",
            RED
        ))

        try:
            conn.close()
        except Exception:
            pass

        return

    print()
    print(c(
        "✓ Người chơi đã vào phòng!",
        GREEN
    ))

    trade_menu(conn, "host")


# ============================================================
# JOIN ROOM
# ============================================================

def join_room():
    print()
    print(c("================================", CYAN))
    print(c("           JOIN ROOM             ", CYAN))
    print(c("================================", CYAN))

    host_ip = input(
        "Nhập IP Radmin của host: "
    ).strip()

    if not host_ip:
        print(c("IP không được để trống.", RED))
        return

    try:
        port_input = input(
            f"Port [{DEFAULT_PORT}]: "
        ).strip()

        port = int(port_input) if port_input else DEFAULT_PORT

    except ValueError:
        print(c("Port không hợp lệ.", RED))
        return

    room_code = input(
        "Room code: "
    ).strip()

    if not room_code:
        print(c(
            "Room code không được để trống.",
            RED
        ))
        return

    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM
    )

    sock.settimeout(15)

    print()
    print("Đang kết nối...")

    try:
        sock.connect((host_ip, port))

    except Exception as e:
        print()
        print(c(
            f"Không thể kết nối: {e}",
            RED
        ))

        sock.close()
        return

    finally:
        sock.settimeout(None)

    try:
        handshake(
            sock,
            room_code
        )

    except Exception as e:
        print()
        print(c(
            f"Handshake thất bại: {e}",
            RED
        ))

        sock.close()
        return

    print()
    print(c(
        "✓ Kết nối thành công!",
        GREEN
    ))

    trade_menu(sock, "client")


# ============================================================
# MAIN MENU
# ============================================================

def main():
    os.system("")

    while True:
        print()
        print(c("================================", MAGENTA))
        print(c("          DAILY WORDLE           ", MAGENTA))
        print(c("             TRADE               ", MAGENTA))
        print(c("================================", MAGENTA))

        print()
        print("1. Tạo phòng")
        print("2. Vào phòng")
        print("3. Thoát")

        choice = input("\nChọn: ").strip()

        if choice == "1":
            create_room()

        elif choice == "2":
            join_room()

        elif choice == "3":
            print("Bye.")
            break

        else:
            print(c(
                "Lựa chọn không hợp lệ.",
                RED
            ))


if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        print()
        print("Đã thoát.")