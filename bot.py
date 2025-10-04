import json
import datetime
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# === CONFIG ===
TOKEN = "8330563514:AAEQ0MqyizMjoPtH0cFgC-gyMOOURGiRDVo"  # Inserisci il tuo token
ADMIN_ID = 234535212  # Inserisci il tuo ID Telegram
CATALOG_FILE = "catalog.json"
ORDERS_FILE = "orders.json"

# Debug mode: se True ignora il controllo sugli orari
DEBUG_MODE = True  
BLACKLIST = ["hitler", "mussolini", "stalin", "succhiapalle", "bocchinaro", "puttanone", "zoccol", "puttan", "ricchione", "frocio", "culattone"]
MAX_QTY_PER_BOOK = 10  # Limite massimo per libro

# === FUNZIONI UTILI ===
def load_catalog():
    try:
        with open(CATALOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_catalog(catalog):
    with open(CATALOG_FILE, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=4, ensure_ascii=False)

def load_orders():
    try:
        with open(ORDERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"counter": 0, "data": {}}

def save_orders(orders):
    with open(ORDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(orders, f, indent=4, ensure_ascii=False)

def generate_order_id():
    orders = load_orders()
    orders["counter"] += 1
    save_orders(orders)
    return f"ORD-{orders['counter']:04d}"

def is_within_order_time():
    if DEBUG_MODE:
        return True
    now = datetime.datetime.now()
    weekday = now.weekday()
    hour = now.hour
    minute = now.minute
    if weekday in range(0, 5):
        return 9 <= hour < 20 or (hour == 20 and minute == 0)
    elif weekday == 5:
        return 9 <= hour < 12 or (hour == 12 and minute == 0)
    return False

def get_pickup_date():
    today = datetime.datetime.now()
    weekday = today.weekday()
    if weekday <= 2:  # Lun-Mer
        days_to_monday = (7 - weekday) % 7
        pickup = today + datetime.timedelta(days=days_to_monday)
    else:  # Gio-Sab
        days_to_wed = (9 - weekday) % 7
        pickup = today + datetime.timedelta(days=days_to_wed)
    return pickup.strftime("%d/%m/%Y")

def is_valid_italian_phone(number):
    return re.fullmatch(r"(3\d{8,9}|0\d{9,10})", number)

def is_clean_text(text):
    return not any(word.lower() in text.lower() for word in BLACKLIST)

# === HANDLERS UTENTE ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Benvenuto nel bot di Armonia! Qui potrai ordinare i tuoi libri di test. Usa /catalogo per vedere i libri disponibili. Usa /listacomandi per vedere tutti i comandi disponibili!")

async def catalogo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_within_order_time():
        await update.message.reply_text(
            "⏰ Gli ordini sono possibili:\n- Lun-Ven 09:00–20:00\n- Sab 09:00–12:00"
        )
        return
    catalog = load_catalog()
    if not catalog:
        await update.message.reply_text("📚 Nessun libro disponibile al momento.")
        return
    keyboard = [[InlineKeyboardButton(f"{book} - €{price}", callback_data=f"order|{book}")]
                for book, price in catalog.items()]
    keyboard.append([InlineKeyboardButton("🛒 Vai al carrello", callback_data="cart")])
    await update.message.reply_text(
        "Seleziona un libro da ordinare:", reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("|")

    if data[0] == "order":
        book = data[1]
        context.user_data["current_book"] = book
        context.user_data["awaiting_quantity"] = True
        await query.edit_message_text(f"Hai scelto: {book}\n📌 Invia la quantità desiderata:")

    elif data[0] == "cart":
        order = context.user_data.get("cart", {})
        if not order:
            await query.edit_message_text("🛒 Il tuo carrello è vuoto.")
            return
        catalog = load_catalog()
        total = sum(catalog[b]*q for b, q in order.items())
        summary = "\n".join([f"{b} x {q} = €{catalog[b]*q}" for b, q in order.items()])
        await query.edit_message_text(
            f"📖 Riepilogo ordine:\n{summary}\n\nTotale = €{total}\n\nRitiro previsto: {get_pickup_date()}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Conferma", callback_data="confirm")],
                [InlineKeyboardButton("✏️ Modifica", callback_data="modify")],
                [InlineKeyboardButton("❌ Annulla", callback_data="cancel")]
            ])
        )

    elif data[0] in ["confirm", "modify", "cancel"]:
        await manage_order(query, context, data[0])

async def quantity_or_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    # Gestione quantità
    if context.user_data.get("awaiting_quantity"):
        try:
            qty = int(text)
            if qty <= 0:
                await update.message.reply_text("❌ Inserisci un numero maggiore di 0.")
                return
        except:
            await update.message.reply_text("❌ Inserisci un numero valido.")
            return

        if qty > MAX_QTY_PER_BOOK:
            await update.message.reply_text(f"❌ Puoi ordinare al massimo {MAX_QTY_PER_BOOK} copie per libro.")
            return

        book = context.user_data["current_book"]
        cart = context.user_data.get("cart", {})
        cart[book] = cart.get(book, 0) + qty
        context.user_data["cart"] = cart
        context.user_data.pop("current_book")
        context.user_data.pop("awaiting_quantity")
        await update.message.reply_text(
            f"✅ Aggiunto {qty} x {book} al carrello.\nUsa /catalogo per aggiungere altro o vai al carrello."
        )
        return

    # Gestione dati personali
    if context.user_data.get("awaiting_data"):
        step = context.user_data["awaiting_data"]
        if not is_clean_text(text):
            await update.message.reply_text("❌ Testo non consentito. Inserisci un altro valore.")
            return
        if step == "name":
            context.user_data["name"] = text
            context.user_data["awaiting_data"] = "surname"
            await update.message.reply_text("Inserisci il tuo *Cognome*:", parse_mode="Markdown")
        elif step == "surname":
            context.user_data["surname"] = text
            context.user_data["awaiting_data"] = "phone"
            await update.message.reply_text("📱 Inserisci il tuo *Numero di cellulare*:", parse_mode="Markdown")
        elif step == "phone":
            if not is_valid_italian_phone(text):
                await update.message.reply_text("❌ Inserisci un numero italiano valido.")
                return
            context.user_data["phone"] = text
            context.user_data.pop("awaiting_data")
            cart = context.user_data.get("cart", {})
            catalog = load_catalog()
            total = sum(catalog[b]*q for b, q in cart.items())
            order_id = generate_order_id()
            pickup_date = get_pickup_date()
            order = {
                "id": order_id,
                "items": cart,
                "total": total,
                "confirmed": True,
                "pickup": pickup_date,
                "name": context.user_data["name"],
                "surname": context.user_data["surname"],
                "phone": context.user_data["phone"]
            }
            orders = load_orders()
            orders["data"][str(update.message.from_user.id)] = order
            save_orders(orders)
            # Notifica admin
            await context.bot.send_message(
                ADMIN_ID,
                f"📦 Nuovo ordine {order['id']} da {order['name']} {order['surname']} 📱 {order['phone']}\n"
                f"Utente: @{update.message.from_user.username or update.message.from_user.first_name}\n"
                f"Libri: {order['items']}\nTotale: €{order['total']}\nRitiro: {order['pickup']}"
            )
            await update.message.reply_text(
                f"✅ Ordine confermato!\nNumero ordine: *{order_id}*\nNon può più essere annullato.\n📍 Ritiro il {pickup_date}.",
                parse_mode="Markdown"
            )
            context.user_data.pop("cart", None)

# Comando per mostrare tutti i comandi disponibili
async def listacomandi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    is_admin = (user_id == ADMIN_ID)

    comandi_utente = """
📚 Comandi Utente:
/start - Inizia a usare il bot
/catalogo - Mostra il catalogo dei libri
/mieiordini - Mostra i tuoi ordini confermati
/listacomandi - Mostra questo elenco di comandi
"""
    comandi_admin = """
🛠 Comandi Admin:
/aggiungi titolo prezzo - Aggiunge un libro al catalogo
/rimuovi titolo - Rimuove un libro dal catalogo
/listalibri - Mostra il catalogo completo
/ordini - Mostra tutti gli ordini confermati
/eliminaordine ORD-XXXX - Elimina un ordine specifico
/listacomandi - Mostra questo elenco di comandi
"""

    if is_admin:
        await update.message.reply_text(comandi_admin)
    else:
        await update.message.reply_text(comandi_utente)

# Comando per vedere i propri ordini
async def mieiordini(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    orders = load_orders()["data"]
    if user_id not in orders:
        await update.message.reply_text("❌ Non hai ancora ordini confermati.")
        return
    order = orders[user_id]
    summary = "\n".join([f"{b} x {q} = €{q*load_catalog()[b]}" for b,q in order["items"].items()])
    await update.message.reply_text(
        f"📦 I tuoi ordini:\nID: {order['id']}\nLibri:\n{summary}\nTotale: €{order['total']}\nRitiro: {order['pickup']}"
    )

# === HANDLERS ADMIN ===
async def aggiungi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    if len(context.args) < 2:
        await update.message.reply_text("Uso: /aggiungi titolo prezzo")
        return
    titolo = " ".join(context.args[:-1])
    prezzo = float(context.args[-1])
    catalog = load_catalog()
    catalog[titolo] = prezzo
    save_catalog(catalog)
    await update.message.reply_text(f"✅ Aggiunto {titolo} a €{prezzo}")

async def rimuovi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    titolo = " ".join(context.args)
    catalog = load_catalog()
    if titolo in catalog:
        del catalog[titolo]
        save_catalog(catalog)
        await update.message.reply_text(f"❌ Rimosso {titolo}")
    else:
        await update.message.reply_text("Libro non trovato.")

async def listalibri(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    catalog = load_catalog()
    if not catalog:
        await update.message.reply_text("📚 Catalogo vuoto.")
        return
    msg = "\n".join([f"{t} - €{p}" for t, p in catalog.items()])
    await update.message.reply_text(f"Catalogo:\n{msg}")

# Comando admin per vedere tutti gli ordini
async def ordini(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    orders = load_orders()["data"]
    if not orders:
        await update.message.reply_text("📦 Nessun ordine al momento.")
        return
    msg = ""
    for o in orders.values():
        items = "\n".join([f"{b} x {q}" for b,q in o["items"].items()])
        msg += f"ID: {o['id']}\nNome: {o['name']} {o['surname']}\nTelefono: {o['phone']}\nLibri:\n{items}\nTotale: €{o['total']}\nRitiro: {o['pickup']}\n\n"
    await update.message.reply_text(msg)

# Comando admin per eliminare ordini
async def eliminaordine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Uso: /eliminaordine ORD-XXXX")
        return
    order_id = context.args[0]
    orders = load_orders()
    found = False
    for user_id, data in list(orders["data"].items()):
        if data["id"] == order_id:
            del orders["data"][user_id]
            save_orders(orders)
            found = True
            await update.message.reply_text(f"✅ Ordine {order_id} eliminato.")
            break
    if not found:
        await update.message.reply_text("❌ Ordine non trovato.")

# === FUNZIONE GESTIONE ORDINE ===
async def manage_order(query, context, action):
    if action == "confirm":
        context.user_data["awaiting_data"] = "name"
        await query.edit_message_text("✍️ Inserisci il tuo *Nome*:", parse_mode="Markdown")
    elif action == "modify":
        await query.edit_message_text("✏️ Usa /catalogo per modificare il tuo ordine.")
    elif action == "cancel":
        context.user_data.pop("cart", None)
        await query.edit_message_text("❌ Ordine annullato.")

# === MAIN ===
def main():
    app = Application.builder().token(TOKEN).build()

    # Comandi generici
    app.add_handler(CommandHandler("listacomandi", listacomandi))

    # Comandi utente
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("catalogo", catalogo))
    app.add_handler(CommandHandler("mieiordini", mieiordini))

    # Comandi admin
    app.add_handler(CommandHandler("aggiungi", aggiungi))
    app.add_handler(CommandHandler("rimuovi", rimuovi))
    app.add_handler(CommandHandler("listalibri", listalibri))
    app.add_handler(CommandHandler("ordini", ordini))
    app.add_handler(CommandHandler("eliminaordine", eliminaordine))

    # Gestione bottoni e messaggi
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, quantity_or_data))

    app.run_polling()

if __name__ == "__main__":
    main()