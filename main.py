from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ytmusicapi import YTMusic

# 1. FastAPI 앱 및 YTMusic 객체 생성
app = FastAPI()
ytmusic = YTMusic()

# 2. CORS 설정 (가장 중요!)
# Next.js(localhost:3000)에서 이 파이썬 서버로 통신할 수 있게 허락해주는 설정이야.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000",
                   "https://mudai-three.vercel.app/"],  # 프론트엔드 주소 허용
    allow_credentials=True,
    allow_methods=["*"],  # GET, POST 등 모든 통신 방식 허용
    allow_headers=["*"],
)

# 3. 유튜브 뮤직 검색 API 엔드포인트 만들기
@app.get("/api/search")
async def search_music(artist: str, limit: int = 20):
    try:
        # 유튜브 뮤직에서 '곡(songs)' 카테고리만 콕 집어서 검색!
        # (티저, 커버, 라이브 영상 등 이상한 거 알아서 다 걸러짐)
        search_results = ytmusic.search(query=artist, filter="songs", limit=limit)
        
        # Next.js 프론트엔드가 쓰기 편하게 데이터 모양을 깔끔하게 다듬기
        clean_tracks = []
        for item in search_results:
            # 곡 제목, 비디오 ID, 썸네일 등 필요한 것만 추출
            clean_tracks.append({
                "videoId": item.get("videoId"),
                "title": item.get("title"),
                "artist": ", ".join([a.get("name") for a in item.get("artists", [])]),
                "thumbnail": item.get("thumbnails")[-1].get("url") if item.get("thumbnails") else "",
                "duration": item.get("duration"),
                "duration_seconds": item.get("duration_seconds")
            })
            
        return {"status": "success", "tracks": clean_tracks}
        
    except Exception as e:
        return {"status": "error", "message": str(e)}

# 기본 접속 테스트용
@app.get("/")
async def root():
    return {"message": "Mudai Python Backend is running! 🚀"}