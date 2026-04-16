import re
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ytmusicapi import YTMusic
import pykakasi
import random

# FastAPI 앱 및 YTMusic 객체 생성
app = FastAPI()
ytmusic = YTMusic()
kks = pykakasi.kakasi()

# CORS 설정 
# Next.js(localhost:3000)에서 이 파이썬 서버로 통신할 수 있게 허락해주는 설정이야.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000",
                   "https://mudai-three.vercel.app"],  # 프론트엔드 주소 허용
    allow_credentials=True,
    allow_methods=["*"],  # GET, POST 등 모든 통신 방식 허용
    allow_headers=["*"],
)

EXCLUDE_KEYWORDS = [
    "cover", "カバー",                      # 커버곡
    "live", "ライブ", "concert",            # 라이브 영상
    "inst", "instrumental", "off vocal",   # 반주
    "mr", "カラオケ", "karaoke",              # 노래방
    "remix",                                # 변형 곡
]

# 프론트엔드에서 가져온 제목 텍스트 가공
def clean_and_split_title(raw_title: str):
    # 1. 특수문자 디코딩
    text = raw_title.replace("&quot;", '"').replace("&#39;", "'").replace("&amp;", "&")
    
    # 2. 메인 제목과 서브 정답(alt_answers) 분리 (기존 fetchYouTubeTracks 로직)
    main_title = text
    alt_answer = ""
    
    if " - " in text:
        parts = text.split(" - ", 1)
        main_title = parts[0].strip()
        alt_answer = parts[1].strip()
    elif " (" in text:
        parts = text.split(" (", 1)
        main_title = parts[0].strip()
        alt_answer = parts[1].replace(")", "").strip()

    # 3. 메인 제목에서 쓸데없는 말과 괄호 지우기 (기존 cleanUpTitle 로직)
    match = re.search(r"「(.*?)」", main_title)
    if match:
        clean_title = match.group(1)
    else:
        # 대소문자 무시(re.IGNORECASE)하고 지저분한 키워드 싹둑!
        clean_title = re.sub(r"【.*?】|\[.*?\]|\(.*?\)|official|music video|mv|audio", "", main_title, flags=re.IGNORECASE).strip()
        
    return clean_title, alt_answer

# 유튜브 뮤직 검색 API 엔드포인트 만들기
@app.get("/api/search")
async def search_music(artist: str, limit: int = 20):
    try:
        # 유튜브 뮤직에서 '곡(songs)' 카테고리만 콕 집어서 검색!
        # (티저, 커버, 라이브 영상 등 이상한 거 알아서 다 걸러짐)
        search_results = ytmusic.search(query=artist, filter="songs", limit=limit)

        if not search_results:
            return {"status": "success", "tracks": []}
        
        sample_artist = search_results[0].get("artists", [{}])[0].get("name", "").split(",")[0].strip()
        
        # Next.js 프론트엔드가 쓰기 편하게 데이터 모양을 깔끔하게 다듬기
        raw_tracks = []
        for item in search_results:
            raw_title = item.get("title", "")
            raw_title_lower = raw_title.lower()

            if any(keyword in raw_title_lower for keyword in EXCLUDE_KEYWORDS):
                continue

            item_artists = [a.get("name") for a in item.get("artists", [])]
            if not any(sample_artist in a for a in item_artists):
                continue
            
            clean_title, alt_answer = clean_and_split_title(raw_title)  # 제목 가공
            kks_result = kks.convert(clean_title)   # 발음 추출: 한자가 섞인 clean_title을 분석해서 여러 형태로 변환함
            kana_reading = "".join([r['kana'] for r in kks_result])  # 1. 가타카나 발음 추출 (예: カイジュウノハナウタ)
            romaji_reading = "".join([r['hepburn'] for r in kks_result])    # 2. 로마자 영어 발음 추출 (예: kaijuunohanauta)

            combined_alts = []
            if alt_answer: 
                combined_alts.append(alt_answer)
            if kana_reading and kana_reading != clean_title: 
                combined_alts.append(kana_reading) # 한자가 포함된 경우만 추가!
            if romaji_reading: 
                combined_alts.append(romaji_reading)

            raw_tracks.append({
                "id": { "videoId": item.get("videoId") },
                "snippet": {
                    "title": clean_title,
                    "channelTitle": ", ".join(item_artists),
                    "thumbnails": { "default": { "url": item.get("thumbnails")[-1].get("url") if item.get("thumbnails") else "" } }
                },
                "alt_answers": ",".join(combined_alts),
                "_duration_seconds": item.get("duration_seconds")
            })
            
        random.shuffle(raw_tracks)
        
        return {"status": "success", "tracks": raw_tracks}
        
    except Exception as e:
        return {"status": "error", "message": str(e)}

# 기본 접속 테스트용
@app.get("/")
async def root():
    return {"message": "Mudai Python Backend is running! 🚀"}