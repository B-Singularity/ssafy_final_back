from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
import traceback 

from .serializers import (
    MovieSearchQueryParamSerializer, # 새로 만든 플랫 시리얼라이저 사용
    MovieSearchResultResponseSerializer,
    MovieDetailResponseSerializer
)
from apps.movie.application.dtos import (
    MovieSearchCriteriaDto, FilterOptionsDto, SortOptionDto, PaginationDto
)
from apps.movie.application.services import MovieAppService
from apps.movie.infrastructure.repositories import DjangoMovieRepository, DjangoMovieSearchRepository
from ...review_community.interface.serializers import PaginationInfoRequestSerializer



def get_movie_app_service():
    movie_repo = DjangoMovieRepository()
    search_repo = DjangoMovieSearchRepository()
    return MovieAppService(movie_repository=movie_repo, movie_search_repository=search_repo)


class MovieSearchAPIView(APIView):
    permission_classes = [AllowAny] 

    def get(self, request):
        query_param_serializer = MovieSearchQueryParamSerializer(data=request.query_params)
        if query_param_serializer.is_valid():
            vd = query_param_serializer.validated_data
            
            genres_list = None
            if vd.get('genres'):
                genres_list = [genre.strip() for genre in vd.get('genres').split(',') if genre.strip()]
            
            filter_options_dto = FilterOptionsDto(
                genres=genres_list,
                release_year_from=vd.get('release_year_from'),
                release_year_to=vd.get('release_year_to')
            )
            
            sort_option_dto = None
            sort_field_value = vd.get('sort_field')
            sort_direction_value = vd.get('sort_direction')
            rating_platform_value = vd.get('rating_platform')

            if sort_field_value:
                effective_sort_direction = sort_direction_value if sort_direction_value else 'asc'
                

                effective_rating_platform = None
                if sort_field_value == 'rating':
                    if not rating_platform_value:
                        # 평점 정렬 시 rating_platform이 없으면 오류 반환 (DTO 생성 전에)
                        return Response({"error": "평점 정렬 시 'rating_platform'을 지정해야 합니다."}, status=status.HTTP_400_BAD_REQUEST)
                    effective_rating_platform = rating_platform_value
                
                try:
                    sort_option_dto = SortOptionDto(
                        field=sort_field_value,
                        direction=effective_sort_direction,
                        rating_platform=effective_rating_platform
                    )
                except ValueError as e: # SortOptionDto 생성자에서 발생한 ValueError 처리
                    print(f"!!! [VIEW] SortOptionDto 생성 중 ValueError: {str(e)} !!!")
                    import traceback
                    traceback.print_exc()
                    return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

            pagination_dto = PaginationDto(
                page_number=vd.get('page_number') if vd.get('page_number') is not None else 1,
                page_size=vd.get('page_size') if vd.get('page_size') is not None else 20
            )

            criteria_dto = MovieSearchCriteriaDto(
                keyword=vd.get('keyword'),
                filters=filter_options_dto,
                sort_by=sort_option_dto,
                pagination=pagination_dto
            )
            
            service = get_movie_app_service()
            try:
                search_result_dto = service.search_movies(criteria_dto)
                response_serializer = MovieSearchResultResponseSerializer(search_result_dto)
                return Response(response_serializer.data)
            except ValueError as e: # ⭐️ DTO 생성자나 서비스에서 발생한 ValueError
                print(f"!!! [VIEW] MovieSearchAPIView - ValueError: {str(e)} !!!")
                import traceback
                traceback.print_exc()
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                print(f"!!! MovieSearchAPIView 서비스 호출 중 오류: {type(e).__name__} - {str(e)} !!!")
                import traceback
                traceback.print_exc()
                return Response({"error": "영화 검색 중 오류 발생"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            return Response(query_param_serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MovieDetailAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, movie_id):
        print(f"--- [VIEW_DETAIL] MovieDetailAPIView.get() 호출 시작, movie_id: {movie_id} ---")

        try:
            print("--- [VIEW_DETAIL] get_movie_app_service() 호출 직전 ---")
            service = get_movie_app_service()
            print(f"--- [VIEW_DETAIL] service.get_movie_details({movie_id}) 호출 직전 ---")

            movie_detail_dto = service.get_movie_details(movie_id=movie_id)

            print(f"--- [VIEW_DETAIL] service.get_movie_details() 반환값: {type(movie_detail_dto)} ---")
            if movie_detail_dto is not None:
                print(
                    f"--- [VIEW_DETAIL] movie_detail_dto ID (존재 시): {getattr(movie_detail_dto, 'movie_id', 'N/A')} ---")

            if movie_detail_dto:
                print(f"--- [VIEW_DETAIL] movie_detail_dto 있음, 시리얼라이저 생성 직전 ---")
                serializer = MovieDetailResponseSerializer(movie_detail_dto)
                print(f"--- [VIEW_DETAIL] MovieDetailResponseSerializer 생성 성공 ---")
                # print(f"--- [VIEW_DETAIL] Serializer data (일부): {serializer.data.get('movie_id')} ---") # 데이터가 너무 클 수 있으므로 주의
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                print(f"--- [VIEW_DETAIL] 영화 ID {movie_id}에 대한 정보 없음 (서비스가 None 반환), 404 반환 ---")
                return Response({"error": "영화를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)

        except ValueError as e:
            print(f"!!! [VIEW_DETAIL] ValueError 발생: {str(e)} !!!")
            traceback.print_exc()
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            print(f"!!! [VIEW_DETAIL] 일반 Exception 발생: {type(e).__name__} - {str(e)} !!!")
            traceback.print_exc()
            return Response({"error": "영화 상세 정보 조회 중 오류가 발생했습니다."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class PopularMoviesAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        service = get_movie_app_service()
        
        # PaginationInfoRequestSerializer를 사용하여 페이지네이션 파라미터 처리
        pagination_param_serializer = PaginationInfoRequestSerializer(data=request.query_params)
        if not pagination_param_serializer.is_valid():
            return Response(pagination_param_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        pagination_data = pagination_param_serializer.validated_data
        pagination_dto = PaginationDto(
            page_number=pagination_data.get('page_number', 1),
            page_size=pagination_data.get('page_size', 10) # 인기 영화는 페이지 크기를 다르게 할 수 있음
        )

        list_type = request.query_params.get('type', 'latest_highly_rated') 
        genre = request.query_params.get('genre')

        try:
            popular_movies_dto = service.get_popular_movies(
                list_type=list_type,
                genre_filter=genre,
                pagination_dto=pagination_dto
            )
            response_serializer = MovieSearchResultResponseSerializer(popular_movies_dto)
            return Response(response_serializer.data)
        except ValueError as e:
             return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"!!! PopularMoviesAPIView 서비스 호출 중 오류: {type(e).__name__} - {str(e)} !!!")
            traceback.print_exc()
            return Response({"error": "인기 영화 목록 조회 중 오류 발생"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)