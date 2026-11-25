import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter
from aiohttp import ClientConnectorError
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from openai import AsyncOpenAI
from core.config import BOT_TOKEN, OPENAI_API_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FloodKutish(BaseRequestMiddleware):
    """Telegram 429 (`retry_after`) — YUBORISH metodida kutib qayta urinadi.

    ⚠️ Jonli (2026-11-20): bitta chatda bir soniyada 11 ta javob bo'lagi va
    2 ta fayl «Flood control, retry in 12» bilan rad etildi va IZSIZ
    yo'qoldi — `_answer_plain` va fayl yuborish 429 ni oddiy xato deb
    ushlardi. Har chaqiruvchini alohida tuzatish o'rniga — shu bitta joy.

    Faqat `_YUBORISH`: draft/tahrir/chat action'da kutish oqimni to'xtatardi
    (keyingi ping baribir keladi), callback/guest javobining esa muddati
    o'tib ketardi, getUpdates'ni aiogram o'zi qayta so'raydi. Uzoq kutish
    (> `ENG_KOP` s) — kutmaymiz, xato chaqiruvchiga (uning zaxirasi bor).

    Ulanib bo'lmadi (`ClientConnectorError`) — ham qayta: so'rov serverga
    umuman yetmagan, ya'ni takror xabar chiqmaydi (jonli: Biznes mijozi
    javobsiz qoldi, 4 marta / 5 kun). ⚠️ TIMEOUT qayta urinilMAYDI — u
    yetib borgan bo'lishi mumkin, mijoz ikki xil javob olardi (CHAT.md)."""

    _YUBORISH = frozenset({
        "sendMessage", "sendDocument", "sendPhoto", "sendVoice", "sendAudio",
        "sendVideo", "sendAnimation", "sendMediaGroup", "sendSticker",
        "sendLocation", "sendVenue", "copyMessage", "forwardMessage",
    })
    ENG_KOP = 30
    URINISH = 2

    async def __call__(self, make_request, bot_, method):
        nomi = getattr(method, "__api_method__", "")
        for qayta in range(self.URINISH + 1):
            try:
                return await make_request(bot_, method)
            except TelegramRetryAfter as e:
                if (nomi not in self._YUBORISH or qayta == self.URINISH
                        or e.retry_after > self.ENG_KOP):
                    raise
                logger.info(f"[Flood] {nomi}: {e.retry_after} s kutib qayta")
                await asyncio.sleep(e.retry_after)
            except TelegramNetworkError as e:
                if (nomi not in self._YUBORISH or qayta == self.URINISH
                        or not isinstance(getattr(e, "original", None), ClientConnectorError)):
                    raise
                logger.info(f"[Flood] {nomi}: Telegram'ga ulanib bo'lmadi, qayta")
                await asyncio.sleep(1.5)


session = AiohttpSession()
session.middleware(FloodKutish())
bot = Bot(
    token=BOT_TOKEN,
    session=session,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)