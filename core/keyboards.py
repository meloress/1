from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

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
            KeyboardButton(text='🏆 Faol foydalanuvchilar'),
            KeyboardButton(text='📊 Statistika')
        ],
        [
            KeyboardButton(text="➖ Admin o'chirish"),
            KeyboardButton(text="➕ Admin qo'shish")
        ],
        [
            KeyboardButton(text="📄 Userlar ro'yxati"),
            KeyboardButton(text="🔍 Foydalanuvchini boshqarish")
        ],
        [
            KeyboardButton(text="🛠 Texnik ta'til"),
            KeyboardButton(text="👁 Kuzatish")
        ],
        [
            KeyboardButton(text="🎁 Bepul Pro"),
            KeyboardButton(text="👥 Referal sharti"),
        ],
        [
            # Audit, xatolar, daromad, limitlar va rejalashtirilgan
            # tarqatmalar — hammasi shu tugma ostidagi inline menyuda.
            # Alohida tugma qilinmadi: reply-klaviatura allaqachon
            # to'lgan va yangi admin qaysi tugma nima qilishini
            # topolmay qolardi.
            KeyboardButton(text="📋 Jurnal va sozlamalar"),
        ],
    ], resize_keyboard=True, one_time_keyboard=False
)







