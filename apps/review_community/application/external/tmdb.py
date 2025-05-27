import requests

class TMDBClient:
    BASE_URL = "https://api.themoviedb.org/3"
    API_KEY = "a6596aeba251cb8c79bcab0b45072ee4"  # 🔐 실제 API 키로 교체 필요

    def fetch_movie_by_id(self, tmdb_id):
        """
        TMDB에서 영화 정보를 불러옵니다.
        """
        url = f"{self.BASE_URL}/movie/{tmdb_id}"
        params = {
            "api_key": self.API_KEY,
            "language": "ko-KR"
        }

        response = requests.get(url, params=params)

        if response.status_code == 200:
            data = response.json()
            return {
                "id": data["id"],
                "title": data.get("title"),
                "original_title": data.get("original_title"),
                "overview": data.get("overview"),
                "release_date": data.get("release_date"),
                "poster_path": f"https://image.tmdb.org/t/p/w500{data.get('poster_path')}" if data.get("poster_path") else None
            }
        else:
            print(f"❌ TMDB API 호출 실패: {response.status_code} {response.text}")
            return None
