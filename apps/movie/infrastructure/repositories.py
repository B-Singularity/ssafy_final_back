from apps.movie.domain.aggregates.movie import Movie
from apps.movie.domain.value_objects.title_info_vo import TitleInfoVO
from apps.movie.domain.value_objects.plot_vo import PlotVO
from apps.movie.domain.value_objects.release_date_vo import ReleaseDateVO
from apps.movie.domain.value_objects.runtime_vo import RuntimeVO
from apps.movie.domain.value_objects.poster_image_vo import PosterImageVO
from apps.movie.domain.value_objects.genre_vo import GenreVO
from apps.movie.domain.value_objects.director_vo import DirectorVO
from apps.movie.domain.value_objects.actor_vo import ActorVO
from apps.movie.domain.value_objects.still_cut_vo import StillCutVO
from apps.movie.domain.value_objects.trailer_vo import TrailerVO
from apps.movie.domain.value_objects.movie_platform_rating_vo import MoviePlatformRatingVO
from apps.movie.domain.value_objects.ott_info_vo import OTTInfoVO

from apps.movie.domain.repositories import MovieRepository, MovieSearchRepository
from apps.movie.models import MovieModel, GenreModel, PersonModel, MovieCastMemberModel, StillCutModel, TrailerModel, MoviePlatformRatingModel, OTTPlatformModel, MovieOTTAvailabilityModel
from apps.movie.application.dtos import MovieSearchCriteriaDto, MovieSearchResultDto, SearchedMovieItemDto, PaginationDto, FilterOptionsDto, SortOptionDto

from typing import Optional, List
from django.db.models import Q, Avg, Subquery, OuterRef
from django.db import transaction

class DjangoMovieRepository(MovieRepository): # UserAccount -> Movie 타입 힌트 수정 필요 (이전 답변 참고)
    def _to_domain_object(self, movie_model): # MovieModel 타입 힌트 수정 필요
        if not movie_model:
            return None

        title_info_vo = TitleInfoVO(korean_title=movie_model.korean_title, original_title=movie_model.original_title)
        plot_vo = PlotVO(text=movie_model.plot) # PlotVO는 내부적으로 None 처리 가능
        
        release_date_vo = ReleaseDateVO(release_date=movie_model.release_date) if movie_model.release_date else None
        runtime_vo = RuntimeVO(minutes=movie_model.runtime_minutes) if movie_model.runtime_minutes is not None else None
        poster_image_vo = PosterImageVO(url=movie_model.poster_image_url) if movie_model.poster_image_url else None

        # 리스트 타입 필드들은 .all() 호출 결과가 비어있으면 빈 리스트가 됨
        genres_vo = [GenreVO(name=g.name) for g in movie_model.genres.all()]
        directors_vo = [DirectorVO(name=d.name, external_id=d.external_id) for d in movie_model.directors.all()]
        
        cast_vo = []
        if hasattr(movie_model, 'cast_members'): # cast_members 관계가 존재할 경우
            for cast_member in movie_model.cast_members.select_related('actor').all():
                cast_vo.append(ActorVO(name=cast_member.actor.name, role_name=cast_member.role_name,
                                       external_id=cast_member.actor.external_id))

        still_cuts_vo = [StillCutVO(image_url=sc.image_url, caption=sc.caption, display_order=sc.display_order) 
                         for sc in movie_model.still_cuts.all()]
        trailers_vo = [
            TrailerVO(url=t.url, trailer_type=t.trailer_type, site_name=t.site_name, thumbnail_url=t.thumbnail_url) 
            for t in movie_model.trailers.all()]

        platform_ratings_vo = [
            MoviePlatformRatingVO(platform_name=r.platform_name, score=r.score)
            for r in movie_model.platform_ratings.all()
        ]
        ott_availability_vo = [
            OTTInfoVO(platform_name=o.platform.name, watch_url=o.watch_url, logo_image_url=o.platform.logo_image_url,
                      availability_note=o.availability_note)
            for o in movie_model.ott_availability.select_related('platform').all()
        ]

        return Movie(
            movie_id=movie_model.id,
            title_info=title_info_vo,
            plot=plot_vo,
            release_date=release_date_vo, # None이 전달될 수 있음
            runtime=runtime_vo,           # None이 전달될 수 있음
            poster_image=poster_image_vo, # None이 전달될 수 있음
            genres=genres_vo,             # 빈 리스트 또는 VO가 채워진 리스트 전달
            directors=directors_vo,       # 빈 리스트 또는 VO가 채워진 리스트 전달
            cast=cast_vo,                 # 빈 리스트 또는 VO가 채워진 리스트 전달
            still_cuts=still_cuts_vo,     # 빈 리스트 또는 VO가 채워진 리스트 전달
            trailers=trailers_vo,         # 빈 리스트 또는 VO가 채워진 리스트 전달
            platform_ratings=platform_ratings_vo, # 빈 리스트 또는 VO가 채워진 리스트 전달
            ott_availability=ott_availability_vo, # 빈 리스트 또는 VO가 채워진 리스트 전달
            created_at=movie_model.created_at,
            updated_at=movie_model.updated_at
        )
    def find_by_id(self, movie_id: int) -> Optional[Movie]:
        try:
            movie_model = MovieModel.objects.prefetch_related(
                'genres', 'directors', 'cast_members__actor',
                'still_cuts', 'trailers', 'platform_ratings',
                'ott_availability__platform'
            ).get(id=movie_id)
            return self._to_domain_object(movie_model)
        except MovieModel.DoesNotExist:
            return None

    def save(self, movie: Movie) -> Movie:
        movie_model, created = MovieModel.objects.update_or_create(
            id=movie.movie_id if movie.movie_id and movie.movie_id > 0 else None,
            defaults={
                'korean_title': movie.title_info.korean_title,
                'original_title': movie.title_info.original_title,
                'plot': movie.plot.text if movie.plot else None,
                'release_date': movie.release_date.release_date if movie.release_date else None,
                'runtime_minutes': movie.runtime.minutes if movie.runtime else None,
                'poster_image_url': movie.poster_image.url if movie.poster_image else None,
            }
        )
        return self._to_domain_object(MovieModel.objects.get(id=movie_model.id))

    def delete(self, movie_id: int) -> None:
        MovieModel.objects.filter(id=movie_id).delete()


class DjangoMovieSearchRepository(MovieSearchRepository):
    def search_movies(self, criteria: MovieSearchCriteriaDto) -> MovieSearchResultDto:
        queryset = MovieModel.objects.all()

        if criteria.keyword:
            queryset = queryset.filter(
                Q(korean_title__icontains=criteria.keyword) |
                Q(original_title__icontains=criteria.keyword) |
                Q(directors__name__icontains=criteria.keyword) |  # M2M 검색
                Q(cast_members__actor__name__icontains=criteria.keyword)  # Through M2M 검색
            ).distinct()

        if criteria.filters:
            if criteria.filters.genres:
                queryset = queryset.filter(genres__name__in=criteria.filters.genres).distinct()
            if criteria.filters.release_year_from:
                queryset = queryset.filter(release_date__year__gte=criteria.filters.release_year_from)
            if criteria.filters.release_year_to:
                queryset = queryset.filter(release_date__year__lte=criteria.filters.release_year_to)
            # production_countries 필터는 제외됨

        if criteria.sort_by:
            sort_field = criteria.sort_by.field
            sort_direction = "-" if criteria.sort_by.direction.lower() == "desc" else ""
            if sort_field == "rating":
                # 대표 평점 필드가 MovieModel에 있다면 사용, 없다면 annotate 필요
                # 예: queryset = queryset.annotate(avg_rating=Avg('platform_ratings__score')).order_by(f'{sort_direction}avg_rating')
                # 여기서는 MovieModel에 rating 필드가 없으므로, 일단 제목으로 정렬
                queryset = queryset.order_by(f'{sort_direction}korean_title')
            elif sort_field == "release_date":
                queryset = queryset.order_by(f'{sort_direction}release_date')
            else:  # 인기도 등 다른 기준은 별도 필드 또는 로직 필요
                queryset = queryset.order_by(f'{sort_direction}korean_title')  # 기본 정렬
        else:
            queryset = queryset.order_by('-release_date')  # 기본 최신순

        total_results = queryset.count()

        start = (criteria.pagination.page_number - 1) * criteria.pagination.page_size
        end = start + criteria.pagination.page_size
        movies_page = queryset[start:end]

        searched_movies_dto = []
        for movie_model in movies_page:
            # 간단한 DTO 변환, 필요시 _to_domain_object 후 더 많은 정보 활용
            avg_rating_model = movie_model.platform_ratings.aggregate(avg_score=Avg('score'))
            avg_rating = avg_rating_model['avg_score'] if avg_rating_model['avg_score'] is not None else None

            searched_movies_dto.append(SearchedMovieItemDto(
                movie_id=movie_model.id,
                title=movie_model.korean_title,
                poster_image_url=movie_model.poster_image_url,
                release_year=movie_model.release_date.year if movie_model.release_date else None,
                rating=round(avg_rating, 1) if avg_rating is not None else None
            ))

        total_pages = (total_results + criteria.pagination.page_size - 1) // criteria.pagination.page_size

        message = "검색 결과가 없습니다." if total_results == 0 else None

        return MovieSearchResultDto(
            movies=searched_movies_dto,
            total_results=total_results,
            current_page=criteria.pagination.page_number,
            total_pages=total_pages,
            message=message
        )

    def find_popular_movies(self,
                            list_type_criterion: str,
                            genre_filter: Optional[str],
                            pagination: PaginationDto
                            ) -> MovieSearchResultDto:
        # 이 부분은 list_type_criterion (예: "domestic_rating", "latest")에 따라
        # 다른 정렬 및 필터링 로직이 필요합니다.
        # search_movies와 유사하게 queryset을 만들고 결과를 DTO로 변환합니다.
        # 예시로 최신 개봉 순으로 간단히 구현:
        criteria = MovieSearchCriteriaDto(
            filters=FilterOptionsDto(genres=[genre_filter] if genre_filter else None),
            sort_by=SortOptionDto(field="release_date", direction="desc") if list_type_criterion == "latest" else None,
            # 다른 기준 추가
            pagination=pagination
        )
        return self.search_movies(criteria)  # 기존 검색 로직 재활용 또는 별도 구현