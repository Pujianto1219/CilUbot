require('dotenv').config();
const { Telegraf } = require('telegraf');
const chalk = require('chalk');

// Validasi Token
if (!process.env.BOT_TOKEN) {
    console.error(chalk.red('❌ Error: BOT_TOKEN tidak ditemukan di file .env'));
    process.exit(1);
}

const bot = new Telegraf(process.env.BOT_TOKEN);

// Tampilan saat bot berjalan
bot.use(async (ctx, next) => {
    const start = new Date();
    await next();
    const ms = new Date() - start;
    const user = ctx.from ? ctx.from.first_name : 'Unknown';
    console.log(chalk.blue('[PESAN]'), `Dari ${user}: ${ctx.message?.text || ctx.updateType}`, chalk.yellow(`(${ms}ms)`));
});

bot.start((ctx) => {
    ctx.reply(`Halo! Saya CilBot.\nBot berhasil diinstal & berjalan lancar! 🚀\n\nID Anda: \`${ctx.from.id}\``, { parse_mode: 'Markdown' });
});

bot.command('ping', (ctx) => ctx.reply('🏓 Pong! Setup berhasil.'));

// Error handling
bot.catch((err) => {
    console.log(chalk.red('Terjadi Error:'), err);
});

console.log(chalk.green('🚀 Bot berhasil login dan siap digunakan!'));
console.log(chalk.cyan(`👤 Owner ID: ${process.env.OWNER_ID}`));

// Jalankan bot
bot.launch();

// Graceful Stop (Agar aman saat di-stop paksa)
process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));
