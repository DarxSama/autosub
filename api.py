from flask import Flask, request, jsonify, send_file
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
from moviepy.video.tools.subtitles import SubtitlesClip
from pydub import AudioSegment
import speech_recognition as sr
import os
import re
from moviepy.config import change_settings
IMAGEMAGICK_PATH = r"C:\Program Files\ImageMagick-7.1.1-Q16\magick.exe"
change_settings({"IMAGEMAGICK_BINARY": IMAGEMAGICK_PATH})


app = Flask(__name__)



# ฟังก์ชันแปลงเวลาจากรูปแบบ "HH:MM:SS,SSS" เป็นวินาที
def time_str_to_seconds(time_str):
    hours, minutes, seconds = time_str.split(':')
    seconds, millis = seconds.split(',')
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000

# ฟังก์ชันอ่านไฟล์ซับไตเติ้ลจากไฟล์ .srt
def read_srt_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()

    pattern = re.compile(r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.*)')
    subtitles = []
    i = 0

    while i < len(lines):
        match = pattern.match(''.join(lines[i:i + 4]))
        if match:
            _, start, end, text = match.groups()
            start_time = time_str_to_seconds(start)  # แปลงเวลาเริ่มต้นเป็นวินาที
            end_time = time_str_to_seconds(end)      # แปลงเวลาสิ้นสุดเป็นวินาที
            subtitles.append(((start_time, end_time), text.strip()))  # เก็บข้อมูลในรูปแบบที่ SubtitlesClip ต้องการ
            i += 4
        else:
            i += 1

    return subtitles

# ฟังก์ชันสำหรับแปลงไฟล์ mp4 เป็น wav
def mp4_to_wav(mp4_file, wav_output):
    video = VideoFileClip(mp4_file)
    audio = video.audio
    audio.write_audiofile("temp_audio.mp3")

    sound = AudioSegment.from_mp3("temp_audio.mp3")
    sound.export(wav_output, format="wav")
    
    audio.close()
    video.close()
    os.remove("temp_audio.mp3")

# ฟังก์ชันแปลงเสียงเป็นข้อความ
def speech_to_text(wav_file):
    recognizer = sr.Recognizer()
    with sr.AudioFile(wav_file) as source:
        audio = recognizer.record(source)
    try:
        text = recognizer.recognize_google(audio, language='en') 
        return text
    except sr.UnknownValueError:
        return ""
    except sr.RequestError:
        return ""

# ฟังก์ชันสำหรับจัดรูปแบบเวลาในรูปแบบ HH:MM:SS,SSS
def format_time(seconds):
    millisec = int((seconds - int(seconds)) * 1000)
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    return f"{hours:02}:{minutes:02}:{seconds:02},{millisec:03}"

def create_subtitle(text, video_duration, output_file="subtitle.srt"):
    if not text.strip():
        text = "ไม่มีข้อความจากเสียง กรุณาตรวจสอบคุณภาพของเสียง"
    
    # แบ่งข้อความเป็นกลุ่มย่อย (ประมาณ 10-15 คำต่อกลุ่ม)
    words = text.split()
    subtitles = []
    max_words_per_sub = 15  # กำหนดจำนวนคำต่อซับไตเติ้ล
    for i in range(0, len(words), max_words_per_sub):
        subtitles.append(" ".join(words[i:i + max_words_per_sub]))
    
    # คำนวณเวลาสำหรับแต่ละซับไตเติ้ล
    interval = video_duration / len(subtitles) if subtitles else 5
    
    with open(output_file, "w", encoding="utf-8") as f:
        for i, subtitle in enumerate(subtitles):
            start_time = i * interval
            end_time = min((i + 1) * interval, video_duration)
            
            f.write(f"{i + 1}\n")
            f.write(f"{format_time(start_time)} --> {format_time(end_time)}\n")
            f.write(subtitle.strip() + "\n\n")

# ฟังก์ชันเพิ่มซับไตเติ้ลลงในวิดีโอ
def add_subtitle_to_video(video_file, subtitle_file, output_file):
    try:
        # โหลดวิดีโอ
        video = VideoFileClip(video_file)

        # อ่านซับไตเติ้ลจากไฟล์ .srt
        subtitles = read_srt_file(subtitle_file)

        # สร้างฟังก์ชันสำหรับสร้าง TextClip
        def subtitle_generator(txt):
            return TextClip(txt, fontsize=24, font="Arial", color="white", bg_color="black")

        # สร้าง SubtitlesClip
        subtitles_clip = SubtitlesClip(subtitles, subtitle_generator)

        # ตั้งค่าตำแหน่งซับไตเติ้ล
        subtitles_clip = subtitles_clip.set_position(('center', 'bottom'))

        # รวมคลิปวิดีโอและซับไตเติ้ล
        final_clip = CompositeVideoClip([video, subtitles_clip.set_duration(video.duration)])

        # บันทึกไฟล์วิดีโอที่มีซับไตเติ้ล
        final_clip.write_videofile(output_file, codec="libx264", fps=video.fps)
        print(f"บันทึกไฟล์สำเร็จ: {output_file}")
    except Exception as e:
        print(f"เกิดข้อผิดพลาด: {e}")

# Endpoint สำหรับอัพโหลดวิดีโอและประมวลผลซับไตเติ้ล
@app.route('/video', methods=['POST'])
def upload_video():
    if 'video' not in request.files:
        return jsonify({"error": "กรุณาอัพโหลดไฟล์วิดีโอ"}), 400

    video_file = request.files['video']
    video_path = "input_video.mp4"
    video_file.save(video_path)

    wav_file = "audio.wav"
    subtitle_file = "subtitle.srt"
    output_video_file = "input.mp4"

    mp4_to_wav(video_path, wav_file)
    text = speech_to_text(wav_file)
    video_duration = VideoFileClip(video_path).duration
    create_subtitle(text, video_duration, subtitle_file)
    add_subtitle_to_video(video_path, subtitle_file, output_video_file)

    return send_file(output_video_file, as_attachment=True)

if __name__ == '__main__':
    app.run(host='10.10.9.48', port=5000, debug=True)
