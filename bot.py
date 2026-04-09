import asyncio
import logging
import os
import uuid
import subprocess
from aiogram import Bot, Dispatcher, types, F
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
    """
    cmd = [
        'ffmpeg', '-i', video_path,
        '-i', image_path,
        '-map', '0', '-map', '1',
        '-c', 'copy',
        '-disposition:v:1', 'attached_pic',
        '-movflags', 'faststart',
        '-map_metadata', '0',
        output_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info(f"FFmpeg success: {result.stderr}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg error: {e.stderr}")
        return False

@dp.message(Command("start"))
async def start_command(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🎬 <b>Video Thumbnail Setter Bot</b>\n\n"
        "Bu bot sizga video faylga o'zingiz tanlagan rasmni oblojka qilib qo'shadi.\n\n"
        "1. Video yuboring\n"
        "2. Rasm yuboring\n"
        "3. Tayyor videoni oling\n\n"
        "⚠️ Video 50 MB dan kichik, rasm JPEG va 200 KB dan kichik bo'lishi tavsiya etiladi.",
        parse_mode="HTML"
    )
    await state.set_state(ThumbnailStates.waiting_for_video)

@dp.message(ThumbnailStates.waiting_for_video, F.video)
async def receive_video(message: Message, state: FSMContext):
    video = message.video
    if video.file_size > 50 * 1024 * 1024:
        await message.answer("❌ Video hajmi 50 MB dan oshmasligi kerak.")
        return
    file = await bot.get_file(video.file_id)
    video_path = f"temp_video_{uuid.uuid4()}.mp4"
    await bot.download_file(file.file_path, video_path)
    await state.update_data(video_path=video_path)
    await state.set_state(ThumbnailStates.waiting_for_image)
    await message.answer("✅ Video qabul qilindi. Endi oblojka uchun rasm yuboring (JPEG/PNG).")

@dp.message(ThumbnailStates.waiting_for_video)
async def invalid_video(message: Message):
    await message.answer("❌ Iltimos, video fayl yuboring.")

@dp.message(ThumbnailStates.waiting_for_image, F.photo)
async def receive_image(message: Message, state: FSMContext):
    data = await state.get_data()
    video_path = data.get("video_path")
    if not video_path:
        await message.answer("❌ Xatolik. /start bilan qayta boshlang.")
        await state.clear()
        return
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    image_path = f"temp_image_{uuid.uuid4()}.jpg"
    await bot.download_file(file.file_path, image_path)
    await state.set_state(ThumbnailStates.processing)
    processing_msg = await message.answer("⏳ Video qayta ishlanmoqda...")
    output_path = f"output_video_{uuid.uuid4()}.mp4"
    success = await add_thumbnail_to_video(video_path, image_path, output_path)
    if not success:
        await processing_msg.delete()
        await message.answer("❌ Xatolik yuz berdi. Boshqa rasm yoki video bilan urinib ko'ring.")
        for path in [video_path, image_path, output_path]:
            if os.path.exists(path):
                os.remove(path)
        await state.clear()
        return
    await processing_msg.delete()
    try:
        await message.answer_video(video=FSInputFile(output_path), caption="✅ Tayyor video!", supports_streaming=True)
    except Exception as e:
        logger.error(f"Yuborish xatosi: {e}")
        await message.answer("❌ Tayyor videoni yuborishda xatolik.")
    finally:
        for path in [video_path, image_path, output_path]:
            if os.path.exists(path):
                os.remove(path)
    await state.clear()
    await message.answer("🎬 Yana bir video uchun /start yuboring.")

@dp.message(ThumbnailStates.waiting_for_image)
async def invalid_image(message: Message):
    await message.answer("❌ Iltimos, rasm yuboring (JPEG/PNG).")

@dp.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext):
    data = await state.get_data()
    video_path = data.get("video_path")
    if video_path and os.path.exists(video_path):
        os.remove(video_path)
    await state.clear()
    await message.answer("❌ Jarayon bekor qilindi. /start bilan qayta boshlang.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
