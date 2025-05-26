from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny

from .serializers import (
    MovieSearchCriteriaRequestSerializer, MovieSearchResultResponseSerializer,
    MovieDetailResponseSerializer
)

from apps.movie.application.dtos import (
    MovieSearchCriteriaDto, FilterOptionsDto, SortOptionDto, PaginationDto # DTO 임포트
)
from apps.movie.application.services import MovieAppService
from apps.movie.infrastructure.repositories import DjangoMovieRepository, DjangoMovieSearchRepository
import traceback

def get_movie_app_service():
    movie_repo = DjangoMovieRepository()
    search_repo = DjangoMovieSearchRepository()
    return MovieAppService(movie_repository=movie_repo, movie_search_repository=search_repo)


class MovieSearchAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        request_serializer = MovieSearchCriteriaRequestSerializer(data=request.query_params)
        if request_serializer.is_valid():
            vd = request_serializer.validated_data

            filters_data = vd.get('filters', {})
            filter_options_dto = FilterOptionsDto(
                genres=filters_data.get('genres'),
                release_year_from=filters_data.get('release_year_from'),
                release_year_to=filters_data.get('release_year_to')
            )

            sort_by_data = vd.get('sort_by')
            sort_option_dto = SortOptionDto(field=sort_by_data['field'],
                                            direction=sort_by_data['direction']) if sort_by_data else None

            pagination_data = vd.get('pagination', {})
            pagination_dto = PaginationDto(
                page_number=pagination_data.get('page_number', 1),
                page_size=pagination_data.get('page_size', 20)
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
            except Exception as e:
                return Response({"error": "영화 검색 중 오류 발생"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(request_serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MovieDetailAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, movie_id):
        service = get_movie_app_service()

        try:
            movie_detail_dto = service.get_movie_details(movie_id=movie_id)

            if movie_detail_dto:
                    
                serializer = MovieDetailResponseSerializer(movie_detail_dto)
                return Response(serializer.data, status=status.HTTP_200_OK)
            else:
                return Response({"error": "영화를 찾을 수 없습니다."}, status=status.HTTP_404_NOT_FOUND)
        
        except ValueError as e: # DTO 유효성 검사, 서비스 내의 명시적 ValueError 등
            traceback.print_exc() # ⭐️ 상세 스택 트레이스 출력
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        
        except Exception as e: # 그 외 모든 예상치 못한 오류
            traceback.print_exc() # ⭐️ 상세 스택 트레이스 출력
            return Response({"error": "영화 상세 정보 조회 중 오류가 발생했습니다."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PopularMoviesAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        service = get_movie_app_service()

        list_type = request.query_params.get('type', 'latest')  # 예시: 기본값 'latest'
        genre = request.query_params.get('genre')
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 10))

        try:
            pagination_dto = PaginationDto(page_number=page, page_size=page_size)
            popular_movies_dto = service.get_popular_movies(
                list_type=list_type,
                genre_filter=genre,
                pagination_dto=pagination_dto
            )
            response_serializer = MovieSearchResultResponseSerializer(popular_movies_dto)
            return Response(response_serializer.data)
        except ValueError as e:  # DTO 유효성 검사 오류 등
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": "인기 영화 목록 조회 중 오류 발생"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
