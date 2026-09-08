from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# To'rt tugma — ilgari 12 ta edi. Qolganlari yo'qolmadi: ular shu
# to'rttaning ostidagi inline menyularda (handlers/admin/menu.py va
# journal.py). Reply-klaviatura ekranning yarmini egallardi va yangi
# admin o'xshash to'rtta tugmadan qaysi biri nima qilishini
# topolmasdi.
admin_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [
            # Ilgari ikkita alohida tugma edi ("Barchaga" va "Userga").
            # Ular bir xil ish qilardi, faqat oluvchi soni farq qilardi —
            # oluvchini oqim ICHIDA tanlash tabiiyroq va bitta kod yo'li
            # qoladi.
            KeyboardButton(text='📢 Xabar yuborish'),
        ],
        [
            # Statistika, faol foydalanuvchilar, ro'yxat va bitta
            # foydalanuvchini boshqarish — hammasi "kim botdan
            # foydalanmoqda" savoli.
            KeyboardButton(text='👥 Foydalanuvchilar'),
        ],
        [
            # Audit, xatolar, daromad, limitlar, rejalashtirilgan
            # tarqatmalar va faol emas foydalanuvchilar.
            KeyboardButton(text="📋 Jurnal va sozlamalar"),
        ],
        [
            # Bepul Pro, referal sharti, texnik ta'til, kuzatish va
            # adminlar ro'yxati — botning o'zini sozlash.
            KeyboardButton(text="⚙️ Sozlamalar"),
        ],
    ], resize_keyboard=True, one_time_keyboard=False
)
