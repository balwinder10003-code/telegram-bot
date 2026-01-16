import os
import json
import logging
import random
import string
import io
import time
from datetime import datetime

from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

import qrcode
from PIL import Image

import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ================= SECURE CONFIG =================

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_CHAT_ID = int(os.environ["ADMIN_CHAT_ID"])

UPI_ID = os.environ["UPI_ID"]
UPI_NAME = os.environ["UPI_NAME"]

SUPPORT_LINK = os.environ["SUPPORT_LINK"]
SHEET_NAME = os.environ.get("SHEET_NAME", "ATTRAH_ORDERS")
logging.basicConfig(level=logging.INFO)

ORDERS = {}
DISPATCH_INPUT = {}

PRICES = {
    "Dubai Mafia": {"3ml": 399, "6ml": 649, "8ml": 849, "12ml": 1199},
    "Pine Desire": {"3ml": 329, "6ml": 499, "8ml": 699, "12ml": 999},
    "Edible Musk": {"3ml": 319, "6ml": 499, "8ml": 699, "12ml": 999},
    "Skin Obsessed": {"3ml": 299, "6ml": 399, "8ml": 599, "12ml": 899},
    "Coco Crave": {"3ml": 299, "6ml": 399, "8ml": 599, "12ml": 899}
}

# ================= GOOGLE SHEETS =================

    def init_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]

    creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS_JSON"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)

    client = gspread.authorize(creds)
    return client.open(SHEET_NAME).sheet1
    

SHEET = init_sheet()

def get_column_map():
    headers = SHEET.row_values(1)
    return {h.strip(): i + 1 for i, h in enumerate(headers)}

def sheet_append(order):
    col = get_column_map()
    row = [""] * len(col)

    def set_col(name, value):
        if name in col:
            row[col[name] - 1] = value

    set_col("Order ID", order.get("order_id", ""))
    set_col("Customer Name", order.get("name", ""))
    set_col("Mobile Number", order.get("mobile", ""))
    set_col("Product", order.get("product", ""))
    set_col("Size", order.get("size", ""))
    set_col("Pcs", order.get("pcs", ""))
    set_col("Amount", order.get("amount", ""))
    set_col("Full Address", order.get("address", ""))
    set_col("Payment Status", order.get("status", ""))
    set_col("Payment Time", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    set_col("Tracking ID", order.get("tracking_id", ""))
    set_col("Tracking Link", order.get("tracking_url", ""))
    set_col("Dispatch Status", order.get("Dispatch_Status", ""))

    SHEET.append_row(row)
def sheet_update(order_id, status, tracking_id="", tracking_url=""):
    col = get_column_map()
    records = SHEET.get_all_records()

    for i, r in enumerate(records, start=2):
        if r.get("Order ID") == order_id:
            if "Payment Status" in col:
                SHEET.update_cell(i, col["Payment Status"], status)
            if "Payment Time" in col:
                SHEET.update_cell(
                    i,	
                    col["Payment Time"],
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
            if tracking_id and "Tracking ID" in col:
                SHEET.update_cell(i, col["Tracking ID"], tracking_id)
            if tracking_url and "Tracking Link" in col:
                SHEET.update_cell(i, col["Tracking Link"], tracking_url)
            if "Dispatch Status" in col:
                SHEET.update_cell(i, col["Dispatch Status"], status)
            break
# ================= HELPERS =================
def generate_order_id():
    while True:
        oid = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
        if oid not in ORDERS:
            return oid

def main_menu():
    return ReplyKeyboardMarkup(
        [
            ["🛒 Place Order", "📦 Active Order"],
            ["🧾 Order Summary", "📍 Delivery Status"],
            ["💰 Payment Status", "📞 Contact Support"]
        ],
        resize_keyboard=True
    )

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to ATTRAH\n\n"
        "We specialize in premium attars crafted with care and long-lasting elegance.\n\n"
        "You can place orders, complete secure payments, and track delivery updates directly from this bot.\n\n"
        "Please use the menu below to continue.",
        reply_markup=main_menu()
    )

# ================= ORDER FLOW =================
async def place_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("👤 Please enter your Full Name:")

async def name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "name" in context.user_data:
        return
    context.user_data["name"] = update.message.text
    buttons = [[KeyboardButton(p)] for p in PRICES]
    await update.message.reply_text(
        "🧴 Select the fragrance you wish to order:",
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    )

async def product_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "name" not in context.user_data or "product" in context.user_data:
        return
    context.user_data["product"] = update.message.text
    await update.message.reply_text("🔢 Enter Pcs. (number of pieces you want to order):")

async def pcs_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "product" not in context.user_data or "pcs" in context.user_data:
        return
    if not update.message.text.isdigit():
        return
    context.user_data["pcs"] = int(update.message.text)
    buttons = [[KeyboardButton(s)] for s in PRICES[context.user_data["product"]]]
    await update.message.reply_text(
        "📦 Select size:",
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    )

async def size_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "pcs" not in context.user_data or "size" in context.user_data:
        return
    context.user_data["size"] = update.message.text
    await update.message.reply_text(
        "🏠 Please enter your full delivery address in the Same Format:\n\n"
        "👤 Full Name:--\n"
        "📞 Mobile Number (WhatsApp preferred):--\n\n"
        "🏠 House / Flat / Building No:--\n"
        "🛣️ Street / Area / Locality:--\n"
        "🏘️ Landmark (Optional):--\n\n"
        "🏙️ City / Town:--\n"
        "🏘️ District:--\n"
        "🗺️ State:--\n"
        "📮 Pincode:--"
    )

async def address_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "size" not in context.user_data:
        return

    oid = generate_order_id()
    product = context.user_data["product"]
    size = context.user_data["size"]
    pcs = context.user_data["pcs"]
    amount = PRICES[product][size] * pcs

    ORDERS[oid] = {
        "order_id": oid,
        "user_id": update.effective_user.id,
        "name": context.user_data["name"],
        "product": product,
        "size": size,
        "pcs": pcs,
        "amount": amount,
        "address": update.message.text,
        "status": "Payment Pending"
    }

    sheet_append(ORDERS[oid])

    upi_data = f"upi://pay?pa=yourupi@bank&pn=ATTRAH&am={amount}&tn=Order {oid}"
    qr = qrcode.make(upi_data)
    bio = io.BytesIO()
    qr.save(bio, format="PNG")
    bio.seek(0)

    await update.message.reply_photo(
        photo=bio,
        caption=(
            f"🧾 Order ID: {oid}\n"
            f"🧴 Product: {product}\n"
            f"📦 Size: {size}\n"
            f"🔢 Pcs: {pcs}\n"
            f"💰 Total Amount: ₹{amount}\n\n"
            "Please complete the payment using the QR above.\n\n"
            "⚠️ Important:\n"
            "The payment note already contains your Order ID.\n"
            "Do NOT change or remove it while paying."
        ),
        reply_markup=main_menu()
    )

    context.user_data["awaiting_screenshot"] = oid

# ================= SCREENSHOT =================
async def screenshot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "awaiting_screenshot" not in context.user_data:
        return

    oid = context.user_data["awaiting_screenshot"]
    order = ORDERS[oid]

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve Payment", callback_data=f"approve_{oid}"),
            InlineKeyboardButton("❌ Reject Payment", callback_data=f"reject_{oid}")
        ]
    ])

    await context.bot.send_photo(
        chat_id=ADMIN_CHAT_ID,
        photo=update.message.photo[-1].file_id,
        caption=(
            "🔔 Payment Verification Request\n\n"
            f"🆔 Order ID: {oid}\n"
            f"👤 Customer: {order['name']}\n"
            f"🧴 Product: {order['product']}\n"
            f"📦 Size: {order['size']}\n"
            f"🔢 Pcs: {order['pcs']}\n"
            f"💰 Amount: ₹{order['amount']}\n\n"
            f"🏠 Address:\n{order['address']}"
        ),
        reply_markup=buttons
    )

# ================= ADMIN ACTIONS =================
async def admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action, oid = query.data.split("_")
    order = ORDERS[oid]
    user_id = order["user_id"]

    if action == "approve":
        order["status"] = "Payment Verified"
        sheet_update(oid, "Payment Verified")

        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "✅ Payment Verified Successfully\n\n"
                "Thank you for your payment!\n"
                "Your transaction has been verified successfully.\n\n"
                f"🧾 Order ID: {oid}\n\n"
                "Your order is now being prepared for dispatch.\n"
                "📦 Tracking details will be shared with you shortly once dispatched.\n\n"
                "We truly appreciate your trust in ATTRAH 🌸"
            ),
            reply_markup=main_menu()
        )

        await query.edit_message_caption(
            caption=f"✅ Payment approved for Order ID {oid}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚚 Enter Dispatch Details", callback_data=f"dispatch_{oid}")]
            ])
        )

    elif action == "reject":
        order["status"] = "Payment Rejected"
        sheet_update(oid, "Payment Rejected")

        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "⚠️ Payment Verification Issue\n\n"
                "We were unable to verify the payment for your order.\n\n"
                "This may be due to:\n"
                "• Amount mismatch\n"
                "• Unclear screenshot\n"
                "• Missing Order ID in payment note\n\n"
                f"🧾 Order ID: {oid}\n\n"
                "Please re-upload a clear payment screenshot or make the payment again using the same QR.\n\n"
                "If you need assistance, our support team is here to help."
            ),
            reply_markup=main_menu()
        )

        await query.edit_message_caption(
            caption=f"❌ Payment rejected for Order ID {oid}"
        )

# ================= DISPATCH =================
async def dispatch_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, oid = query.data.split("_")
    DISPATCH_INPUT[query.from_user.id] = {"order_id": oid}

    await context.bot.send_message(
        chat_id=query.from_user.id,
        text=(
            "🚚 *Enter Dispatch Details*\n\n"
            "Courier Name:\n"
            "Tracking ID:\n"
            "Tracking URL:"
        ),
        parse_mode=None
    )

async def dispatch_details_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.effective_user.id
    if admin_id not in DISPATCH_INPUT:
        return

    lines = update.message.text.strip().split("\n")
    if len(lines) < 3:
        return

    oid = DISPATCH_INPUT[admin_id]["order_id"]
    order = ORDERS[oid]

    courier = lines[0]
    tracking_id = lines[1]
    tracking_url = lines[2]

    order["status"] = "Dispatched"
    order["tracking_id"] = tracking_id
    order["tracking_url"] = tracking_url

    sheet_update(oid, "Dispatched", tracking_id, tracking_url)

    await context.bot.send_message(
        chat_id=order["user_id"],
        text=(
            "🚚 Order Dispatched Successfully!\n\n"
            "Your order has been shipped.\n\n"
            f"🧾 Order ID: {oid}\n"
            f"📦 Courier: {courier}\n"
            f"🔢 Tracking ID: {tracking_id}\n"
            f"🌐 Track here: {tracking_url}\n\n"
            "Thank you for shopping with ATTRAH 🌸"
        )
    )

    DISPATCH_INPUT.pop(admin_id, None)

# ================= SUPPORT =================
async def contact_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤝 We’re Here to Help You\n\n"
        "For any questions, payment concerns, or order-related assistance,\n"
        "our dedicated support team is available to help you personally.\n\n"
        f"👉 Tap below to chat directly with our support team:\n{SUPPORT_LINK}",
        reply_markup=main_menu()
    )

# ================= MAIN =================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("^🛒 Place Order$"), place_order))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, name_handler))
    app.add_handler(MessageHandler(filters.TEXT, product_handler))
    app.add_handler(MessageHandler(filters.TEXT, pcs_handler))
    app.add_handler(MessageHandler(filters.TEXT, size_handler))
    app.add_handler(MessageHandler(filters.TEXT, address_handler))
    app.add_handler(MessageHandler(filters.PHOTO, screenshot_handler))
    app.add_handler(CallbackQueryHandler(dispatch_start, pattern="^dispatch_"))
    app.add_handler(CallbackQueryHandler(admin_action, pattern="^(approve|reject)_"))
    app.add_handler(MessageHandler(filters.TEXT & filters.Chat(ADMIN_CHAT_ID), dispatch_details_handler))
    app.add_handler(MessageHandler(filters.Regex("^📞 Contact Support$"), contact_support))

    app.run_polling()

if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as e:
            print("🔥 BOT CRASHED:", e)
            time.sleep(5)

