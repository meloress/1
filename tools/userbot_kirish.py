"""Navbatchi uchun BIR MARTALIK kirish — O'Z kompyuteringizda, O'ZINGIZ yurgizasiz.

    python tools/userbot_kirish.py

1. https://my.telegram.org → API development tools → api_id va api_hash.
2. Skript telefon raqamingizni, Telegram yuborgan kodni (va ikki bosqichli
   parol bo'lsa — uni) so'raydi. Ularni faqat shu terminalga kiritasiz.
3. Oxirida chiqqan uzun qator — USERBOT_SESSION. Uni Railway → Variables'ga
   qo'ying (USERBOT_SESSION, USERBOT_API_ID, USERBOT_API_HASH).

⛔️ USERBOT_SESSION — akkauntingizning TO'LIQ kaliti: hech kimga yubormang,
chatga, gitga, skrinshotga tushirmang. Sizib chiqsa: Telegram → Sozlamalar →
Qurilmalar → shu sessiyani tugating (kalit darhol o'ladi).
"""
import asyncio
from getpass import getpass

from telethon import TelegramClient
from telethon.sessions import StringSession


async def main() -> None:
    api_id = int(input("api_id: ").strip())
    api_hash = getpass("api_hash (ko'rinmaydi): ").strip()
    # `async with` → client.start(): raqam, kod, 2FA parolini o'zi so'raydi.
    async with TelegramClient(StringSession(), api_id, api_hash) as client:
        me = await client.get_me()
        print(f"\nKirildi: {me.first_name} (id {me.id})")
        print("\nQuyidagi qatorni Railway → Variables → USERBOT_SESSION ga qo'ying:\n")
        print(client.session.save())
        print("\n⛔️ Bu qatorni hech kimga ko'rsatmang. Terminalni tozalab qo'ying.")


if __name__ == "__main__":
    asyncio.run(main())
