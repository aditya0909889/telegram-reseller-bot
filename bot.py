import os
import logging
import requests
import sqlite3

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

# ==============================
# CONFIGURATION
# ==============================

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
SHOP_ID = os.getenv("SHOP_ID", "")
API_KEY = os.getenv("API_KEY", "")

API_BASE = os.getenv(
    "API_BASE",
    "https://lahastore.up.railway.app/api/v1"
).rstrip("/")

ADMIN_IDS = {
    int(x)
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ==============================
# DATABASE
# ==============================

def init_db():
    with sqlite3.connect("shop.db") as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                product_id TEXT,
                product_name TEXT,
                status TEXT DEFAULT 'pending'
            )
        """)


# ==============================
# API CONNECTION
# ==============================

def api_get(endpoint, params=None):
    headers = {
        "X-API-Key": API_KEY
    }

    response = requests.get(
        f"{API_BASE}{endpoint}",
        headers=headers,
        params=params,
        timeout=20
    )

    response.raise_for_status()
    return response.json()


# ==============================
# MAIN MENU
# ==============================

def main_menu():
    keyboard = [
        [
            InlineKeyboardButton(
                "🛍️ Shop Products",
                callback_data="products"
            )
        ],
        [
            InlineKeyboardButton(
                "💰 API Balance",
                callback_data="balance"
            ),
            InlineKeyboardButton(
                "📦 My Orders",
                callback_data="orders"
            )
        ],
        [
            InlineKeyboardButton(
                "👤 My Profile",
                callback_data="profile"
            )
        ],
        [
            InlineKeyboardButton(
                "📞 Support",
                callback_data="support"
            )
        ]
    ]

    return InlineKeyboardMarkup(keyboard)


# ==============================
# START COMMAND
# ==============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    await update.message.reply_text(
        f"👋 Welcome {user.first_name}!\n\n"
        "🛍️ Welcome to our Digital Shop.\n\n"
        "Choose an option below:",
        reply_markup=main_menu()
    )


# ==============================
# SHOW PRODUCTS
# ==============================

async def show_products(query):
    data = api_get("/products", {
        "page": 1,
        "limit": 10
    })

    products = data.get("products", [])

    if not products:
        await query.edit_message_text(
            "❌ No products available.",
            reply_markup=main_menu()
        )
        return

    buttons = []
    text = "🛍️ AVAILABLE PRODUCTS\n\n"

    for product in products[:10]:
        product_id = product.get(
            "id",
            product.get("productId", product.get("code", ""))
        )

        name = product.get(
            "name",
            product.get("title", "Product")
        )

        price = product.get(
            "priceUsd",
            product.get("price", "N/A")
        )

        text += (
            f"📦 {name}\n"
            f"💵 Price: {price}\n\n"
        )

        if product_id:
            buttons.append([
                InlineKeyboardButton(
                    f"🛒 Request {str(name)[:30]}",
                    callback_data=f"buy:{product_id}"
                )
            ])

    buttons.append([
        InlineKeyboardButton(
            "🏠 Main Menu",
            callback_data="home"
        )
    ])

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# ==============================
# API BALANCE
# ==============================

async def show_balance(query):
    data = api_get("/balance")

    balance = data.get(
        "balanceUsd",
        data.get("balance", "Unavailable")
    )

    await query.edit_message_text(
        f"💰 SHOP API BALANCE\n\n"
        f"🆔 Shop ID: {SHOP_ID}\n"
        f"💵 Balance: {balance}\n\n"
        "Note: This is the supplier balance.",
        reply_markup=main_menu()
    )


# ==============================
# ORDERS
# ==============================

async def show_orders(query):
    if query.from_user.id not in ADMIN_IDS:
        await query.edit_message_text(
            "🔒 Order history is available to the shop admin only.",
            reply_markup=main_menu()
        )
        return

    data = api_get("/orders", {
        "limit": 10,
        "includeAccounts": 0
    })

    orders = data.get("orders", [])

    if not orders:
        text = "📦 No recent orders found."
    else:
        text = "📦 RECENT ORDERS\n\n"

        for order in orders[:10]:
            text += (
                f"Order: {order.get('orderCode', 'N/A')}\n"
                f"Product: {order.get('productName', 'N/A')}\n"
                f"Status: {order.get('status', 'Unknown')}\n\n"
            )

    await query.edit_message_text(
        text,
        reply_markup=main_menu()
    )


# ==============================
# PURCHASE REQUEST
# ==============================

async def create_request(query, context, product_id):
    user = query.from_user

    try:
        data = api_get("/products")
        products = data.get("products", [])

        product = next(
            (
                p for p in products
                if str(p.get("id", p.get("productId", p.get("code", ""))))
                == str(product_id)
            ),
            None
        )

        if not product:
            await query.edit_message_text(
                "❌ Product not found. Please reopen the shop.",
                reply_markup=main_menu()
            )
            return

        name = product.get(
            "name",
            product.get("title", "Product")
        )

        with sqlite3.connect("shop.db") as db:
            cursor = db.execute(
                """
                INSERT INTO requests
                (user_id, username, product_id, product_name)
                VALUES (?, ?, ?, ?)
                """,
                (
                    user.id,
                    user.username or "",
                    str(product_id),
                    str(name)
                )
            )
            request_id = cursor.lastrowid

        await query.edit_message_text(
            f"✅ Purchase request submitted!\n\n"
            f"📦 Product: {name}\n"
            f"🧾 Request ID: {request_id}\n\n"
            "Your request is waiting for admin confirmation. "
            "No payment has been taken.",
            reply_markup=main_menu()
        )

        for admin_id in ADMIN_IDS:
            await context.bot.send_message(
                chat_id=admin_id,
                text=(
                    "🛒 NEW PURCHASE REQUEST\n\n"
                    f"Request ID: {request_id}\n"
                    f"User: {user.full_name}\n"
                    f"User ID: {user.id}\n"
                    f"Product: {name}\n"
                    f"Product ID: {product_id}"
                )
            )

    except Exception:
        logger.exception("Purchase request failed")
        await query.edit_message_text(
            "❌ Could not submit the request. Please try again later.",
            reply_markup=main_menu()
        )


# ==============================
# BUTTON HANDLER
# ==============================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action = query.data

    try:
        if action == "home":
            await query.edit_message_text(
                "🏠 Welcome to Digital Shop!",
                reply_markup=main_menu()
            )

        elif action == "products":
            await show_products(query)

        elif action == "balance":
            if query.from_user.id not in ADMIN_IDS:
                await query.edit_message_text(
                    "🔒 API balance is available to the shop admin only.",
                    reply_markup=main_menu()
                )
            else:
                await show_balance(query)

        elif action == "orders":
            await show_orders(query)

        elif action == "profile":
            user = query.from_user

            await query.edit_message_text(
                f"👤 MY PROFILE\n\n"
                f"Name: {user.full_name}\n"
                f"Telegram ID: {user.id}\n"
                f"Username: @{user.username or 'Not set'}",
                reply_markup=main_menu()
            )

        elif action == "support":
            await query.edit_message_text(
                "📞 Please contact the shop administrator for support.",
                reply_markup=main_menu()
            )

        elif action.startswith("buy:"):
            product_id = action.split(":", 1)[1]

            await create_request(
                query,
                context,
                product_id
            )

    except requests.RequestException:
        logger.exception("Supplier API request failed")

        await query.edit_message_text(
            "⚠️ Supplier API is unavailable. Please try again later.",
            reply_markup=main_menu()
        )

    except Exception:
        logger.exception("Button handler failed")

        await query.edit_message_text(
            "⚠️ Something went wrong. Please try again.",
            reply_markup=main_menu()
        )


# ==============================
# ADMIN COMMAND
# ==============================

async def admin_requests(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Admin only.")
        return

    with sqlite3.connect("shop.db") as db:
        rows = db.execute(
            """
            SELECT id, user_id, product_name, status
            FROM requests
            ORDER BY id DESC
            LIMIT 20
            """
        ).fetchall()

    if not rows:
        await update.message.reply_text("No purchase requests yet.")
        return

    text = "🧾 RECENT REQUESTS\n\n"

    for row in rows:
        text += (
            f"ID: {row[0]}\n"
            f"User ID: {row[1]}\n"
            f"Product: {row[2]}\n"
            f"Status: {row[3]}\n\n"
        )

    await update.message.reply_text(text)


# ==============================
# RUN BOT
# ==============================

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN variable is missing.")

    if not API_KEY:
        raise RuntimeError("API_KEY variable is missing.")

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("requests", admin_requests))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("Telegram Reseller Shop Bot is starting...")

    app.run_polling()


if __name__ == "__main__":
    main()
