from typing import List, Optional
from datetime import datetime

from django.utils import timezone

from apps.movie.domain.repositories import MovieRepository, MovieSearchRepository
from apps.movie.domain.aggregates.movie import Movie
from .dtos import (
    MovieSearchCriteriaDto, MovieSearchResultDto, SearchedMovieItemDto,
    MovieDetailDto, TitleInfoDisplayDto, PlotDisplayDto, StillCutDisplayDto,
    TrailerDisplayDto, MoviePlatformRatingDisplayDto, OTTInfoDisplayDto,
    PaginationDto
)

class MovieAppService:
    def __init__(self,
                 movie_repository,
                 movie_search_repository):
        self.movie_repository = movie_repository
        self.movie_search_repository = movie_search_repository

    def _movie_aggregate_to_detail_dto(self, movie):
        genres_display = [genre_vo.name for genre_vo in movie.genres]
        directors_display = [director_vo.name for director_vo in movie.directors]
        cast_display = [
            f"{actor_vo.name}{' (' + actor_vo.role_name + ')' if actor_vo.role_name else ''}"
            for actor_vo in movie.cast
        ]
        still_cuts_display = [
            StillCutDisplayDto(
                image_url=still_cut.image_url,
                caption=still_cut.caption,
                display_order=still_cut.display_order
            ) for still_cut in movie.still_cuts
        ]
        trailers_display = [
            TrailerDisplayDto(
                url=trailer.url,
                trailer_type=trailer.trailer_type,
                site_name=trailer.site_name,
                thumbnail_url=trailer.thumbnail_url
            ) for trailer in movie.trailer
        ]
        platform_ratings_display = [
            MoviePlatformRatingDisplayDto(
                platform_name=r.platform_name,
                score=r.score
            ) for r in movie.platform_ratings
        ]
        ott_availability_display = [
            OTTInfoDisplayDto(
                platform_name=o.platform_name,
                watch_url=o.watch_url,
                logo_image_url=o.logo_image_url,
                availability_note=o.availability_note
            ) for o in movie.ott_availability
        ]

        return MovieDetailDto(
            movie_id=movie.movie_id,
            title_info=TitleInfoDisplayDto(
                korean_title=movie.title_info.korean_title,
                original_title=movie.title_info.original_title
            ),
            plot=PlotDisplayDto(text=movie.plot.text),
            release_date_str=movie.release_date.formatted(),
            runtime_minutes=movie.runtime.minutes,
            poster_image_url=movie.poster_image.url,
            genres=genres_display,
            directors=directors_display,
            cast=cast_display,
            still_cuts=still_cuts_display,
            trailers=trailers_display,
            platform_ratings=platform_ratings_display,
            ott_availability=ott_availability_display,
            created_at_str=movie.created_at.isoformat() if movie.created_at else None,
            updated_at_str=movie.updated_at.isoformat() if movie.updated_at else None
        )

    def search_movies(self, criteria_dto):
        return self.movie_search_repository.search_movies(criteria=criteria_dto)

    def get_movie_details(self, movie_id):
        movie_aggregate = self.movie_repository.find_by_id(movie_id)
        if not movie_aggregate:
            return None

        movie_detail_dto = self._movie_aggregate_to_detail_dto(movie_aggregate)
        return movie_detail_dto

    def get_popular_movies(self,
                           list_type,
                           genre_filter=None,
                           pagination_dto=None
                           ):
        resolved_pagination = pagination_dto if pagination_dto else PaginationDto()
        return self.movie_search_repository.find_popular_movies(
            list_type_criterion=list_type,
            genre_filter=genre_filter,
            pagination=resolved_pagination
        )

