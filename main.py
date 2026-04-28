import re
import os
from fastapi import Request
from supabase import create_client, Client
from pydantic import BaseModel
from typing import List, Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ytmusicapi import YTMusic
import pykakasi
from janome.tokenizer import Tokenizer
import random

# FastAPI 앱 및 YTMusic 객체 생성
app = FastAPI()
ytmusic = YTMusic()
kks = pykakasi.kakasi()
tokenizer = Tokenizer()

SUPABASE_URL = "https://ypeulfyywbpvzhokzftu.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlwZXVsZnl5d2Jwdnpob2t6ZnR1Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQzMjQwNTgsImV4cCI6MjA4OTkwMDA1OH0.hyUipwapRkPWSrh1S7Ad9T5m10Y70TjIJqrV48n1lzY"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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

class QuestionSchema(BaseModel):
    image_text: str
    answer: str
    alt_answers: str
    hint: str
    youtube_url: str
    start_time: int
    end_time: int

class QuizCreateSchema(BaseModel):
    title: str
    type: str
    author: str
    user_id: Optional[str]
    tags: List[str]
    description: str
    thumbnail_url: str
    questions: List[QuestionSchema]

class NormalizeRequest(BaseModel):
    text: str

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

    # 고리점(。) 제거
    clean_title = clean_title.replace("。", "").replace(".", "").strip()
    alt_answer = alt_answer.replace("。", "").replace(".", "").strip()

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

            tokens = tokenizer.tokenize(clean_title)
            kana_reading = "".join([token.reading if token.reading != '*' else token.surface for token in tokens])

            kks_result = kks.convert(kana_reading)   # 발음 추출: 한자가 섞인 clean_title을 분석해서 여러 형태로 변환함
            #kana_reading = "".join([r['kana'] for r in kks_result])  # 1. 가타카나 발음 추출 (예: カイジュウノハナウタ)
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
    
@app.get("/api/quizzes")
async def get_quizzes():
    try:
        # 프론트엔드가 하던 짓을 백엔드가 대신 함!
        response = supabase.table("quizzes").select("*").order("id", desc=True).execute()
        
        return {"status": "success", "data": response.data}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    
@app.get("/api/quizzes/{quiz_id}")
async def get_quiz_details(quiz_id: int):
    try:
        # 1. 퀴즈 기본 정보 가져오기
        quiz_res = supabase.table("quizzes").select("*").eq("id", quiz_id).single().execute()
        
        # 2. 해당 퀴즈에 속한 문제 목록 가져오기
        questions_res = supabase.table("questions").select("*").eq("quiz_id", quiz_id).order("id").execute()
        
        return {
            "status": "success",
            "quiz": quiz_res.data,
            "questions": questions_res.data
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

# 퀴즈 생성 엔드포인트
@app.post("/api/quizzes")
async def create_full_quiz(data: QuizCreateSchema, request: Request):
    try:
        # 1. 프론트엔드가 보낸 '입장권(토큰)' 꺼내기
        auth_header = request.headers.get("Authorization")
        
        # 2. 이 요청 하나만을 위한 1회용 Supabase 클라이언트 만들기 
        # (전역 변수로 둔 supabase를 쓰면 동시 접속자들끼리 권한이 꼬일 수 있음!)
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # 3. 토큰이 있으면 "이 유저 권한으로 실행해 줘" 라고 세팅
        if auth_header:
            token = auth_header.replace("Bearer ", "")
            client.postgrest.auth(token) # 🚀 핵심: 경비원(RLS) 통과용 암호!

        # Step 1: 퀴즈 정보 삽입
        quiz_res = client.table("quizzes").insert({
            "title": data.title,
            "type": data.type,
            "author": data.author,
            "user_id": data.user_id,
            "tags": data.tags,
            "description": data.description,
            "thumbnail_url": data.thumbnail_url,
            "plays": 0
        }).execute()
        
        new_quiz_id = quiz_res.data[0]["id"]
        
        # Step 2: 문제 리스트 삽입 (quiz_id 연결)
        questions_to_insert = []
        for q in data.questions:
            questions_to_insert.append({
                "quiz_id": new_quiz_id,
                "image_text": q.image_text,
                "answer": q.answer,
                "alt_answers": q.alt_answers,
                "hint": q.hint,
                "youtube_url": q.youtube_url,
                "start_time": q.start_time,
                "end_time": q.end_time
            })
            
        client.table("questions").insert(questions_to_insert).execute()
        
        return {"status": "success", "id": new_quiz_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# 내 퀴즈 목록 가져오기 (인증 필요)
@app.get("/api/my-quizzes")
async def get_my_quizzes(request: Request):
    try:
        auth_header = request.headers.get("Authorization")
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        if auth_header:
            token = auth_header.replace("Bearer ", "")

            user_response = client.auth.get_user(token)
            my_user_id = user_response.user.id
            
            client.postgrest.auth(token)

        # RLS가 켜져있으므로 토큰을 세팅하면 내 퀴즈만 자동으로 필터링됨
        response = client.table("quizzes").select("*").eq("user_id", my_user_id).order("id", desc=True).execute()
        return {"status": "success", "data": response.data}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# 퀴즈 삭제하기 (인증 필요)
@app.delete("/api/quizzes/{quiz_id}")
async def delete_quiz(quiz_id: int, request: Request):
    try:
        auth_header = request.headers.get("Authorization")
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        if auth_header:
            token = auth_header.replace("Bearer ", "")
            client.postgrest.auth(token)

        # 1. 문제 먼저 삭제 (참조 무결성)
        client.table("questions").delete().eq("quiz_id", quiz_id).execute()
        # 2. 퀴즈 삭제
        client.table("quizzes").delete().eq("id", quiz_id).execute()
        
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/profile")
async def get_my_profile(request: Request):
    try:
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            return {"status": "error", "message": "토큰이 없습니다."}

        token = auth_header.replace("Bearer ", "")
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # 1. 토큰을 해독해서 유저 정보(user_id) 확인
        user_response = client.auth.get_user(token)
        my_user_id = user_response.user.id
        
        client.postgrest.auth(token) # RLS 통과용

        # 2. 내 ID에 해당하는 profiles 테이블 정보 가져오기
        profile_res = client.table("profiles").select("*").eq("id", my_user_id).single().execute()
        
        return {
            "status": "success", 
            "profile": profile_res.data
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
    
# 유저 입력값 발음 변환용 API
@app.post("/api/normalize")
async def normalize_text(req: NormalizeRequest):
    try:
        if not req.text:
            return {"status": "success", "normalized": ""}

        tokens = tokenizer.tokenize(req.text)
        
        # token.reading이 '*'이면 기호나 영어 등이므로 원래 글자(surface)를 그대로 사용
        kana_reading = [token.reading if token.reading != '*' else token.surface for token in tokens]
        normalized_text = "".join(kana_reading).replace(" ", "")

        # 고리점(。) 제거
        normalized_text = normalized_text.replace("。", "").replace(".", "").strip()
        # pykakasi로 유저 입력값을 분석해서 히라가나(hira)만 쏙쏙 뽑아내고 띄어쓰기 없애기!
        # result = kks.convert(req.text)
        # normalized_text = "".join([item['hira'] for item in result]).replace(" ", "")
        
        return {"status": "success", "normalized": normalized_text}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# 기본 접속 테스트용
@app.get("/")
async def root():
    return {"message": "Mudai Python Backend is running! 🚀"}