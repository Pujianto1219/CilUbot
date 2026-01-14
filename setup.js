const fs = require('fs');
const readline = require('readline');
const chalk = require('chalk'); // Agar terminal berwarna

// Nama file konfigurasi rahasia
const envFile = '.env';

// Fungsi untuk bertanya di terminal
const askQuestion = (query) => {
    const rl = readline.createInterface({
        input: process.stdin,
        output: process.stdout,
    });
    return new Promise((resolve) => rl.question(query, (ans) => {
        rl.close();
        resolve(ans);
    }));
};

const startBot = () => {
    console.log(chalk.green('\n✅ Konfigurasi ditemukan. Menjalankan Bot...\n'));
    // Jalankan file utama bot
    require('./index.js');
};

const setup = async () => {
    // Cek apakah file .env sudah ada
    if (fs.existsSync(envFile)) {
        startBot();
        return;
    }

    console.clear();
    console.log(chalk.blue.bold('========================================='));
    console.log(chalk.yellow.bold('      CILBOT AUTO SETUP INSTALLER        '));
    console.log(chalk.blue.bold('========================================='));
    console.log('File konfigurasi (.env) belum ditemukan.');
    console.log('Silakan masukkan data yang diperlukan:\n');

    try {
        // Pertanyaan 1: Bot Token
        let token = '';
        while (!token) {
            token = await askQuestion(chalk.cyan('1. Masukkan Bot Token (dari @BotFather): '));
            if (!token) console.log(chalk.red('❌ Token tidak boleh kosong!'));
        }

        // Pertanyaan 2: Owner ID (Opsional, default ke angka random kalau kosong)
        let owner = await askQuestion(chalk.cyan('2. Masukkan ID Telegram Owner (Opsional): '));
        if (!owner) owner = '123456789';

        // Pertanyaan 3: MongoDB (Opsional)
        let mongo = await askQuestion(chalk.cyan('3. Masukkan Mongo URI (Enter untuk lewati): '));
        
        // Menyusun isi file .env
        let envContent = `BOT_TOKEN=${token.trim()}\nOWNER_ID=${owner.trim()}\n`;
        if (mongo) envContent += `MONGO_URI=${mongo.trim()}\n`;

        // Membuat file .env
        fs.writeFileSync(envFile, envContent);
        
        console.log(chalk.green('\n✅ Setup Berhasil! File .env telah dibuat.'));
        console.log(chalk.gray('Bot akan berjalan dalam 3 detik...'));
        
        setTimeout(() => {
            startBot();
        }, 3000);

    } catch (error) {
        console.error(chalk.red('Terjadi kesalahan saat setup:'), error);
    }
};

// Jalankan Setup
setup();
