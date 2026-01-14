const fs = require("fs");

const path = require("path");

const chalk = require("chalk");

const { Telegraf, Markup, session } = require("telegraf");

const config = require("./config");

const bot = new Telegraf(config.BOT_TOKEN);

// ====== Storage Orders (JSON file) ======

const DB_PATH = path.join(__dirname, "orders.json");

function readDB() {

  if (!fs.existsSync(DB_PATH)) fs.writeFileSync(DB_PATH, JSON.stringify({ orders: [] }, null, 2));

  return JSON.parse(fs.readFileSync(DB_PATH, "utf-8"));

}

function writeDB(db) {

  fs.writeFileSync(DB_PATH, JSON.stringify(db, null, 2));

}

function newOrderId() {

  // contoh: ORD-20260102-AB12

  const d = new Date();

  const y = d.getFullYear();

  const m = String(d.getMonth() + 1).padStart(2, "0");

  const da = String(d.getDate()).padStart(2, "0");

  const rand = Math.random().toString(36).slice(2, 6).toUpperCase();

  return `ORD-${y}${m}${da}-${rand}`;

}

function formatRupiah(n) {

  return new Intl.NumberFormat("id-ID", { style: "currency", currency: "IDR" }).format(n);

}

function isAdmin(ctx) {

  return config.ADMIN_IDS.includes(ctx.from?.id);

}

function productKeyboard() {

  const rows = config.PRODUCTS.map(p => ([

    Markup.button.callback(`${p.name} • ${formatRupiah(p.price)}`, `buy:${p.id}`)

  ]));

  rows.push([Markup.button.callback("📦 Cek Status Order", "check_status")]);

  return Markup.inlineKeyboard(rows);

}

function adminActionKeyboard(orderId) {

  return Markup.inlineKeyboard([

    [

      Markup.button.callback("✅ APPROVE", `admin:approve:${orderId}`),

      Markup.button.callback("❌ REJECT", `admin:reject:${orderId}`)

    ],

    [

      Markup.button.callback("💰 MARK PAID", `admin:paid:${orderId}`),

      Markup.button.callback("🚚 DELIVER", `admin:deliver:${orderId}`)

    ]

  ]);

}

// ====== Session for order flow ======

bot.use(session());

// ====== UI / Welcome ======

async function sendWelcome(ctx) {

  const senderName = ctx.from.first_name || "User";

  const waktuRunPanel = new Date().toLocaleString("id-ID", { timeZone: "Asia/Jakarta" });

  const text =

`📌 *${config.STORE_NAME}*

Halo *@${ctx.from.username || senderName}*!

🕒 ${waktuRunPanel}

Pilih produk di bawah untuk *auto order*.

Setelah order dibuat, kamu akan dapat *invoice* + instruksi pembayaran.`;

  return ctx.replyWithPhoto(

    { url: "https://files.catbox.moe/o0ebfp.jpg" },

    {

      caption: text,

      parse_mode: "Markdown",

      ...productKeyboard()

    }

  );

}

// ====== Commands ======

bot.start(async (ctx) => {

  ctx.session = {}; // reset

  await sendWelcome(ctx);

});

bot.command("catalog", async (ctx) => {

  ctx.session = {};

  await sendWelcome(ctx);

});

bot.command("cancel", async (ctx) => {

  ctx.session = {};

  await ctx.reply("❎ Order dibatalkan. Ketik /start untuk mulai lagi.");

});

bot.command("status", async (ctx) => {

  await ctx.reply("Kirim: /status ORD-YYYYMMDD-XXXX\nContoh: /status ORD-20260102-AB12");

});

bot.hears(/^\/status\s+(.+)/i, async (ctx) => {

  const orderId = ctx.match[1].trim();

  const db = readDB();

  const order = db.orders.find(o => o.id === orderId && o.userId === ctx.from.id);

  if (!order) return ctx.reply("❌ Order tidak ditemukan / bukan milik kamu.");

  const msg =

`📦 *Status Order*

• ID: \`${order.id}\`

• Produk: *${order.productName}*

• Harga: *${formatRupiah(order.price)}*

• Status: *${order.status}*

📌 Catatan: ${order.note || "-"}`;

  await ctx.reply(msg, { parse_mode: "Markdown" });

});

// ====== Inline Actions ======

bot.action("check_status", async (ctx) => {

  await ctx.answerCbQuery();

  await ctx.reply("Kirim: /status ORD-YYYYMMDD-XXXX\nContoh: /status ORD-20260102-AB12");

});

// User chooses product

bot.action(/^buy:(.+)$/i, async (ctx) => {

  await ctx.answerCbQuery();

  const productId = ctx.match[1];

  const product = config.PRODUCTS.find(p => p.id === productId);

  if (!product) return ctx.reply("❌ Produk tidak ditemukan.");

  ctx.session.order = {

    step: "ASK_EMAIL",

    productId: product.id,

    productName: product.name,

    price: product.price,

    duration: product.duration

  };

  await ctx.reply(

`🛒 Kamu pilih: *${product.name}*

Durasi: *${product.duration}*

Harga: *${formatRupiah(product.price)}*

📩 Kirim *email* yang akan dipakai (contoh: nama@gmail.com)`,

    { parse_mode: "Markdown" }

  );

});

// ====== Order Flow via text messages ======

bot.on("text", async (ctx) => {

  const s = ctx.session?.order;

  if (!s) return; // ignore if not in flow

  const text = ctx.message.text.trim();

  // Step: ask email

  if (s.step === "ASK_EMAIL") {

    const ok = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(text);

    if (!ok) return ctx.reply("❌ Format email tidak valid. Coba lagi (contoh: nama@gmail.com).");

    s.email = text;

    s.step = "ASK_WHATSAPP";

    return ctx.reply("📱 Kirim nomor WhatsApp (contoh: 08xxxxxxxxxx) untuk konfirmasi:");

  }

  // Step: ask whatsapp

  if (s.step === "ASK_WHATSAPP") {

    const digits = text.replace(/[^\d]/g, "");

    if (digits.length < 9) return ctx.reply("❌ Nomor WA kurang valid. Coba lagi (contoh: 08xxxxxxxxxx).");

    s.whatsapp = text;

    s.step = "ASK_PAYMENT";

    return ctx.reply(

      `💳 Pilih metode pembayaran:`,

      Markup.inlineKeyboard(

        config.PAYMENT_INFO.methods.map((m, idx) => [Markup.button.callback(m, `pay:${idx}`)])

      )

    );

  }

  // Step: waiting payment choice (ignore random texts)

  if (s.step === "ASK_PAYMENT") {

    return ctx.reply("Klik salah satu tombol metode pembayaran ya 🙂");

  }

  // Step: ask notes

  if (s.step === "ASK_NOTE") {

    s.note = text.slice(0, 200);

    s.step = "CONFIRM";

    const confirmText =

`🧾 *Konfirmasi Order*

• Produk: *${s.productName}* (${s.duration})

• Harga: *${formatRupiah(s.price)}*

• Email: \`${s.email}\`

• WhatsApp: \`${s.whatsapp}\`

• Bayar via: *${s.paymentMethod}*

• Catatan: ${s.note || "-"}

Lanjut buat invoice?`;

    return ctx.reply(confirmText, {

      parse_mode: "Markdown",

      ...Markup.inlineKeyboard([

        [Markup.button.callback("✅ BUAT INVOICE", "confirm_invoice")],

        [Markup.button.callback("❎ BATAL", "cancel_order")]

      ])

    });

  }

});

// Choose payment method

bot.action(/^pay:(\d+)$/i, async (ctx) => {

  await ctx.answerCbQuery();

  const s = ctx.session?.order;

  if (!s) return ctx.reply("Session order tidak ada. Ketik /start.");

  const idx = Number(ctx.match[1]);

  const method = config.PAYMENT_INFO.methods[idx];

  if (!method) return ctx.reply("❌ Metode tidak valid.");

  s.paymentMethod = method;

  s.step = "ASK_NOTE";

  await ctx.reply(

`📝 Tulis catatan (opsional).

Contoh: "Mau proses cepat" / "Aktifkan jam 8 malam"

Jika tidak ada, ketik: -`

  );

});

// Cancel in flow

bot.action("cancel_order", async (ctx) => {

  await ctx.answerCbQuery();

  ctx.session = {};

  await ctx.reply("❎ Order dibatalkan. Ketik /start untuk mulai lagi.");

});

// Confirm invoice -> create order, notify admin

bot.action("confirm_invoice", async (ctx) => {

  await ctx.answerCbQuery();

  const s = ctx.session?.order;

  if (!s || s.step !== "CONFIRM") return ctx.reply("❌ Tidak ada order yang bisa dikonfirmasi. Ketik /start.");

  const orderId = newOrderId();

  const createdAt = new Date().toISOString();

  const order = {

    id: orderId,

    createdAt,

    status: "PENDING",

    userId: ctx.from.id,

    username: ctx.from.username || null,

    name: ctx.from.first_name || "User",

    productId: s.productId,

    productName: s.productName,

    duration: s.duration,

    price: s.price,

    email: s.email,

    whatsapp: s.whatsapp,

    paymentMethod: s.paymentMethod,

    note: s.note || "-"

  };

  const db = readDB();

  db.orders.push(order);

  writeDB(db);

  const invoice =

`✅ *INVOICE BERHASIL DIBUAT*

• ID: \`${order.id}\`

• Produk: *${order.productName}* (${order.duration})

• Total: *${formatRupiah(order.price)}*

• Bayar via: *${order.paymentMethod}*

📌 *Instruksi:*

${config.PAYMENT_INFO.note}

Setelah bayar, kirim *bukti transfer* ke admin (atau reply ke bot dengan foto bukti + tulis ID order).`;

  await ctx.reply(invoice, { parse_mode: "Markdown" });

  // Notify Admin(s)

  const adminMsg =

`🛎️ *ORDER BARU MASUK*

• ID: \`${order.id}\`

• User: ${order.username ? `@${order.username}` : order.name} (ID: ${order.userId})

• Produk: *${order.productName}* (${order.duration})

• Harga: *${formatRupiah(order.price)}*

• Email: \`${order.email}\`

• WA: \`${order.whatsapp}\`

• Bayar: *${order.paymentMethod}*

• Catatan: ${order.note}

Klik aksi di bawah:`;

  for (const adminId of config.ADMIN_IDS) {

    try {

      await bot.telegram.sendMessage(adminId, adminMsg, {

        parse_mode: "Markdown",

        ...adminActionKeyboard(order.id)

      });

    } catch (e) {

      // ignore

    }

  }

  // reset session

  ctx.session = {};

});

// ====== Admin actions ======

async function updateOrderStatus(orderId, status, note) {

  const db = readDB();

  const idx = db.orders.findIndex(o => o.id === orderId);

  if (idx === -1) return null;

  db.orders[idx].status = status;

  db.orders[idx].note = note || db.orders[idx].note;

  writeDB(db);

  return db.orders[idx];

}

bot.action(/^admin:(approve|reject|paid|deliver):(.+)$/i, async (ctx) => {

  await ctx.answerCbQuery();

  if (!isAdmin(ctx)) return ctx.reply("❌ Kamu bukan admin.");

  const action = ctx.match[1];

  const orderId = ctx.match[2];

  let status = "PENDING";

  let note = "";

  if (action === "approve") { status = "APPROVED"; note = "Order disetujui admin."; }

  if (action === "reject") { status = "REJECTED"; note = "Order ditolak admin."; }

  if (action === "paid") { status = "PAID"; note = "Pembayaran dikonfirmasi admin."; }

  if (action === "deliver") { status = "DELIVERED"; note = "Pesanan sudah dikirim/diaktifkan."; }

  const order = await updateOrderStatus(orderId, status, note);

  if (!order) return ctx.reply("❌ Order tidak ditemukan.");

  // Inform user

  const userMsg =

`📌 *Update Order*

• ID: \`${order.id}\`

• Produk: *${order.productName}*

• Status: *${order.status}*

Catatan: ${order.note || "-"}`;

  try {

    await bot.telegram.sendMessage(order.userId, userMsg, { parse_mode: "Markdown" });

  } catch (e) {

    // ignore

  }

  await ctx.reply(`✅ Order ${orderId} => ${status}`);

});

// ====== Optional: user sends proof photo (forward to admin) ======

bot.on("photo", async (ctx) => {

  const caption = (ctx.message.caption || "").trim();

  // user can write order id in caption

  const possibleId = caption.match(/ORD-\d{8}-[A-Z0-9]{4}/i)?.[0];

  const info =

`🧾 Bukti pembayaran masuk

User: ${ctx.from.username ? `@${ctx.from.username}` : ctx.from.first_name}

UserID: ${ctx.from.id}

OrderID: ${possibleId || "(tidak ditulis)"}

Caption: ${caption || "-"}`;

  for (const adminId of config.ADMIN_IDS) {

    try {

      await bot.telegram.sendMessage(adminId, info);

      await bot.telegram.forwardMessage(adminId, ctx.chat.id, ctx.message.message_id);

    } catch (e) {}

  }

  await ctx.reply("✅ Bukti pembayaran terkirim ke admin. Tunggu konfirmasi ya.");

});

// ====== Banner ======

const banner = chalk.green(`

┏───────────────────────────────┓

│ ${config.STORE_NAME.padEnd(29)}│

│ Version   : AutoOrder v1      │

│ Platform  : Telegram          │

│ Library   : Telegraf          │

┗───────────────────────────────┛

`);

console.clear();

console.log(banner);

// ====== Launch ======

(async () => {

  try {

    await bot.launch();

  } catch (e) {

    console.log("Bot failed to launch:", e.message);

  }

})();

process.once("SIGINT", () => bot.stop("SIGINT"));

process.once("SIGTERM", () => bot.stop("SIGTERM"));