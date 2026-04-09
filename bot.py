import asyncio
import logging
import os
import uuid
from typing import Dict, Any

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, FSInputFile
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required")

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

class ThumbnailStates(StatesGroup):
    waiting_for_video = State()
    waiting_for_image = State()
    processing = State()

async def add_thumbnail_to_video(video_path: str, image_path: str, output_path: str) -> bool:
    """
    FFmpeg yordamida videoga thumbnail qo'shish.
    Qayta kodlamasdan, tez va sifatli usul.
    """
    import subprocess
    
    # FFmpeg buyrug'i: ikkala faylni o'qiydi, videoni qayta kodlamaydi, 
    # rasmni esa thumbnail sifatida belgilaydi
    cmd = [
        'ffmpeg', '-i', video_path,  # Video fayl
        '-i', image_path,             # Rasm fayl
        '-map', '0', '-map', '1',     # Video va rasm streamlarini belgilash
        '-c', 'copy',                 # Qayta kodlamasdan nusxalash
        '-disposition:v:1', 'attached_pic',  # Rasmni thumbnail sifatida belgilash
        '-movflags', 'faststart',     # Streaming uchun optimallashtirish
        '-map_metadata', '0',         # Original video metama'lumotlarini saqlash
        output_path
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info(f"FFmpeg successful: {result.stderr}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg error: {e.stderr}")
        return False

@dp.message(Command("start"))
async def start_command(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "🎬 <b>Video Thumbnail Setter Bot</b>\n\n"
        "Bu bot sizga video faylga o'zingiz tanlagan rasmni oblojka qilib qo'shish imkonini beradi.\n\n"
        "📌 <b>Ishlash tartibi:</b>\n"
        "1. Video faylni yuboring\n"
        "2. Rasm faylni yuboring (JPEG/PNG)\n"
        "3. Bot qayta ishlab, tayyor videoni sizga qaytaradi\n\n"
        "⚠️ <b>Eslatma:</b> Video 50 MB dan kichik bo'lishi kerak. Rasm esa JPEG formatida va 200 KB dan kichik bo'lishi tavsiya etiladi.",
        parse_mode="HTML"
    )
    await state.set_state(ThumbnailStates.waiting_for_video)

@dp.message(ThumbnailStates.waiting_for_video, F.video)
async def receive_video(message: Message, state: FSMContext) -> None:
    video = message.video
    if video.file_size > 50 * 1024 * 1024:
        await message.answer("❌ Video hajmi 50 MB dan oshmasligi kerak. Iltimos, kichikroq video yuboring.")
        return
    
    # Videoni vaqtincha saqlash
    file = await bot.get_file(video.file_id)
    video_path = f"temp_video_{uuid.uuid4()}.mp4"
    await bot.download_file(file.file_path, video_path)
    
    await state.update_data(video_path=video_path)
    await state.set_state(ThumbnailStates.waiting_for_image)
    await message.answer("✅ Video qabul qilindi. Endi oblojka uchun rasm yuboring (JPEG yoki PNG formatida).")

@dp.message(ThumbnailStates.waiting_for_video)
async def invalid_video(message: Message) -> None:
    await message.answer("❌ Iltimos, video fayl yuboring.")

@dp.message(ThumbnailStates.waiting_for_image, F.photo)
async def receive_image(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    video_path = data.get("video_path")
    
    if not video_path:
        await message.answer("❌ Xatolik yuz berdi. Iltimos, /start buyrug'i bilan qayta urinib ko'ring.")
        await state.clear()
        return
    
    # Eng yuqori sifatli rasmni olish
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    image_path = f"temp_image_{uuid.uuid4()}.jpg"
    await bot.download_file(file.file_path, image_path)
    
    await state.set_state(ThumbnailStates.processing)
    processing_msg = await message.answer("⏳ Video qayta ishlanmoqda... Bu bir necha daqiqa olishi mumkin.")
    
    # Video va rasmni birlashtirish
    output_path = f"output_video_{uuid.uuid4()}.mp4"
    success = await add_thumbnail_to_video(video_path, image_path, output_path)
    
    if not success:
        await processing_msg.delete()
        await message.answer("❌ Video qayta ishlashda xatolik yuz berdi. Iltimos, boshqa video yoki rasm bilan urinib ko'ring.")
        # Tozalash
        for path in [video_path, image_path, output_path]:
            if os.path.exists(path):
                os.remove(path)
        await state.clear()
        return
    
    # Tayyor videoni yuborish
    await processing_msg.delete()
    try:
        with open(output_path, 'rb') as video_file:
            await message.answer_video(
                video=FSInputFile(output_path),
                caption="✅ Tayyor video! Endi uni asosiy botingizga yuborishingiz mumkin.",
                supports_streaming=True
            )
    except Exception as e:
        logger.error(f"Error sending video: {e}")
        await message.answer("❌ Tayyor videoni yuborishda xatolik yuz berdi.")
    finally:
        # Vaqtinchalik fayllarni o'chirish
        for path in [video_path, image_path, output_path]:
            if os.path.exists(path):
                os.remove(path)
    
    await state.clear()
    await message.answer("🎬 Yana bir video uchun /start buyrug'ini yuboring.")

@dp.message(ThumbnailStates.waiting_for_image)
async def invalid_image(message: Message) -> None:
    await message.answer("❌ Iltimos, oblojka uchun rasm yuboring.")

@dp.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    video_path = data.get("video_path")
    if video_path and os.path.exists(video_path):
        os.remove(video_path)
    await state.clear()
    await message.answer("❌ Jarayon bekor qilindi. /start bilan qayta boshlashingiz mumkin.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
