import os
import json
import requests
import traceback
from typing import List, Tuple, Optional
from genieapi.Error import GenieScraperError
from bs4 import BeautifulSoup



class GenieAPI:
    """지니뮤직 API"""

    def __init__(self):
        self.LYRICS_BASE_URL = "https://dn.genie.co.kr/app/purchase/get_msl.asp?path=a&songid="
        self.SEARCH_BASE_URL = "https://www.genie.co.kr/search/searchAuto"
        self.SONG_INFO_BASE_URL = "https://www.genie.co.kr/detail/songInfo"

    def _get_request_headers(self) -> dict:
        """브라우저를 모방한 요청 헤더 생성."""
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

    def search_song(self, song_name: str, limit: int = 1) -> List[Tuple[str, str, str, str]]:
        """
        지니뮤직에서 노래 검색.

        입력값:
            song_name (str): 검색할 노래 이름
            limit (int, optional): 검색 결과 제한. 기본값은 1.

        반환값:
            (노래 이름, 노래 ID, 추가 필드, 썸네일 URL)의 튜플 리스트
        """
        if not 1 <= limit <= 4:
            raise ValueError("limit 값은 1에서 4 사이여야 합니다.")

        try:
            response = requests.get(
                self.SEARCH_BASE_URL,
                params={"query": song_name},
                headers=self._get_request_headers()
            )
            response.raise_for_status()
            data = response.json()

            songs = []
            for i in range(min(limit, len(data.get('song', [])))):
                song = data['song'][i]
                song_id = song['id']
                
                # 썸네일 URL 가져오기
                thumbnail_url = self._get_thumbnail_url(song_id)
                
                songs.append((
                    song['word'],         # 노래 제목
                    song_id,              # 노래 ID
                    song.get('field1', ''), # 추가 정보 (아티스트 - 앨범)
                    thumbnail_url         # 썸네일 URL
                ))

            return songs

        except requests.RequestException as e:
            raise GenieScraperError(f"검색 요청 실패: {e}")
        except (KeyError, IndexError) as e:
            raise GenieScraperError(f"예상치 못한 응답 형식: {e}")

    def get_lyrics(self, song_id: str) -> Optional[str]:
        """
        주어진 노래 ID의 가사 조회.

        입력값:
            song_id (str): 노래 고유 식별자

        반환값:
            가사 문자열 또는 None
        """
        try:
            response = requests.get(
                self.LYRICS_BASE_URL + song_id,
                headers=self._get_request_headers()
            )
            response.raise_for_status()

            lyrics_json_str = response.text[response.text.index("(") + 1:response.text.rindex(")")]
            lyrics_data = json.loads(lyrics_json_str)
            
            # 타임스탬프로 정렬된 가사 생성
            lyrics_lines = [
                f"[{int(time_ms) // 60000:02}:{(int(time_ms) % 60000) // 1000:02}.{(int(time_ms) % 1000) // 10:02}] {lyric}"
                for time_ms, lyric in sorted(lyrics_data.items(), key=lambda x: int(x[0]))
            ]
            
            return "\n".join(lyrics_lines)

        except requests.RequestException as e:
            print(f"[DEBUG] 가사 조회 실패: {e}")
            return None
        except (ValueError, json.JSONDecodeError) as e:
            print(f"[DEBUG] 잘못된 가사 형식: {e}")
            return None

    def _make_lrc_file(self, file_name: str, lyrics_json: str) -> str:
        """
        동기화된 가사를 가진 LRC 파일 생성.

        입력값:
            file_name (str): 출력 파일 기본 이름
            lyrics_json (str): 가사와 타임스탬프를 포함한 JSON 문자열

        반환값:
            생성된 LRC 파일 경로
        """
        os.makedirs("result", exist_ok=True)

        lyrics_data = json.loads(lyrics_json)
        output_path = os.path.join("result", f"{file_name}.lrc")

        with open(output_path, "w", encoding="utf-8") as f:
            # 타임스탬프 정렬 및 LRC 형식화
            lrc_lines = [
                f"[{int(time_ms) // 60000:02}:{(int(time_ms) % 60000) // 1000:02}.{(int(time_ms) % 1000) // 10:02}] {lyric}"
                for time_ms, lyric in sorted(lyrics_data.items(), key=lambda x: int(x[0]))
            ]
            f.write("\n".join(lrc_lines))
        print(f"[GENIEAPI] LRC 파일 생성: {output_path}")
        return output_path

    def _get_thumbnail_url(self, song_id: str) -> Optional[str]:
        """노래의 썸네일 URL을 가져옵니다."""
        try:
            response = requests.get(
                f"{self.SONG_INFO_BASE_URL}?xgnm={song_id}",
                headers=self._get_request_headers()
            )
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 썸네일 URL
            album_img = soup.select_one('div.photo-zone span.cover > img')
            if album_img and 'src' in album_img.attrs:
                img_url = album_img['src']
                if img_url.startswith('//'):
                    img_url = 'https:' + img_url
                return img_url.replace('/dims/resize/Q_80,0', '')
                
        except Exception as e:
            print(f"[DEBUG] 썸네일 URL 가져오기 실패: {e}")
            
        return None

    def _get_song_details(self, song_id: str) -> dict:
    """노래의 상세 정보를 가져옵니다."""
    details = {
        'thumbnail_url': None,
        'release_date': None,
        'genre': None,
        'publisher': None,
        'agency': None
    }
    
    try:
        response = requests.get(
            f"{self.SONG_INFO_BASE_URL}?xgnm={song_id}",
            headers=self._get_request_headers()
        )
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 썸네일 URL 가져오기
        album_img = soup.select_one('div.photo-zone span.cover > img')
        if album_img and 'src' in album_img.attrs:
            img_url = album_img['src']
            if img_url.startswith('//'):
                img_url = 'https:' + img_url
            details['thumbnail_url'] = img_url.replace('/dims/resize/Q_80,0', '')
        
        # 상세 정보 영역의 각 항목을 고정된 CSS 선택자로 가져오기
        genre_elem = soup.select_one('#body-content > div.album-detail-infos > div.info-zone > ul > li:nth-child(1) > span.value')
        if genre_elem:
            details['genre'] = genre_elem.text.strip()
            
        publisher_elem = soup.select_one('#body-content > div.album-detail-infos > div.info-zone > ul > li:nth-child(2) > span.value')
        if publisher_elem:
            details['publisher'] = publisher_elem.text.strip()
            
        agency_elem = soup.select_one('#body-content > div.album-detail-infos > div.info-zone > ul > li:nth-child(3) > span.value')
        if agency_elem:
            details['agency'] = agency_elem.text.strip()
            
        release_date_elem = soup.select_one('#body-content > div.album-detail-infos > div.info-zone > ul > li:nth-child(4) > span.value')
        if release_date_elem:
            details['release_date'] = release_date_elem.text.strip()
            
        print(f"[DEBUG] 노래 상세 정보 가져오기 성공: {song_id}")
        print(f"[DEBUG] 상세 정보: {details}")
                        
    except Exception as e:
        print(f"[DEBUG] 노래 상세 정보 가져오기 실패: {e}")
        traceback.print_exc()
        
    return details

            print(f"[DEBUG] 노래 상세 정보 가져오기 성공: {song_id}")
            print(f"[DEBUG] 상세 정보: {details}")
                        
        except Exception as e:
            print(f"[DEBUG] 노래 상세 정보 가져오기 실패: {e}")
            traceback.print_exc()
            
        return details
